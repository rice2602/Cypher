"""
targets.py — Fetch agent targets from backend.

Backend is the single source of truth for which destinations to probe.
Falls back to TARGETS env var if backend is unreachable.
"""

import json
import logging
import socket
import urllib.request
import urllib.error
from typing import List, Optional

from agent.config import config

logger = logging.getLogger("cypher.agent.targets")


def _sign_request(body: bytes) -> dict:
    """Produce HMAC-SHA256 auth headers."""
    import hashlib
    import hmac
    import time

    if not config.AGENT_KEY_ID or not config.AGENT_KEY_SECRET:
        return {}

    timestamp = str(int(time.time()))
    key_hash = hashlib.sha256(config.AGENT_KEY_SECRET.encode("utf-8")).hexdigest()
    signature = hmac.new(
        key_hash.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()

    return {
        "X-Cypher-Key-Id": config.AGENT_KEY_ID,
        "X-Cypher-Signature": signature,
        "X-Cypher-Timestamp": timestamp,
    }


def fetch_targets_from_backend() -> Optional[List[str]]:
    """
    Fetch assigned targets from backend GET /api/v1/agent/targets.
    Returns list of "host:port" strings, or None on failure.
    """
    if not config.AGENT_KEY_ID:
        logger.debug("No AGENT_KEY_ID configured, cannot fetch targets from backend")
        return None

    url = f"{config.BACKEND_URL}/api/v1/agent/targets"
    req = urllib.request.Request(url, method="GET")
    headers = _sign_request(b"")
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            targets = data.get("targets", [])
            if targets:
                logger.info("Fetched %d targets from backend", len(targets))
                return targets
            else:
                logger.warning("Backend returned empty target list")
                return []
    except Exception as exc:
        logger.warning("Failed to fetch targets from backend: %s", exc)
        return None


def get_fallback_targets() -> List[str]:
    """Parse TARGETS env var as list of 'host:port' strings."""
    return [t.strip() for t in config.TARGETS.split(",") if t.strip()]


def resolve_targets() -> List[str]:
    """
    Get targets: try backend first, fall back to env var.
    Returns list of "host:port" strings.
    """
    backend_targets = fetch_targets_from_backend()
    if backend_targets is not None:
        return backend_targets
    logger.info("Using fallback targets from TARGETS env var")
    return get_fallback_targets()
