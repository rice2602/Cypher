"""
models.py — Database models for Cypher.

Destination: what to monitor.
Agent: registered monitoring agent (auto-assigned to all destinations by default).
Incident, UptimeMetric: monitoring data.
AgentKey: HMAC signing key per agent.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Text, DateTime, Boolean,
    UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Destinations — what to monitor
# ---------------------------------------------------------------------------

class Destination(Base):
    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="host")
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# Agents — registered monitoring agents
# ---------------------------------------------------------------------------

class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Backend-generated unique ID (e.g. "agent-a1b2c3d4")
    agent_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # JSON array of destination IDs. Empty = monitors all active destinations.
    destination_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Linked AgentKey.key_id
    key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Agent-reported metadata (updated with each heartbeat)
    metadata_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_uptime: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# Agent Keys — HMAC signing credentials
# ---------------------------------------------------------------------------

class AgentKey(Base):
    __tablename__ = "agent_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# Incidents — down events
# ---------------------------------------------------------------------------

class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DOWN")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ping_diagnostic: Mapped[str | None] = mapped_column(Text, nullable=True)
    dns_diagnostic: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_diagnostic: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceroute_diagnostic: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_diagnostic: Mapped[str | None] = mapped_column(Text, nullable=True)
    dns_verification_diagnostic: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Agent-reported metadata at time of incident
    agent_hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_region: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        Index("idx_incidents_target_created", "target", created_at.desc()),
        Index("idx_incidents_agent_uid", "agent_uid"),
    )


# ---------------------------------------------------------------------------
# Uptime Metrics
# ---------------------------------------------------------------------------

class UptimeMetric(Base):
    __tablename__ = "uptime_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    up_probes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_probes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("target", "day", name="uq_target_day"),
        Index("idx_uptime_metrics_target_day", "target", "day"),
    )
