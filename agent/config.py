"""
config.py — Agent configuration.

All values are read from environment variables with sensible defaults
so the agent can run with zero configuration during development.
"""

import os


class AgentConfig:
    # Unique identifier for this agent instance.
    AGENT_ID: str = os.getenv("AGENT_ID", "agent-01")

    # Comma-separated list of host:port pairs to probe.
    # Example: "google.com:443,8.8.8.8:53"
    TARGETS: str = os.getenv("TARGETS", "google.com:443")

    # Backend API base URL (no trailing slash).
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

    # How often to run probes, in seconds.
    PROBE_INTERVAL: int = int(os.getenv("PROBE_INTERVAL", "30"))

    # TCP connection timeout per probe, in seconds.
    PROBE_TIMEOUT: int = int(os.getenv("PROBE_TIMEOUT", "5"))

    # Agent enrollment key credentials (optional — if blank, requests are unsigned).
    AGENT_KEY_ID: str = os.getenv("AGENT_KEY_ID", "")
    AGENT_KEY_SECRET: str = os.getenv("AGENT_KEY_SECRET", "")


config = AgentConfig()
