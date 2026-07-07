"""
main.py — Cypher v1 FastAPI application.

Auth:    POST /auth/register, POST /auth/login, GET /auth/me
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

from app.auth import create_jwt, verify_jwt, hash_password, verify_password
from app.config import settings
from app.database import engine, get_db
from app.models import Base, User, Destination, Agent, AgentKey, Incident, UptimeMetric
from app.notifications import dispatch_alerts
from app.redis_client import redis_client
from app.schemas import (
    RegisterRequest, LoginRequest, TokenResponse, MeResponse,
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
# Auth helpers / dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: validate Bearer JWT and return the User."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ", 1)[1]
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    result = await db.execute(select(User).where(User.id == payload.get("user_id")))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


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


# ---------------------------------------------------------------------------
# Authentication endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user. Returns a JWT and the user_key (store it!)."""
    # Check username not taken
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_jwt({"user_id": user.id, "user_key": user.user_key})
    return TokenResponse(token=token, user_key=user.user_key)


@app.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with username + password. Returns JWT and user_key."""
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_jwt({"user_id": user.id, "user_key": user.user_key})
    return TokenResponse(token=token, user_key=user.user_key)


@app.get("/auth/me", response_model=MeResponse)
async def auth_me(current_user: User = Depends(get_current_user)):
    """Return info about the logged-in user."""
    return current_user


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

@app.get("/api/v1/destinations", response_model=list[DestinationOut])
async def list_destinations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Destination)
        .where(Destination.user_key == current_user.user_key)
        .order_by(desc(Destination.created_at))
    )
    return result.scalars().all()


@app.post("/api/v1/destinations", response_model=DestinationOut, status_code=201)
async def create_destination(
    body: DestinationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dest = Destination(**body.model_dump(), user_key=current_user.user_key)
    db.add(dest)
    await db.commit()
    await db.refresh(dest)
    return dest


@app.put("/api/v1/destinations/{dest_id}", response_model=DestinationOut)
async def update_destination(
    dest_id: int,
    body: DestinationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Destination).where(
            Destination.id == dest_id,
            Destination.user_key == current_user.user_key,
        )
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Destination).where(
            Destination.id == dest_id,
            Destination.user_key == current_user.user_key,
        )
    )
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    await db.delete(dest)
    await db.commit()


# ---------------------------------------------------------------------------
# Agents  (require >= 1 destination before registering)
# ---------------------------------------------------------------------------

async def _require_destination(user_key: str, db: AsyncSession):
    """Guard: raise 403 if user has no destinations yet."""
    result = await db.execute(
        select(func.count())
        .select_from(Destination)
        .where(Destination.user_key == user_key)
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
        "user_key": agent.user_key,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent)
        .where(Agent.user_key == current_user.user_key)
        .order_by(desc(Agent.created_at))
    )
    return [_make_agent_out(a) for a in result.scalars().all()]


@app.post("/api/v1/agents", response_model=AgentCreateResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Guard: must have at least one destination
    await _require_destination(current_user.user_key, db)

    # Validate that all provided destination IDs belong to this user
    if body.destination_ids:
        result = await db.execute(
            select(func.count())
            .select_from(Destination)
            .where(
                Destination.id.in_(body.destination_ids),
                Destination.user_key == current_user.user_key,
            )
        )
        if result.scalar() != len(body.destination_ids):
            raise HTTPException(
                status_code=400,
                detail="One or more destination IDs are invalid or do not belong to you.",
            )

    # Generate HMAC key for this agent
    agent_id_str = f"{current_user.user_key[:8]}-{body.name.lower().replace(' ', '-')}"
    key_id = f"ak_{secrets.token_hex(16)}"
    key_secret = secrets.token_hex(32)
    key_hash = hashlib.sha256(key_secret.encode()).hexdigest()

    agent_key = AgentKey(
        key_id=key_id,
        key_hash=key_hash,
        agent_id=agent_id_str,
        user_key=current_user.user_key,
        is_active=True,
    )
    db.add(agent_key)
    await db.flush()

    agent = Agent(
        user_key=current_user.user_key,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.user_key == current_user.user_key,
        )
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.user_key == current_user.user_key,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()


# ---------------------------------------------------------------------------
# Monitoring — heartbeats and incidents (agent-facing)
# ---------------------------------------------------------------------------

async def record_uptime_probe(db: AsyncSession, target: str, is_up: bool, user_key: str | None = None):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(UptimeMetric).where(
            UptimeMetric.target == target,
            UptimeMetric.day == today,
            UptimeMetric.user_key == user_key,
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
            user_key=user_key,
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
    """Look up the user_key from the AgentKey associated with this agent_id."""
    result = await db.execute(
        select(AgentKey.user_key).where(AgentKey.agent_id == agent_id, AgentKey.is_active == True)
    )
    row = result.first()
    return row[0] if row else None


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
    user_key = await _resolve_user_key_from_agent(heartbeat.agent_id, db)
    await record_uptime_probe(db, heartbeat.target, is_up=True, user_key=user_key)
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
    user_key = await _resolve_user_key_from_agent(incident.agent_id, db)

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
        user_key=user_key,
    )
    db.add(db_incident)
    await db.commit()

    await record_uptime_probe(db, incident.target, is_up=False, user_key=user_key)

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Live status for this user's agents (filtered by user_key)."""
    result = await db.execute(
        select(AgentKey.agent_id).where(AgentKey.user_key == current_user.user_key)
    )
    user_agent_ids = {row[0] for row in result.all()}

    keys = await redis_client.keys("heartbeat:*")
    statuses = []
    for key in keys:
        raw = await redis_client.get(key)
        if raw:
            data = json.loads(raw)
            if not user_agent_ids or data.get("agent_id") in user_agent_ids:
                statuses.append(data)
    return {"statuses": statuses}


@app.get("/api/v1/incidents")
async def get_incidents(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent incidents belonging to this user."""
    result = await db.execute(
        select(Incident)
        .where(Incident.user_key == current_user.user_key)
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """7-day uptime statistics for this user's targets."""
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
            UptimeMetric.user_key == current_user.user_key,
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
