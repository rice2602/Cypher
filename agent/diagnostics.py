"""
diagnostics.py — Automatic diagnostics collector.

Called when a TCP probe fails.  Collects ping and DNS results to
help engineers understand why a target went DOWN without logging in
to run the commands manually.

Uses only Python stdlib (subprocess + socket) — no third-party libs.
"""

import socket
import subprocess
import sys
from typing import Dict


def run_ping(host: str) -> str:
    """
    Send a single ICMP ping to host and return a one-line summary.

    Uses platform-appropriate flags:
      Windows  — ping -n 1 -w 1000
      Linux    — ping -c 1 -W 1
    """
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", "1000", host]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", host]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout + result.stderr).strip()
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        return lines[-1] if lines else "no output"
    except subprocess.TimeoutExpired:
        return "ping timed out"
    except FileNotFoundError:
        return "ping command not found"
    except Exception as exc:
        return f"ping error: {exc}"


def run_dns(host: str) -> str:
    """
    Resolve host to IP addresses and return a compact summary string.
    Example: "google.com -> 142.250.185.46, 2607:f8b0:4004:c09::65"
    """
    try:
        results = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        addrs = sorted({r[4][0] for r in results})
        return f"{host} -> {', '.join(addrs)}"
    except socket.gaierror as exc:
        return f"dns failed: {exc}"
    except Exception as exc:
        return f"dns error: {exc}"


def collect(host: str, error: str = "TCP connection failed") -> Dict[str, str]:
    """
    Collect all diagnostics for a failed target.

    Args:
        host:  The hostname (no port) extracted from the target string.
        error: Short description of the original failure reason.

    Returns:
        {"ping": ..., "dns": ..., "error": ...}
    """
    return {
        "ping": run_ping(host),
        "dns": run_dns(host),
        "error": error,
    }
