"""
sender.py — Backend API reporter with retry and metadata.

Sends heartbeat (UP) and incident (DOWN) payloads to the Cypher
backend API. Includes configurable retry and agent metadata.
"""

import hashlib
import hmac
import json
import logging
import platform
import time
import traceback
import urllib.request
import urllib.error
from typing import Dict, Optional

from agent.config import config

logger = logging.getLogger("cypher.agent.sender")

# Track agent start time for uptime reporting
_start_time = time.time()


def _get_metadata() -> dict:
    """Build agent metadata for heartbeat payloads."""
    return {
        "version": config.AGENT_VERSION,
        "hostname": platform.node() or "unknown",
        "region": config.AGENT_REGION or "unknown",
        "uptime": int(time.time() - _start_time),
    }


def _sign_request(body: bytes) -> dict:
    """Produce HMAC-SHA256 authentication headers."""
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


def _post_with_retry(url: str, payload: dict) -> bool:
    """HTTP POST with configurable retry. Returns True on success."""
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    headers.update(_sign_request(data))

    for attempt in range(config.RETRY_COUNT + 1):
        req = urllib.request.Request(
            url, data=data, headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
                return True
        except Exception as exc:
            if attempt < config.RETRY_COUNT:
                logger.warning("POST %s attempt %d/%d failed: %s — retrying in %.1fs",
                               url, attempt + 1, config.RETRY_COUNT + 1, exc, config.RETRY_DELAY)
                time.sleep(config.RETRY_DELAY)
            else:
                logger.error("POST %s failed after %d attempts: %s\n%s",
                             url, config.RETRY_COUNT + 1, exc, traceback.format_exc())
    return False


def send_heartbeat(agent_id: str, target: str, latency_ms: float) -> bool:
    """Report a successful probe. Returns True on success."""
    payload = {
        "agent_id": agent_id,
        "target": target,
        "status": "UP",
        "latency_ms": int(latency_ms),
        "metadata": _get_metadata(),
    }
    return _post_with_retry(f"{config.BACKEND_URL}/heartbeat", payload)


def send_incident(agent_id: str, target: str, diagnostics: Dict[str, str]) -> bool:
    """Report a failed probe. Returns True on success."""
    payload = {
        "agent_id": agent_id,
        "target": target,
        "status": "DOWN",
        "latency_ms": None,
        "diagnostics": diagnostics,
        "metadata": _get_metadata(),
    }
    return _post_with_retry(f"{config.BACKEND_URL}/incident", payload)
