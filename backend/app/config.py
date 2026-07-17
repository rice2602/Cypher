import os


class Settings:
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://cypher:cypher@localhost:5432/cypher"
    )

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # JWT signing secret
    JWT_SECRET: str = os.getenv("JWT_SECRET", "cypher-change-this-in-production")

    # Single-user mode — when True all auth checks are bypassed.
    SINGLE_USER_MODE: bool = os.getenv("SINGLE_USER_MODE", "true").lower() == "true"

    # Notifications (all optional)
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")
    TEAMS_WEBHOOK_URL: str = os.getenv("TEAMS_WEBHOOK_URL", "")
    PAGERDUTY_ROUTING_KEY: str = os.getenv("PAGERDUTY_ROUTING_KEY", "")
    GENERIC_WEBHOOK_URL: str = os.getenv("GENERIC_WEBHOOK_URL", "")

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))

    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

    # Heartbeat TTL multiplier: heartbeat keys expire after PROBE_INTERVAL * this
    HEARTBEAT_TTL_MULTIPLIER: int = int(os.getenv("HEARTBEAT_TTL_MULTIPLIER", "3"))

    # Default probe interval (used for staleness detection if agent doesn't report)
    DEFAULT_PROBE_INTERVAL: int = int(os.getenv("DEFAULT_PROBE_INTERVAL", "30"))


settings = Settings()
