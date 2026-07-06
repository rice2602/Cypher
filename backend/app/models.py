from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
