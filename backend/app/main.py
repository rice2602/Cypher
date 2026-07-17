"""
main.py — Cypher FastAPI application.

Destinations: GET/POST/PUT/DELETE /api/v1/destinations
Agents:       GET/POST/PUT/DELETE /api/v1/agents
Agent:        GET /api/v1/agent/targets (agent fetches its assigned targets)
Monitoring:   POST /heartbeat, POST /incident (agent-facing, HMAC-signed)
Dashboard:    GET /api/v1/status/summary, /api/v1/incidents, /api/v1/metrics/uptime
"""

import hashlib
import hmac
import json
import logging
import pathlib
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import (
    FastAPI, Depends, BackgroundTasks,
    HTTPException, status, Header, Request
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import select, desc, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("cypher")

from app.config import settings
from app.database import engine, get_db
from app.models import Base, Destination, Agent, AgentKey, Incident, UptimeMetric
from app.notifications import dispatch_alerts
from app.redis_client import redis_client
from app.schemas import (
    DestinationCreate, DestinationUpdate, DestinationOut,
    AgentCreate, AgentUpdate, AgentOut, AgentCreateResponse,
    AgentTargetsResponse, Heartbeat, IncidentCreate,
    AgentProbeStatus, TargetStatus,
)

# Dashboard HTML path
_DASHBOARD = pathlib.Path(__file__).parent.parent.parent / "dashboard" / "index.html"


# ---------------------------------------------------------------------------
# App Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migrations
        for stmt in [
            # Legacy incident columns
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS traceroute_diagnostic TEXT;",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS http_diagnostic TEXT;",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS dns_verification_diagnostic TEXT;",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS root_cause_analysis TEXT;",
            # Agent metadata columns
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS agent_uid VARCHAR(64);",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS metadata_version VARCHAR(32);",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS metadata_hostname VARCHAR(255);",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS metadata_region VARCHAR(128);",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS metadata_uptime INTEGER;",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ;",
            # Incident agent metadata
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS agent_uid VARCHAR(64) DEFAULT 'unknown';",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS agent_hostname VARCHAR(255);",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS agent_region VARCHAR(128);",
            # AgentKey.agent_uid
            "ALTER TABLE agent_keys ADD COLUMN IF NOT EXISTS agent_uid VARCHAR(64);",
            # Backfill agent_uid for legacy agents
            """DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM agents WHERE agent_uid IS NULL LIMIT 1) THEN
                    UPDATE agents SET agent_uid = 'agent-' || substr(md5(random()::text), 1, 8)
                    WHERE agent_uid IS NULL;
                END IF;
            END$$;""",
            # Backfill agent_keys.agent_uid from agents
            """DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM agent_keys ak LEFT JOIN agents a ON ak.agent_uid IS NULL LIMIT 1) THEN
                    UPDATE agent_keys ak SET agent_uid = a.agent_uid
                    FROM agents a WHERE ak.key_id = a.key_id AND ak.agent_uid IS NULL;
                END IF;
            END$$;""",
            # Indexes
            "CREATE INDEX IF NOT EXISTS idx_incidents_target_created ON incidents(target, created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_incidents_agent_uid ON incidents(agent_uid);",
            "CREATE INDEX IF NOT EXISTS idx_uptime_metrics_target_day ON uptime_metrics(target, day DESC);",
        ]:
            await conn.execute(text(stmt))
    yield
    try:
        await redis_client.aclose()
    except Exception:
        pass


app = FastAPI(title="Cypher API", version="2.0.0", lifespan=lifespan)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

async def check_rate_limit(request: Request):
    key_id = request.headers.get("X-Cypher-Key-Id") or (
        request.client.host if request.client else "unknown"
    )
    bucket = int(time.time()) // 60
    rkey = f"ratelimit:{key_id}:{bucket}"
    pipe = redis_client.pipeline()
    pipe.incr(rkey)
    pipe.expire(rkey, 120)
    results = await pipe.execute()
    current = results[0]
    if current > settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
        )


# ---------------------------------------------------------------------------
# Agent HMAC signature verification
# ---------------------------------------------------------------------------

