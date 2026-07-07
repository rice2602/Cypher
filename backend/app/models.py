"""
models.py — Database models for Cypher v1.

User model: username + hashed_password + user_key (tenant identifier).
Destination: what to monitor.
Agent: registered monitoring agent (requires >= 1 destination).
Incident, UptimeMetric: existing monitoring data.
AgentKey: HMAC signing key per agent.
"""

import secrets
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Text, DateTime, ForeignKey, Boolean,
    UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Login identity
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Tenant key — used as the owner FK on all resources.
    # Never exposed in URLs; returned once at registration and stored in JWT.
    user_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: secrets.token_hex(24)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# Destinations — what the user wants to monitor
# ---------------------------------------------------------------------------

class Destination(Base):
    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Owner
    user_key: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_key", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Type: host | url | subnet | vmware | custom
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="host")

    # Optional details
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

    # Owner
    user_key: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_key", ondelete="CASCADE"),
        nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # JSON array of destination IDs this agent is assigned to monitor
    destination_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Linked AgentKey.key_id — set after agent key is auto-generated on creation
    key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    # The agent_id string used in heartbeats/incidents
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Owner
    user_key: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_key", ondelete="SET NULL"),
        nullable=True, index=True
    )

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
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
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

    # Owner (nullable for backward compat with old incidents)
    user_key: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_key", ondelete="SET NULL"),
        nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
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

    # Owner (nullable for backward compat)
    user_key: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_key", ondelete="SET NULL"),
        nullable=True, index=True
    )

    __table_args__ = (
        UniqueConstraint("target", "day", "user_key", name="uq_target_day_user"),
    )
