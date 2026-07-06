"""
sender.py — Backend API reporter.

Sends heartbeat (UP) and incident (DOWN) payloads to the Cypher
backend API.  Errors are logged and swallowed so a transient backend
outage never crashes the agent probe loop.

Uses only Python stdlib (urllib + json) — no third-party libs.
"""

import json
import urllib.request
import urllib.error
from typing import Dict

from agent.config import config


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_heartbeat(agent_id: str, target: str, latency_ms: float) -> None:
    """
    Report a successful probe to POST /heartbeat.

    Args:
        agent_id:   Unique agent identifier from config.
        target:     The probed target string (e.g. "google.com:443").
        latency_ms: Measured TCP connection latency (float → cast to int).
    """
    payload = {
        "agent_id": agent_id,
        "target": target,
        "status": "UP",
        "latency_ms": int(latency_ms),
    }
    _post(f"{config.BACKEND_URL}/heartbeat", payload)


def send_incident(agent_id: str, target: str, diagnostics: Dict[str, str]) -> None:
    """
    Report a failed probe to POST /incident.

    Args:
        agent_id:    Unique agent identifier from config.
        target:      The probed target string (e.g. "google.com:443").
        diagnostics: {"ping": str, "dns": str, "error": str}
    """
    payload = {
        "agent_id": agent_id,
        "target": target,
        "status": "DOWN",
        "latency_ms": None,
        "diagnostics": diagnostics,
    }
    _post(f"{config.BACKEND_URL}/incident", payload)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _post(url: str, payload: dict) -> None:
    """HTTP POST payload as JSON. Logs and suppresses all errors."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as exc:
        print(f"[sender] POST {url} failed: {exc}", flush=True)
