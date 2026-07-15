"""
main.py — Agent entry point.

Starts the probe loop: periodically checks each configured target and
reports the result to the Cypher backend.
"""

import signal
import time
import sys

from agent.config import config
from agent.diagnostics import collect
from agent.probe import tcp_probe
from agent.sender import send_heartbeat, send_incident

_running = True


def _shutdown(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global _running
    print(f"\n[agent] Received signal {signum}, shutting down...", flush=True)
    _running = False


def run() -> None:
    """Main probe loop — runs until interrupted."""
    targets = [t.strip() for t in config.TARGETS.split(",") if t.strip()]

    if not targets:
        print("[agent] No targets configured. Set TARGETS env var. Exiting.", flush=True)
        sys.exit(1)

    # Handle both SIGTERM (Docker stop) and SIGINT (Ctrl+C)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"Cypher Agent starting (id={config.AGENT_ID})", flush=True)
    print(f"Targets: {targets}", flush=True)
    print(f"Backend: {config.BACKEND_URL}", flush=True)
    print(f"Probe interval: {config.PROBE_INTERVAL}s", flush=True)

    try:
        while _running:
            for target in targets:
                if not _running:
                    break
                _probe_target(target)
            # Sleep in small increments so SIGTERM is responsive
            for _ in range(config.PROBE_INTERVAL):
                if not _running:
                    break
                time.sleep(1)
    finally:
        print("Agent stopped.", flush=True)


def _probe_target(target: str) -> None:
    """
    Full probe cycle for one target:
      1. Parse host:port
      2. TCP probe → measure latency
      3. UP  → send heartbeat
      4. DOWN → collect diagnostics → send incident
    """
    try:
        host, port_str = target.rsplit(":", 1)
        port = int(port_str)
    except ValueError:
        print(f"[probe] {target} — invalid format (expected host:port)", flush=True)
        return

    reachable, latency_ms = tcp_probe(host, port, config.PROBE_TIMEOUT)

    if reachable:
        print(f"[probe] {target}  UP  {latency_ms} ms", flush=True)
        send_heartbeat(config.AGENT_ID, target, latency_ms)
    else:
        print(f"[probe] {target}  DOWN", flush=True)
        diag = collect(host, port, error="TCP connection failed")
        send_incident(config.AGENT_ID, target, diag)


if __name__ == "__main__":
    run()