async def verify_agent_signature(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> str | None:
    """
    Verify HMAC-SHA256 on agent requests.
    If no AgentKey rows exist, skip for backward compat.
    Returns the authenticated agent_uid or None if skipped.
    """
    count_result = await db.execute(select(func.count()).select_from(AgentKey))
    if count_result.scalar() == 0:
        return None

    key_id = request.headers.get("X-Cypher-Key-Id")
    signature = request.headers.get("X-Cypher-Signature")
    timestamp = request.headers.get("X-Cypher-Timestamp")

    if not key_id or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing agent auth headers",
        )

    if timestamp:
        try:
            ts = int(timestamp)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid timestamp header")
        if abs(time.time() - ts) > 300:
            raise HTTPException(status_code=401, detail="Request timestamp expired")

    result = await db.execute(select(AgentKey).where(AgentKey.key_id == key_id))
    agent_key = result.scalar_one_or_none()

    if not agent_key:
        raise HTTPException(status_code=401, detail="Unknown agent key")
    if not agent_key.is_active:
        raise HTTPException(status_code=401, detail="Agent key revoked")
    if agent_key.expires_at and agent_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Agent key expired")

    body = await request.body()
    expected = hmac.new(
        agent_key.key_hash.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    return agent_key.agent_uid


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/")
async def health_check():
    try:
        await redis_client.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {e}"
    return {"status": "ok", "version": "2.0.0", "redis": redis_status}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return _DASHBOARD.read_text(encoding="utf-8")


@app.get("/api/v1/mode")
async def get_mode():
    return {"single_user_mode": settings.SINGLE_USER_MODE}


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

@app.get("/api/v1/destinations", response_model=list[DestinationOut])
async def list_destinations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Destination).order_by(desc(Destination.created_at))
    )
    return result.scalars().all()


@app.post("/api/v1/destinations", response_model=DestinationOut, status_code=201)
async def create_destination(
    body: DestinationCreate,
    db: AsyncSession = Depends(get_db),
):
    dest = Destination(**body.model_dump())
    db.add(dest)
    await db.commit()
    await db.refresh(dest)
    return dest


@app.put("/api/v1/destinations/{dest_id}", response_model=DestinationOut)
async def update_destination(
    dest_id: int,
    body: DestinationUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Destination).where(Destination.id == dest_id))
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(dest, field, value)
    await db.commit()
    await db.refresh(dest)
    return dest


@app.delete("/api/v1/destinations/{dest_id}", status_code=204)
async def delete_destination(
    dest_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Destination).where(Destination.id == dest_id))
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    await db.delete(dest)
    await db.commit()


# ---------------------------------------------------------------------------
# Agents (backend-generated IDs, auto-assign to all destinations)
# ---------------------------------------------------------------------------

def _parse_dest_ids(raw: str) -> list[int]:
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _make_agent_out(agent: Agent) -> AgentOut:
    return AgentOut(
        id=agent.id,
        name=agent.name,
        agent_uid=agent.agent_uid,
        description=agent.description,
        location=agent.location,
        destination_ids=_parse_dest_ids(agent.destination_ids),
        key_id=agent.key_id,
        metadata_version=agent.metadata_version,
        metadata_hostname=agent.metadata_hostname,
        metadata_region=agent.metadata_region,
        metadata_uptime=agent.metadata_uptime,
        is_active=agent.is_active,
        last_seen=agent.last_seen,
        created_at=agent.created_at,
    )


@app.get("/api/v1/agents", response_model=list[AgentOut])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).order_by(desc(Agent.created_at)))
    return [_make_agent_out(a) for a in result.scalars().all()]


