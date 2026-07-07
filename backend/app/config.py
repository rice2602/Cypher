import os


class Settings:
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://cypher:cypher@localhost:5432/cypher"
    )

    # Redis (use Upstash REDIS_URL in production)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # JWT signing secret — set a strong random value in production
    JWT_SECRET: str = os.getenv("JWT_SECRET", "cypher-change-this-in-production")

    # Notifications (all optional)
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")
    TEAMS_WEBHOOK_URL: str = os.getenv("TEAMS_WEBHOOK_URL", "")
    PAGERDUTY_ROUTING_KEY: str = os.getenv("PAGERDUTY_ROUTING_KEY", "")
    GENERIC_WEBHOOK_URL: str = os.getenv("GENERIC_WEBHOOK_URL", "")

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))

    # CORS allowed origins (comma-separated). "*" allows all in dev.
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")


settings = Settings()
