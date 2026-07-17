"""
schemas.py — Pydantic request/response models for Cypher.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from datetime import datetime


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

DESTINATION_TYPES = Literal["host", "url", "subnet", "vmware", "custom"]


class DestinationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1, max_length=500)
    type: DESTINATION_TYPES = "host"
    port: Optional[int] = Field(None, ge=1, le=65535)
    description: Optional[str] = None
    tags: Optional[str] = None
    is_active: bool = True


class DestinationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[str] = Field(None, min_length=1, max_length=500)
    type: Optional[DESTINATION_TYPES] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    description: Optional[str] = None
    tags: Optional[str] = None
    is_active: Optional[bool] = None


class DestinationOut(BaseModel):
    id: int
    name: str
    url: str
    type: str
    port: Optional[int] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)
    # Empty/omitted = auto-assign to all active destinations
    destination_ids: Optional[List[int]] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)
    destination_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None


class AgentOut(BaseModel):
    id: int
    name: str
    agent_uid: str
    description: Optional[str] = None
    location: Optional[str] = None
    destination_ids: List[int]
    key_id: Optional[str] = None
    metadata_version: Optional[str] = None
    metadata_hostname: Optional[str] = None
    metadata_region: Optional[str] = None
    metadata_uptime: Optional[int] = None
    is_active: bool
    last_seen: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentCreateResponse(BaseModel):
    agent: AgentOut
    key_id: str
    key_secret: str


class AgentTargetsResponse(BaseModel):
    """Response for agent target fetch."""
    targets: List[str]  # list of "host:port" strings


# ---------------------------------------------------------------------------
# Monitoring data (heartbeats / incidents)
# ---------------------------------------------------------------------------

class AgentMetadata(BaseModel):
    """Optional metadata sent with heartbeats."""
    version: Optional[str] = None
    hostname: Optional[str] = None
    region: Optional[str] = None
    uptime: Optional[int] = None  # seconds since agent start


class Heartbeat(BaseModel):
    agent_id: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    status: Literal["UP"]
    latency_ms: int = Field(..., ge=0)
    metadata: Optional[AgentMetadata] = None


class Diagnostics(BaseModel):
    ping: str
    dns: str
    error: str
    traceroute: Optional[str] = None
    http: Optional[str] = None
    dns_verification: Optional[str] = None


class IncidentCreate(BaseModel):
    agent_id: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    status: Literal["DOWN"]
    latency_ms: None = None
    diagnostics: Diagnostics
    metadata: Optional[AgentMetadata] = None


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

class AgentProbeStatus(BaseModel):
    """Single agent's probe status for a target."""
    agent_uid: str
    agent_name: str
    status: str  # UP, DOWN, STALE
    latency_ms: Optional[int] = None
    last_seen: Optional[str] = None
    region: Optional[str] = None
    hostname: Optional[str] = None


class TargetStatus(BaseModel):
    """Aggregated status for one target."""
    target: str
    status: str  # UP, DEGRADED, DOWN, STALE, UNKNOWN
    agent_count: int
    agents_up: int
    agents_down: int
    agents_stale: int
    avg_latency_ms: Optional[float] = None
    last_seen: Optional[str] = None
    is_stale: bool = False
    agent_details: List[AgentProbeStatus]
