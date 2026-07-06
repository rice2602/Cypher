from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import pathlib
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.redis_client import redis_client
from app.schemas import Heartbeat, IncidentCreate
from app.database import engine, get_db
from app.models import Base, Incident
from app.notifications import send_telegram_notification

_DASHBOARD = pathlib.Path(__file__).parent.parent.parent / "dashboard" / "index.html"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables in PostgreSQL on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await redis_client.aclose()

app = FastAPI(title="Cypher Backend API", lifespan=lifespan)

@app.get("/")
async def health_check():
    try:
        await redis_client.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    return {
        "status": "ok",
        "redis": redis_status
    }

@app.post("/heartbeat")
async def receive_heartbeat(heartbeat: Heartbeat):
    # Prepare payload with received timestamp
    data = heartbeat.model_dump()
    data["received_at"] = datetime.now(timezone.utc).isoformat()
    
    # Store in Redis
    key = f"heartbeat:{heartbeat.agent_id}:{heartbeat.target}"
    await redis_client.set(key, json.dumps(data))
    
    return {"status": "ok"}

@app.post("/incident")
async def receive_incident(
    incident: IncidentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # Store incident in PostgreSQL
    db_incident = Incident(
        agent_id=incident.agent_id,
        target=incident.target,
        status=incident.status,
        latency_ms=None,
        ping_diagnostic=incident.diagnostics.ping,
        dns_diagnostic=incident.diagnostics.dns,
        error_diagnostic=incident.diagnostics.error
    )
    db.add(db_incident)
    await db.commit()

    # Update latest status in Redis
    redis_key = f"heartbeat:{incident.agent_id}:{incident.target}"
    redis_data = incident.model_dump()
    redis_data["received_at"] = datetime.now(timezone.utc).isoformat()
    await redis_client.set(redis_key, json.dumps(redis_data))

    # Trigger Telegram notification in background
    message = (
        f"\U0001f6a8 <b>Cypher Incident Detected</b> \U0001f6a8\n\n"
        f"<b>Agent:</b> {incident.agent_id}\n"
        f"<b>Target:</b> {incident.target}\n"
        f"<b>Status:</b> DOWN\n\n"
        f"<b>Diagnostics:</b>\n"
        f"\u2022 <b>Ping:</b> {incident.diagnostics.ping}\n"
        f"\u2022 <b>DNS:</b> {incident.diagnostics.dns}\n"
        f"\u2022 <b>Error:</b> {incident.diagnostics.error}"
    )
    background_tasks.add_task(send_telegram_notification, message)

    return {"status": "ok"}

@app.get("/status")
async def get_status():
    """Return live status for all known agent:target pairs from Redis."""
    keys = await redis_client.keys("heartbeat:*")
    statuses = []
    for key in keys:
        raw = await redis_client.get(key)
        if raw:
            statuses.append(json.loads(raw))
    return {"statuses": statuses}

@app.get("/incidents")
async def get_incidents(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Return the most recent incidents from PostgreSQL."""
    result = await db.execute(
        select(Incident).order_by(desc(Incident.created_at)).limit(limit)
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
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in rows
        ]
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the Cypher dashboard HTML."""
    return _DASHBOARD.read_text(encoding="utf-8")
