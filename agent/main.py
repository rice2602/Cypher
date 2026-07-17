"""
main.py — Agent entry point.

Periodically fetches targets from backend, probes them, and reports results.
Backend is the source of truth for which destinations to monitor.
"""

import signal
import time
import sys

from agent.config import config
from agent.diagnostics import collect
from agent.probe import tcp_probe
from agent.sender import send_heartbeat, send_incident
from agent.targets import resolve_targets

_running = True
_agent_uid = None  # Set on first successful backend response or from env


def _shutdown(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global _running
    print(f"\n[agent] Received signal {signum}, shutting down...", flush=True)
    _running = False


def run() -> None:
    """Main probe loop — runs until interrupted."""
    global _agent_uid

    targets = resolve_targets()
    if not targets:
        print("[agent] No targets available. Set TARGETS env var or register agent in backend.", flush=True)
        sys.exit(1)

    _agent_uid = config.AGENT_KEY_ID or "local-agent"

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"Cypher Agent starting (uid={_agent_uid})", flush=True)
    print(f"Targets: {targets}", flush=True)
    print(f"Backend: {config.BACKEND_URL}", flush=True)
    print(f"Probe interval: {config.PROBE_INTERVAL}s", flush=True)
    print(f"Retry: {config.RETRY_COUNT} retries, {config.RETRY_DELAY}s delay", flush=True)

    last_fetch = time.time()

    try:
        while _running:
            # Periodically re-fetch targets from backend
            if time.time() - last_fetch >= config.TARGET_FETCH_INTERVAL:
                new_targets = resolve_targets()
                if new_targets != targets:
                    print(f"[agent] Targets updated: {new_targets}", flush=True)
                    targets = new_targets
                last_fetch = time.time()

            if not targets:
                print("[agent] No targets available, waiting...", flush=True)
                _sleep(config.PROBE_INTERVAL)
                continue

            for target in targets:
                if not _running:
                    break
                _probe_target(target)

            _sleep(config.PROBE_INTERVAL)
    finally:
        print("Agent stopped.", flush=True)


def _sleep(seconds: float) -> None:
    """Sleep in small increments so SIGTERM is responsive."""
    deadline = time.time() + seconds
    while _running and time.time() < deadline:
        time.sleep(min(1, deadline - time.time()))


def _probe_target(target: str) -> None:
    """Full probe cycle for one target with retry."""
    try:
        host, port_str = target.rsplit(":", 1)
        port = int(port_str)
    except ValueError:
        print(f"[probe] {target} — invalid format (expected host:port)", flush=True)
        return

    reachable = False
    latency_ms = 0.0

    for attempt in range(config.RETRY_COUNT + 1):
        reachable, latency_ms = tcp_probe(host, port, config.PROBE_TIMEOUT)
        if reachable:
            break
        if attempt < config.RETRY_COUNT:
            print(f"[probe] {target} attempt {attempt + 1}/{config.RETRY_COUNT + 1} failed, retrying in {config.RETRY_DELAY}s", flush=True)
            time.sleep(config.RETRY_DELAY)

    if reachable:
        print(f"[probe] {target}  UP  {latency_ms} ms", flush=True)
        send_heartbeat(_agent_uid, target, latency_ms)
    else:
        print(f"[probe] {target}  DOWN (after {config.RETRY_COUNT + 1} attempts)", flush=True)
        diag = collect(host, port, error="TCP connection failed")
        send_incident(_agent_uid, target, diag)


if __name__ == "__main__":
    run()
