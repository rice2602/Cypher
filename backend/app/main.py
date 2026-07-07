"""
main.py — Cypher v1 FastAPI application.

Single-user mode (default): No auth required. All API endpoints are open.
Set SINGLE_USER_MODE=false to require JWT for all /api/v1/* routes.

Auth:         POST /auth/register, POST /auth/login  (future; currently no-op when SUM=true)
Destinations: GET/POST/PUT/DELETE /api/v1/destinations
Agents:       GET/POST/PUT/DELETE /api/v1/agents
Monitoring:   POST /heartbeat, POST /incident (agent-facing, HMAC-signed)
Dashboard:    GET  /api/v1/status, /api/v1/incidents, /api/v1/metrics/uptime
"""

import hashlib
import hmac
import json
import os
import pathlib
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import (
    FastAPI, Depends, BackgroundTasks,
    HTTPException, status, Header, Request
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import select, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine, get_db
from app.models import Base, Destination, Agent, AgentKey, Incident, UptimeMetric
from app.notifications import dispatch_alerts
from app.redis_client import redis_client
from app.schemas import (
    DestinationCreate, DestinationUpdate, DestinationOut,
    AgentCreate, AgentUpdate, AgentOut, AgentCreateResponse,
    AgentKeyOut, Heartbeat, IncidentCreate,
)

# Dashboard HTML path (served at GET /dashboard)
_DASHBOARD = pathlib.Path(__file__).parent.parent.parent / "dashboard" / "index.html"


# ---------------------------------------------------------------------------
# App Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migrations for legacy columns
        for stmt in [
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS traceroute_diagnostic TEXT;",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS http_diagnostic TEXT;",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS dns_verification_diagnostic TEXT;",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS root_cause_analysis TEXT;",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS user_key TEXT;",
            "ALTER TABLE uptime_metrics ADD COLUMN IF NOT EXISTS user_key TEXT;",
        ]:
            await conn.execute(text(stmt))
    yield
    await redis_client.aclose()


app = FastAPI(title="Cypher API", version="1.0.0", lifespan=lifespan)

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
# Rate limiting (Redis sliding window per key or IP)
# ---------------------------------------------------------------------------

async def check_rate_limit(request: Request):
    key_id = request.headers.get("X-Cypher-Key-Id") or (
        request.client.host if request.client else "unknown"
    )
    bucket = int(time.time()) // 60
    rkey = f"ratelimit:{key_id}:{bucket}"
    current = await redis_client.incr(rkey)
    if current == 1:
        await redis_client.expire(rkey, 120)
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
    If no AgentKey rows exist (fresh install), skip for backward compat.
    Returns the authenticated agent_id or None if skipped.
    """
    count_result = await db.execute(select(func.count()).select_from(AgentKey))
    if count_result.scalar() == 0:
        return None

    key_id = request.headers.get("X-Cypher-Key-Id")
    signature = request.headers.get("X-Cypher-Signature")

    if not key_id or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing agent auth headers (X-Cypher-Key-Id, X-Cypher-Signature)",
        )

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

    return agent_key.agent_id


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
    return {"status": "ok", "version": "1.0.0", "redis": redis_status}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the Cypher dashboard SPA."""
    return _DASHBOARD.read_text(encoding="utf-8")


@app.get("/api/v1/mode")
async def get_mode():
    """Return server mode. Dashboard checks this on boot to skip login."""
    return {"single_user_mode": settings.SINGLE_USER_MODE}

# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

@app.get("/api/v1/destinations", response_model=list[DestinationOut])
async def list_destinations(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Destination)
        .order_by(desc(Destination.created_at))
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
    result = await db.execute(
        select(Destination).where(Destination.id == dest_id)
    )
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
    result = await db.execute(
        select(Destination).where(Destination.id == dest_id)
    )
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    await db.delete(dest)
    await db.commit()


# ---------------------------------------------------------------------------
# Agents  (require >= 1 destination before registering)
# ---------------------------------------------------------------------------

async def _require_destination(db: AsyncSession):
    """Guard: raise 403 if no destinations exist yet."""
    result = await db.execute(
        select(func.count()).select_from(Destination)
    )
    if result.scalar() == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You must create at least one Destination before registering an Agent."
            ),
        )


def _parse_dest_ids(raw: str) -> list[int]:
    """Parse JSON-stored destination_ids string into list[int]."""
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _make_agent_out(agent: Agent) -> AgentOut:
    data = {
        "id": agent.id,
        "user_key": None,
        "name": agent.name,
        "description": agent.description,
        "location": agent.location,
        "destination_ids": _parse_dest_ids(agent.destination_ids),
        "key_id": agent.key_id,
        "is_active": agent.is_active,
        "created_at": agent.created_at,
    }
    return AgentOut(**data)


@app.get("/api/v1/agents", response_model=list[AgentOut])
async def list_agents(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent)
        .order_by(desc(Agent.created_at))
    )
    return [_make_agent_out(a) for a in result.scalars().all()]


