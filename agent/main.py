"""
main.py — Agent entry point.

Starts the probe loop: periodically checks each configured target and
reports the result to the Cypher backend.
"""

import time
import sys

from agent.config import config
from agent.diagnostics import collect
from agent.probe import tcp_probe
from agent.sender import send_heartbeat, send_incident


def run() -> None:
    """Main probe loop — runs until interrupted."""
    targets = [t.strip() for t in config.TARGETS.split(",") if t.strip()]

    print(f"Cypher Agent starting (id={config.AGENT_ID})", flush=True)
    print(f"Targets: {targets}", flush=True)
    print(f"Backend: {config.BACKEND_URL}", flush=True)
    print(f"Probe interval: {config.PROBE_INTERVAL}s", flush=True)

    try:
        while True:
            for target in targets:
                _probe_target(target)
            time.sleep(config.PROBE_INTERVAL)
    except KeyboardInterrupt:
        print("\nAgent stopped.", flush=True)
        sys.exit(0)


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
        diag = collect(host, error="TCP connection failed")
        send_incident(config.AGENT_ID, target, diag)


if __name__ == "__main__":
    run()