@app.post("/api/v1/agents", response_model=AgentCreateResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    # Backend generates unique agent ID
    agent_uid = f"agent-{uuid.uuid4().hex[:12]}"

    # Validate explicit destination IDs if provided
    dest_ids = body.destination_ids or []
    if dest_ids:
        result = await db.execute(
            select(func.count()).select_from(Destination)
            .where(Destination.id.in_(dest_ids))
        )
        if result.scalar() != len(dest_ids):
            raise HTTPException(status_code=400, detail="One or more destination IDs are invalid.")

    # Generate HMAC key
    key_id = f"ak_{secrets.token_hex(16)}"
    key_secret = secrets.token_hex(32)
    key_hash = hashlib.sha256(key_secret.encode()).hexdigest()

    agent_key = AgentKey(
        key_id=key_id,
        key_hash=key_hash,
        agent_uid=agent_uid,
        is_active=True,
    )
    db.add(agent_key)
    await db.flush()

    agent = Agent(
        name=body.name,
        description=body.description,
        location=body.location,
        agent_uid=agent_uid,
        destination_ids=json.dumps(dest_ids),
        key_id=key_id,
        is_active=True,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    return AgentCreateResponse(
        agent=_make_agent_out(agent),
        key_id=key_id,
        key_secret=key_secret,
    )


@app.put("/api/v1/agents/{agent_db_id}", response_model=AgentOut)
async def update_agent(
    agent_db_id: int,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_db_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    update_data = body.model_dump(exclude_unset=True)
    if "destination_ids" in update_data:
        update_data["destination_ids"] = json.dumps(update_data["destination_ids"])
    for field, value in update_data.items():
        setattr(agent, field, value)
    await db.commit()
    await db.refresh(agent)
    return _make_agent_out(agent)


@app.delete("/api/v1/agents/{agent_db_id}", status_code=204)
async def delete_agent(
    agent_db_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_db_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    # Also delete the agent key
    if agent.key_id:
        key_result = await db.execute(
            select(AgentKey).where(AgentKey.key_id == agent.key_id)
        )
        ak = key_result.scalar_one_or_none()
        if ak:
            await db.delete(ak)
    await db.delete(agent)
    await db.commit()


# ---------------------------------------------------------------------------
# Agent target fetch (backend is source of truth)
# ---------------------------------------------------------------------------

@app.get("/api/v1/agent/targets", response_model=AgentTargetsResponse)
async def get_agent_targets(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Agent fetches its assigned targets.
    If agent has explicit destination_ids → return those.
    If empty → return ALL active destinations.
    """
    key_id = request.headers.get("X-Cypher-Key-Id")
    if not key_id:
        raise HTTPException(status_code=401, detail="Missing X-Cypher-Key-Id header")

    result = await db.execute(select(AgentKey).where(AgentKey.key_id == key_id))
    agent_key = result.scalar_one_or_none()
    if not agent_key or not agent_key.is_active:
        raise HTTPException(status_code=401, detail="Invalid agent key")

    # Find the agent
    agent_result = await db.execute(
        select(Agent).where(Agent.agent_uid == agent_key.agent_uid)
    )
    agent = agent_result.scalar_one_or_none()
    if not agent or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found or inactive")

    assigned_ids = _parse_dest_ids(agent.destination_ids)

    if assigned_ids:
        # Agent has explicit destination assignments
        dest_result = await db.execute(
            select(Destination)
            .where(Destination.id.in_(assigned_ids), Destination.is_active == True)
        )
    else:
        # Auto-assign: return all active destinations
        dest_result = await db.execute(
            select(Destination).where(Destination.is_active == True)
        )

    targets = []
    for dest in dest_result.scalars().all():
        host = dest.url
        if dest.port:
            target_str = f"{host}:{dest.port}"
        else:
            target_str = f"{host}:443"
        targets.append(target_str)

    return AgentTargetsResponse(targets=targets)


# ---------------------------------------------------------------------------
# Monitoring — heartbeats and incidents
# ---------------------------------------------------------------------------

async def record_uptime_probe(db: AsyncSession, target: str, is_up: bool):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    up_inc = 1 if is_up else 0
    stmt = pg_insert(UptimeMetric).values(
        target=target,
        day=today,
        up_probes=up_inc,
        total_probes=1,
    ).on_conflict_do_update(
        index_elements=["target", "day"],
        set_={
            "total_probes": UptimeMetric.total_probes + 1,
            "up_probes": UptimeMetric.up_probes + up_inc,
        },
    )
    await db.execute(stmt)
    await db.commit()


async def perform_rca(target: str, failed_agent_uid: str) -> str:
    pattern = f"heartbeat:*:{target}"
    keys = []
    async for key in redis_client.scan_iter(match=pattern, count=100):
        keys.append(key)
    if not keys:
        return "Single agent monitoring this target. Global status unconfirmed."
    pipe = redis_client.pipeline()
    for key in keys:
        pipe.get(key)
    results = await pipe.execute()
    total = down = 0
    for raw in results:
        if raw:
            try:
                data = json.loads(raw)
                if data.get("target") == target:
                    total += 1
                    if data.get("status") == "DOWN":
                        down += 1
            except Exception:
                pass
    if total <= 1:
        return "Single agent monitoring this target. Global status unconfirmed."
    if down == total:
        return f"Global Outage: All {total} agents see target as DOWN."
    if down == 1:
        return f"Localized Issue: Only 1 of {total} agents sees target as DOWN."
    return f"Partial Outage: {down} of {total} agents see target as DOWN."


@app.post("/heartbeat")
async def receive_heartbeat(
    heartbeat: Heartbeat,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    agent_uid = await verify_agent_signature(request, db)
    await check_rate_limit(request)

    data = heartbeat.model_dump()
    data["received_at"] = datetime.now(timezone.utc).isoformat()

    # TTL = probe_interval * multiplier (default 90s)
    ttl = settings.DEFAULT_PROBE_INTERVAL * settings.HEARTBEAT_TTL_MULTIPLIER

    await redis_client.set(
        f"heartbeat:{heartbeat.agent_id}:{heartbeat.target}",
        json.dumps(data),
        ex=ttl,
    )
    await record_uptime_probe(db, heartbeat.target, is_up=True)

    # Update agent metadata + last_seen
    if agent_uid:
        meta = heartbeat.metadata
        await db.execute(
            text("""
                UPDATE agents SET
                    last_seen = NOW(),
                    metadata_version = COALESCE(:version, metadata_version),
                    metadata_hostname = COALESCE(:hostname, metadata_hostname),
                    metadata_region = COALESCE(:region, metadata_region),
                    metadata_uptime = COALESCE(:uptime, metadata_uptime)
                WHERE agent_uid = :agent_uid
            """),
            {
                "agent_uid": agent_uid,
                "version": meta.version if meta else None,
                "hostname": meta.hostname if meta else None,
                "region": meta.region if meta else None,
                "uptime": meta.uptime if meta else None,
            },
        )
        await db.commit()

    logger.info("heartbeat UP agent=%s target=%s latency=%sms",
                heartbeat.agent_id, heartbeat.target, heartbeat.latency_ms)
    return {"status": "ok"}


@app.post("/incident")
async def receive_incident(
    incident: IncidentCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    agent_uid = await verify_agent_signature(request, db)
    await check_rate_limit(request)

    redis_key = f"heartbeat:{incident.agent_id}:{incident.target}"
    redis_data = incident.model_dump()
    redis_data["received_at"] = datetime.now(timezone.utc).isoformat()

    ttl = settings.DEFAULT_PROBE_INTERVAL * settings.HEARTBEAT_TTL_MULTIPLIER
    await redis_client.set(redis_key, json.dumps(redis_data), ex=ttl)

    rca_summary = await perform_rca(incident.target, incident.agent_id)

    # Get agent metadata for incident record
    agent_hostname = None
    agent_region = None
    if incident.metadata:
        agent_hostname = incident.metadata.hostname
        agent_region = incident.metadata.region

    db_incident = Incident(
        agent_uid=incident.agent_id,
        target=incident.target,
        status=incident.status,
        latency_ms=None,
        ping_diagnostic=incident.diagnostics.ping,
        dns_diagnostic=incident.diagnostics.dns,
        error_diagnostic=incident.diagnostics.error,
        traceroute_diagnostic=incident.diagnostics.traceroute,
        http_diagnostic=incident.diagnostics.http,
        dns_verification_diagnostic=incident.diagnostics.dns_verification,
        root_cause_analysis=rca_summary,
        agent_hostname=agent_hostname,
        agent_region=agent_region,
    )
    db.add(db_incident)
    await db.commit()

    await record_uptime_probe(db, incident.target, is_up=False)

    # Update agent last_seen
    if agent_uid:
        meta = incident.metadata
        await db.execute(
            text("""
                UPDATE agents SET
                    last_seen = NOW(),
                    metadata_version = COALESCE(:version, metadata_version),
                    metadata_hostname = COALESCE(:hostname, metadata_hostname),
                    metadata_region = COALESCE(:region, metadata_region),
                    metadata_uptime = COALESCE(:uptime, metadata_uptime)
                WHERE agent_uid = :agent_uid
            """),
            {
                "agent_uid": agent_uid,
                "version": meta.version if meta else None,
                "hostname": meta.hostname if meta else None,
                "region": meta.region if meta else None,
                "uptime": meta.uptime if meta else None,
            },
        )
        await db.commit()

    logger.warning("incident DOWN agent=%s target=%s rca=%s",
                   incident.agent_id, incident.target, rca_summary)

    background_tasks.add_task(
        dispatch_alerts,
        incident.agent_id,
        incident.target,
        "DOWN",
        incident.diagnostics.error,
        rca_summary,
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dashboard data API (aggregated per-target, 3-state)
# ---------------------------------------------------------------------------

@app.get("/api/v1/status/summary")
async def get_status_summary(
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregated per-target status with staleness detection.
    Status logic:
      UP      = all agents report UP and none stale
      DOWN    = all agents report DOWN
      DEGRADED = mixed statuses, or some agents stale but at least one UP
      STALE   = all agents stale or no data
    """
    # Gather all heartbeat keys
    keys = []
    async for key in redis_client.scan_iter(match="heartbeat:*", count=100):
        keys.append(key)
    if not keys:
        return {"targets": [], "stats": {"total": 0, "up": 0, "degraded": 0, "down": 0}}

    pipe = redis_client.pipeline()
    for key in keys:
        pipe.get(key)
    results = await pipe.execute()

    # Gather all active agents for name/region lookup
    agent_result = await db.execute(select(Agent))
    agents_by_uid = {a.agent_uid: a for a in agent_result.scalars().all()}

    # Group by target
    from collections import defaultdict
    target_agents: dict[str, list[dict]] = defaultdict(list)
    now = datetime.now(timezone.utc)

    for raw in results:
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        target = data.get("target", "")
        agent_id = data.get("agent_id", "")
        received_at = data.get("received_at")
        is_stale = True
        if received_at:
            try:
                ts = datetime.fromisoformat(received_at)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (now - ts).total_seconds()
                stale_threshold = settings.DEFAULT_PROBE_INTERVAL * settings.HEARTBEAT_TTL_MULTIPLIER
                is_stale = age > stale_threshold
            except Exception:
                pass

        agent_info = agents_by_uid.get(agent_id, None)
        agent_details = {
            "agent_uid": agent_id,
            "agent_name": agent_info.name if agent_info else agent_id,
            "status": "STALE" if is_stale else data.get("status", "UNKNOWN"),
            "latency_ms": data.get("latency_ms"),
            "last_seen": received_at,
            "region": (agent_info.metadata_region if agent_info else None) or "unknown",
            "hostname": (agent_info.metadata_hostname if agent_info else None) or "unknown",
        }
        target_agents[target].append(agent_details)

    # Build target summaries
    targets = []
    stats = {"total": 0, "up": 0, "degraded": 0, "down": 0}

    for target, agents in sorted(target_agents.items()):
        up_count = sum(1 for a in agents if a["status"] == "UP")
        down_count = sum(1 for a in agents if a["status"] == "DOWN")
        stale_count = sum(1 for a in agents if a["status"] == "STALE")
        total = len(agents)

        # Determine aggregated status
        if up_count == total and stale_count == 0:
            agg_status = "UP"
        elif down_count == total:
            agg_status = "DOWN"
        elif up_count > 0 and (down_count > 0 or stale_count > 0):
            agg_status = "DEGRADED"
        elif stale_count > 0:
            agg_status = "STALE"
        else:
            agg_status = "UNKNOWN"

        # Average latency (only from UP agents)
        up_latencies = [a["latency_ms"] for a in agents if a["status"] == "UP" and a["latency_ms"] is not None]
        avg_lat = round(sum(up_latencies) / len(up_latencies), 1) if up_latencies else None

        # Last seen (most recent across all agents)
        last_seen = None
        for a in agents:
            if a["last_seen"]:
                if last_seen is None or a["last_seen"] > last_seen:
                    last_seen = a["last_seen"]

        is_stale = agg_status in ("STALE", "UNKNOWN")

        targets.append(TargetStatus(
            target=target,
            status=agg_status,
            agent_count=total,
            agents_up=up_count,
            agents_down=down_count,
            agents_stale=stale_count,
            avg_latency_ms=avg_lat,
            last_seen=last_seen,
            is_stale=is_stale,
            agent_details=[AgentProbeStatus(**a) for a in agents],
        ).model_dump())

        stats["total"] += 1
        if agg_status == "UP":
            stats["up"] += 1
        elif agg_status == "DOWN":
            stats["down"] += 1
        else:
            stats["degraded"] += 1

    # Sort: DOWN first, then DEGRADED, then STALE, then UP
    priority = {"DOWN": 0, "DEGRADED": 1, "STALE": 2, "UNKNOWN": 3, "UP": 4}
    targets.sort(key=lambda t: (priority.get(t["status"], 9), t["target"]))

    return {"targets": targets, "stats": stats}


# Keep legacy endpoint for backward compat
@app.get("/api/v1/status")
async def get_status(db: AsyncSession = Depends(get_db)):
    """Legacy: raw per-agent status. Use /api/v1/status/summary instead."""
    keys = []
    async for key in redis_client.scan_iter(match="heartbeat:*", count=100):
        keys.append(key)
    if not keys:
        return {"statuses": []}
    pipe = redis_client.pipeline()
    for key in keys:
        pipe.get(key)
    results = await pipe.execute()
    statuses = []
    for raw in results:
        if raw:
            try:
                statuses.append(json.loads(raw))
            except Exception:
                pass
    return {"statuses": statuses}


@app.get("/api/v1/incidents")
async def get_incidents(
    limit: int = 50,
    target: str = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Incident).order_by(desc(Incident.created_at)).limit(limit)
    if target:
        query = query.where(Incident.target == target)
    result = await db.execute(query)
    rows = result.scalars().all()
    return {
        "incidents": [
            {
                "id": i.id,
                "agent_uid": i.agent_uid,
                "target": i.target,
                "status": i.status,
                "ping": i.ping_diagnostic,
                "dns": i.dns_diagnostic,
                "error": i.error_diagnostic,
                "traceroute": i.traceroute_diagnostic,
                "http": i.http_diagnostic,
                "dns_verification": i.dns_verification_diagnostic,
                "root_cause": i.root_cause_analysis,
                "agent_hostname": i.agent_hostname,
                "agent_region": i.agent_region,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in rows
        ]
    }


@app.get("/api/v1/metrics/uptime")
async def get_uptime_metrics(db: AsyncSession = Depends(get_db)):
    seven_days_ago = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=7)
    result = await db.execute(
        select(
            UptimeMetric.target,
            func.sum(UptimeMetric.up_probes).label("up"),
            func.sum(UptimeMetric.total_probes).label("total"),
        )
        .where(UptimeMetric.day >= seven_days_ago)
        .group_by(UptimeMetric.target)
    )
    metrics = {}
    for target, up, total in result.all():
        availability = (up / total * 100) if total > 0 else 100.0
        metrics[target] = {
            "target": target,
            "up_probes": int(up),
            "total_probes": int(total),
            "availability_percentage": round(availability, 2),
        }
    return {"metrics": metrics}
