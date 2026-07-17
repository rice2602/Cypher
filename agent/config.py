"""
config.py — Agent configuration.

All values are read from environment variables with sensible defaults.
Backend is the source of truth for targets; TARGETS env var is fallback only.
"""

import os


class AgentConfig:
    # Backend API base URL (no trailing slash).
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

    # Agent HMAC key credentials (required for backend auth)
    AGENT_KEY_ID: str = os.getenv("AGENT_KEY_ID", "")
    AGENT_KEY_SECRET: str = os.getenv("AGENT_KEY_SECRET", "")

    # Fallback targets (only used if backend fetch fails)
    TARGETS: str = os.getenv("TARGETS", "google.com:443")

    # How often to run probes, in seconds.
    PROBE_INTERVAL: int = max(1, int(os.getenv("PROBE_INTERVAL", "30")))

    # TCP connection timeout per probe, in seconds.
    PROBE_TIMEOUT: int = max(1, int(os.getenv("PROBE_TIMEOUT", "5")))

    # Retry config
    RETRY_COUNT: int = max(0, int(os.getenv("RETRY_COUNT", "3")))
    RETRY_DELAY: float = max(0.1, float(os.getenv("RETRY_DELAY", "2")))

    # How often to re-fetch targets from backend (seconds)
    TARGET_FETCH_INTERVAL: int = max(10, int(os.getenv("TARGET_FETCH_INTERVAL", "60")))

    # Agent identity metadata
    AGENT_REGION: str = os.getenv("AGENT_REGION", "")
    AGENT_VERSION: str = "2.0.0"


config = AgentConfig()
