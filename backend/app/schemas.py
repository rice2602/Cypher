from pydantic import BaseModel, Field
from typing import Literal

class Heartbeat(BaseModel):
    agent_id: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    status: Literal["UP"]
    latency_ms: int = Field(..., ge=0)

class Diagnostics(BaseModel):
    ping: str
    dns: str
    error: str

class IncidentCreate(BaseModel):
    agent_id: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    status: Literal["DOWN"]
    latency_ms: None = None
    diagnostics: Diagnostics
