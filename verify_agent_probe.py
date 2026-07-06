"""
verify_agent_probe.py — Verify the TCP probe + latency measurement task.

Tests tcp_probe() against:
  - A port that is definitely open     (localhost:port we bind ourselves)
  - A port that is definitely closed   (refused connection)
  - A host that times out              (non-routable address)
  - The _probe_target() integration in main.py

No backend, Redis, or PostgreSQL required.

Usage:
    python verify_agent_probe.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.abspath("."))

from agent.probe import tcp_probe  # noqa: E402

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[bool] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    results.append(condition)
    mark = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{suffix}")


# ---------------------------------------------------------------------------
# Helper: start a real TCP listener on a random port so we can probe it
# ---------------------------------------------------------------------------

def _start_listener() -> tuple[int, threading.Event]:
    """Bind a TCP socket on localhost, accept one connection, then close."""
    stop = threading.Event()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(1)
    srv.settimeout(5)

    def _accept():
        try:
            conn, _ = srv.accept()
            conn.close()
        except OSError:
            pass
        finally:
            srv.close()
            stop.set()

    threading.Thread(target=_accept, daemon=True).start()
    return port, stop


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_reachable() -> None:
    print("\n=== Reachable target (localhost listener) ===")
    port, stop = _start_listener()
    time.sleep(0.05)  # let listener settle

    reachable, latency_ms = tcp_probe("127.0.0.1", port, timeout=3)

    check("reachable is True", reachable is True)
    check("latency_ms is a float", isinstance(latency_ms, float))
    check("latency_ms >= 0", latency_ms >= 0.0, f"{latency_ms} ms")
    check("latency_ms < 2000 ms (sane upper bound)", latency_ms < 2000.0, f"{latency_ms} ms")

    stop.wait(timeout=1)


def test_refused() -> None:
    print("\n=== Unreachable target (connection refused) ===")
    # Bind and immediately close to get a port that will refuse connections
    tmp = socket.socket()
    tmp.bind(("127.0.0.1", 0))
    port = tmp.getsockname()[1]
    tmp.close()

    reachable, latency_ms = tcp_probe("127.0.0.1", port, timeout=3)

    check("reachable is False", reachable is False)
    check("latency_ms is 0.0", latency_ms == 0.0, f"got {latency_ms}")


def test_timeout() -> None:
    print("\n=== Timeout target (non-routable address) ===")
    # 192.0.2.x is TEST-NET-1 (RFC 5737) — guaranteed non-routable
    start = time.perf_counter()
    reachable, latency_ms = tcp_probe("192.0.2.1", 9999, timeout=1)
    elapsed = time.perf_counter() - start

    check("reachable is False", reachable is False)
    check("latency_ms is 0.0", latency_ms == 0.0, f"got {latency_ms}")
    check("probe respected timeout (elapsed < 3s)", elapsed < 3.0, f"{elapsed:.2f}s")


def test_probe_target_integration() -> None:
    print("\n=== _probe_target() integration (stdout output) ===")
    import io
    from contextlib import redirect_stdout
    from agent.main import _probe_target  # noqa: PLC0415

    # Reachable path — bind a listener
    port, stop = _start_listener()
    time.sleep(0.05)

    buf = io.StringIO()
    with redirect_stdout(buf):
        _probe_target(f"127.0.0.1:{port}")
    output = buf.getvalue()
    stop.wait(timeout=1)

    check("UP printed for reachable target", "UP" in output, repr(output.strip()))
    check("ms latency present in UP output", "ms" in output)

    # Down path — refused port
    tmp = socket.socket()
    tmp.bind(("127.0.0.1", 0))
    closed_port = tmp.getsockname()[1]
    tmp.close()

    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        _probe_target(f"127.0.0.1:{closed_port}")
    output2 = buf2.getvalue()
    check("DOWN printed for refused target", "DOWN" in output2, repr(output2.strip()))

    # Invalid format
    buf3 = io.StringIO()
    with redirect_stdout(buf3):
        _probe_target("no-port-here")
    output3 = buf3.getvalue()
    check("invalid format error message", "invalid" in output3.lower(), repr(output3.strip()))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    test_reachable()
    test_refused()
    test_timeout()
    test_probe_target_integration()

    print()
    if all(results):
        print("All checks passed.")
        sys.exit(0)
    else:
        failed = sum(1 for r in results if not r)
        print(f"{failed} check(s) FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
