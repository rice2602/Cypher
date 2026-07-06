"""
probe.py — TCP connectivity probe with latency measurement.

Tries to open a TCP connection to (host, port) within the configured
timeout.  Returns whether the target was reachable and the measured
round-trip latency in milliseconds.

Uses only Python stdlib (socket + time) — no third-party libraries.
"""

import socket
import time
from typing import Tuple


def tcp_probe(host: str, port: int, timeout: int) -> Tuple[bool, float]:
    """
    Attempt a TCP connection to host:port.

    Args:
        host:    Hostname or IP address.
        port:    TCP port number.
        timeout: Connection timeout in seconds.

    Returns:
        (reachable, latency_ms)
        reachable  — True if the connection succeeded, False otherwise.
        latency_ms — Wall-clock milliseconds from connect start to
                     successful connection.  0.0 when unreachable.
    """
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency_ms = (time.perf_counter() - start) * 1000
            return True, round(latency_ms, 2)
    except OSError:
        return False, 0.0
