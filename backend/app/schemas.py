"""
schemas.py — Pydantic request/response models for Cypher v1.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from datetime import datetime


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    token: str
    type: str = "Bearer"
    user_key: str


class MeResponse(BaseModel):
    id: int
    username: str
    user_key: str
    created_at: datetime

    class Config:
        from_attributes = True


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
    user_key: str
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
    destination_ids: List[int] = Field(..., min_length=1,
                                       description="IDs of destinations this agent monitors. Must have at least one.")


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)
    destination_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None


class AgentOut(BaseModel):
    id: int
    user_key: str
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    destination_ids: List[int]
    key_id: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AgentCreateResponse(BaseModel):
    agent: AgentOut
    key_id: str
    key_secret: str   # Shown ONCE — store it safely


# ---------------------------------------------------------------------------
# Agent HMAC Key management (admin view)
# ---------------------------------------------------------------------------

class AgentKeyOut(BaseModel):
    key_id: str
    agent_id: str
    is_active: bool
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Monitoring data (heartbeats / incidents)
# ---------------------------------------------------------------------------

class Heartbeat(BaseModel):
    agent_id: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    status: Literal["UP"]
    latency_ms: int = Field(..., ge=0)


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
