"""
verify_agent_sender.py — Verify heartbeat sender, diagnostics, incident sender,
and the full probe→report loop.

Uses a real stdlib HTTP server on localhost to capture POSTed payloads —
no mocks, no external services, no backend required.

Usage:
    python verify_agent_sender.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import http.server
import json
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.abspath("."))

# Override backend URL to point at our capture server before importing sender
os.environ["BACKEND_URL"] = "http://127.0.0.1:19876"
os.environ["AGENT_ID"] = "test-agent"

from agent.diagnostics import collect, run_dns, run_ping  # noqa: E402
from agent.sender import send_heartbeat, send_incident     # noqa: E402
from agent.main import _probe_target                       # noqa: E402

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[bool] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    results.append(condition)
    mark = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{suffix}")


# ---------------------------------------------------------------------------
# Minimal HTTP capture server
# ---------------------------------------------------------------------------

captured: list[dict] = []


class _CaptureHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        captured.append({"path": self.path, "body": json.loads(body)})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *_):
        pass  # suppress access log noise


def _start_capture_server(port: int = 19876) -> threading.Thread:
    server = http.server.HTTPServer(("127.0.0.1", port), _CaptureHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)  # let server bind
    return t


# ---------------------------------------------------------------------------
# Helper: real listener so probe sees UP
# ---------------------------------------------------------------------------

def _open_listener() -> tuple[int, threading.Event]:
    stop = threading.Event()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(5)
    srv.settimeout(3)

    def _serve():
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                break
        srv.close()

    threading.Thread(target=_serve, daemon=True).start()
    return port, stop


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def test_diagnostics() -> None:
    print("\n=== diagnostics.run_ping / run_dns / collect ===")

    ping_result = run_ping("127.0.0.1")
    check("run_ping returns a non-empty string", bool(ping_result), repr(ping_result))
    check("run_ping result is a string", isinstance(ping_result, str))

    dns_result = run_dns("localhost")
    check("run_dns returns a non-empty string", bool(dns_result), repr(dns_result))
    check("run_dns result is a string", isinstance(dns_result, str))

    diag = collect("localhost", error="test error")
    check("collect returns dict with 3 keys", set(diag.keys()) == {"ping", "dns", "error"})
    check("collect error field is propagated", diag["error"] == "test error")
    check("collect ping field is a string", isinstance(diag["ping"], str))
    check("collect dns field is a string", isinstance(diag["dns"], str))


def test_send_heartbeat() -> None:
    print("\n=== sender.send_heartbeat ===")
    captured.clear()

    send_heartbeat("test-agent", "example.com:443", 12.5)
    time.sleep(0.1)

    check("heartbeat POST was sent", len(captured) == 1, f"captured={len(captured)}")
    if not captured:
        return

    req = captured[0]
    check("path is /heartbeat", req["path"] == "/heartbeat", req["path"])
    body = req["body"]
    check("agent_id matches", body.get("agent_id") == "test-agent")
    check("target matches", body.get("target") == "example.com:443")
    check("status is UP", body.get("status") == "UP")
    check("latency_ms is int", isinstance(body.get("latency_ms"), int))
    check("latency_ms value is 12", body.get("latency_ms") == 12, str(body.get("latency_ms")))


def test_send_incident() -> None:
    print("\n=== sender.send_incident ===")
    captured.clear()

    diag = {"ping": "request timed out", "dns": "failed", "error": "TCP timeout"}
    send_incident("test-agent", "bad-host:80", diag)
    time.sleep(0.1)

    check("incident POST was sent", len(captured) == 1, f"captured={len(captured)}")
    if not captured:
        return

    req = captured[0]
    check("path is /incident", req["path"] == "/incident", req["path"])
    body = req["body"]
    check("agent_id matches", body.get("agent_id") == "test-agent")
    check("target matches", body.get("target") == "bad-host:80")
    check("status is DOWN", body.get("status") == "DOWN")
    check("latency_ms is null", body.get("latency_ms") is None)
    d = body.get("diagnostics", {})
    check("diagnostics.ping matches", d.get("ping") == "request timed out")
    check("diagnostics.dns matches", d.get("dns") == "failed")
    check("diagnostics.error matches", d.get("error") == "TCP timeout")


def test_full_loop_up() -> None:
    print("\n=== Full loop — UP path ===")
    captured.clear()

    # Start a real listener so tcp_probe returns True
    port, stop = _open_listener()
    time.sleep(0.05)

    _probe_target(f"127.0.0.1:{port}")
    time.sleep(0.2)
    stop.set()

    check("heartbeat POST sent on UP", len(captured) >= 1)
    if captured:
        body = captured[0]["body"]
        check("UP path sends to /heartbeat", captured[0]["path"] == "/heartbeat")
        check("UP body status is UP", body.get("status") == "UP")
        check("UP body has latency_ms >= 0", isinstance(body.get("latency_ms"), int) and body["latency_ms"] >= 0)


def test_full_loop_down() -> None:
    print("\n=== Full loop — DOWN path ===")
    captured.clear()

    # Use a port that is definitely not listening (bind+close pattern)
    tmp = socket.socket()
    tmp.bind(("127.0.0.1", 0))
    port = tmp.getsockname()[1]
    tmp.close()

    _probe_target(f"127.0.0.1:{port}")
    time.sleep(0.5)

    check("incident POST sent on DOWN", len(captured) >= 1)
    if captured:
        body = captured[0]["body"]
        check("DOWN path sends to /incident", captured[0]["path"] == "/incident")
        check("DOWN body status is DOWN", body.get("status") == "DOWN")
        diag = body.get("diagnostics", {})
        check("DOWN body has diagnostics.ping", bool(diag.get("ping")))
        check("DOWN body has diagnostics.dns", bool(diag.get("dns")))
        check("DOWN body has diagnostics.error", bool(diag.get("error")))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _start_capture_server()

    test_diagnostics()
    test_send_heartbeat()
    test_send_incident()
    test_full_loop_up()
    test_full_loop_down()

    print()
    if all(results):
        print(f"All {len(results)} checks passed.")
        sys.exit(0)
    else:
        failed = sum(1 for r in results if not r)
        print(f"{failed}/{len(results)} check(s) FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