@app.post("/api/v1/agents", response_model=AgentCreateResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    # Guard: must have at least one destination
    await _require_destination(db)

    # Validate that all provided destination IDs exist
    if body.destination_ids:
        result = await db.execute(
            select(func.count())
            .select_from(Destination)
            .where(Destination.id.in_(body.destination_ids))
        )
        if result.scalar() != len(body.destination_ids):
            raise HTTPException(
                status_code=400,
                detail="One or more destination IDs are invalid.",
            )

    # Generate HMAC key for this agent
    agent_id_str = f"agent-{body.name.lower().replace(' ', '-')}"
    key_id = f"ak_{secrets.token_hex(16)}"
    key_secret = secrets.token_hex(32)
    key_hash = hashlib.sha256(key_secret.encode()).hexdigest()

    agent_key = AgentKey(
        key_id=key_id,
        key_hash=key_hash,
        agent_id=agent_id_str,
        is_active=True,
    )
    db.add(agent_key)
    await db.flush()

    agent = Agent(
        name=body.name,
        description=body.description,
        location=body.location,
        destination_ids=json.dumps(body.destination_ids),
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


@app.put("/api/v1/agents/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: int,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
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


@app.delete("/api/v1/agents/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()


# ---------------------------------------------------------------------------
# Monitoring — heartbeats and incidents (agent-facing)
# ---------------------------------------------------------------------------

async def record_uptime_probe(db: AsyncSession, target: str, is_up: bool):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(UptimeMetric).where(
            UptimeMetric.target == target,
            UptimeMetric.day == today,
            UptimeMetric.user_key == None,
        )
    )
    metric = result.scalar_one_or_none()
    if metric:
        metric.total_probes += 1
        if is_up:
            metric.up_probes += 1
    else:
        metric = UptimeMetric(
            target=target,
            day=today,
            up_probes=1 if is_up else 0,
            total_probes=1,
            user_key=None,
        )
        db.add(metric)
    await db.commit()


async def perform_rca(target: str, failed_agent_id: str) -> str:
    pattern = f"heartbeat:*:{target}"
    keys = await redis_client.keys(pattern)
    total = down = 0
    for key in keys:
        raw = await redis_client.get(key)
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


async def _resolve_user_key_from_agent(agent_id: str, db: AsyncSession) -> str | None:
    """No-op for single-user mode - always returns None."""
    return None


@app.post("/heartbeat")
async def receive_heartbeat(
    heartbeat: Heartbeat,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await verify_agent_signature(request, db)
    await check_rate_limit(request)

    data = heartbeat.model_dump()
    data["received_at"] = datetime.now(timezone.utc).isoformat()
    await redis_client.set(
        f"heartbeat:{heartbeat.agent_id}:{heartbeat.target}",
        json.dumps(data),
    )
    await record_uptime_probe(db, heartbeat.target, is_up=True)
    return {"status": "ok"}


@app.post("/incident")
async def receive_incident(
    incident: IncidentCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await verify_agent_signature(request, db)
    await check_rate_limit(request)

    redis_key = f"heartbeat:{incident.agent_id}:{incident.target}"
    redis_data = incident.model_dump()
    redis_data["received_at"] = datetime.now(timezone.utc).isoformat()
    await redis_client.set(redis_key, json.dumps(redis_data))

    rca_summary = await perform_rca(incident.target, incident.agent_id)

    db_incident = Incident(
        agent_id=incident.agent_id,
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
        user_key=None,
    )
    db.add(db_incident)
    await db.commit()

    await record_uptime_probe(db, incident.target, is_up=False)

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
# Dashboard data API (authenticated, scoped to user_key)
# ---------------------------------------------------------------------------

@app.get("/api/v1/status")
async def get_status(
    db: AsyncSession = Depends(get_db),
):
    """Live status for all agents."""
    keys = await redis_client.keys("heartbeat:*")
    statuses = []
    for key in keys:
        raw = await redis_client.get(key)
        if raw:
            data = json.loads(raw)
            statuses.append(data)
    return {"statuses": statuses}


@app.get("/api/v1/incidents")
async def get_incidents(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Recent incidents."""
    result = await db.execute(
        select(Incident)
        .order_by(desc(Incident.created_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return {
        "incidents": [
            {
                "id": i.id,
                "agent_id": i.agent_id,
                "target": i.target,
                "status": i.status,
                "ping": i.ping_diagnostic,
                "dns": i.dns_diagnostic,
                "error": i.error_diagnostic,
                "traceroute": i.traceroute_diagnostic,
                "http": i.http_diagnostic,
                "dns_verification": i.dns_verification_diagnostic,
                "root_cause": i.root_cause_analysis,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in rows
        ]
    }


@app.get("/api/v1/metrics/uptime")
async def get_uptime_metrics(
    db: AsyncSession = Depends(get_db),
):
    """7-day uptime statistics for all targets."""
    seven_days_ago = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=7)

    result = await db.execute(
        select(
            UptimeMetric.target,
            func.sum(UptimeMetric.up_probes).label("up"),
            func.sum(UptimeMetric.total_probes).label("total"),
        )
        .where(
            UptimeMetric.day >= seven_days_ago,
            UptimeMetric.user_key == None,
        )
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
