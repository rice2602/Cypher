"""
verify_dashboard.py — Verify the Dashboard tasks against a running backend.

Checks:
  1. GET /status   — endpoint exists, returns {"statuses": [...]}
  2. GET /incidents — endpoint exists, returns {"incidents": [...]}
  3. GET /dashboard — serves HTML with expected landmark content
  4. /status reflects a heartbeat that was just posted
  5. /incidents reflects an incident that was just posted
  6. dashboard/index.html file exists and has required elements

Prerequisites:
  - Backend running at http://localhost:8000
  - Redis and PostgreSQL reachable by the backend

Usage:
    python verify_dashboard.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[bool] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    results.append(condition)
    mark = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{suffix}")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def get(path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return -1, str(e).encode()


def post_json(path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


# ── Test suites ───────────────────────────────────────────────────────────────

def test_backend_reachable() -> None:
    print("\n=== Backend health check ===")
    code, body = get("/")
    check("GET / returns 200", code == 200, f"status={code}")
    if code == 200:
        data = json.loads(body)
        check("health status is ok", data.get("status") == "ok")


def test_status_endpoint_shape() -> None:
    print("\n=== GET /status — endpoint shape ===")
    code, body = get("/status")
    check("GET /status returns 200", code == 200, f"status={code}")
    if code != 200:
        return
    data = json.loads(body)
    check("response has 'statuses' key", "statuses" in data)
    check("statuses is a list", isinstance(data.get("statuses"), list))


def test_incidents_endpoint_shape() -> None:
    print("\n=== GET /incidents — endpoint shape ===")
    code, body = get("/incidents")
    check("GET /incidents returns 200", code == 200, f"status={code}")
    if code != 200:
        return
    data = json.loads(body)
    check("response has 'incidents' key", "incidents" in data)
    check("incidents is a list", isinstance(data.get("incidents"), list))


def test_heartbeat_appears_in_status() -> None:
    print("\n=== Heartbeat -> /status round-trip ===")
    payload = {
        "agent_id": "verify-dash-agent",
        "target": "status-check.test:443",
        "status": "UP",
        "latency_ms": 7,
    }
    code, _ = post_json("/heartbeat", payload)
    check("POST /heartbeat accepted", code == 200, f"status={code}")
    time.sleep(0.3)

    code2, body2 = get("/status")
    check("GET /status succeeds after posting", code2 == 200)
    if code2 != 200:
        return
    data = json.loads(body2)
    entry = next(
        (s for s in data["statuses"]
         if s.get("agent_id") == "verify-dash-agent"
         and s.get("target") == "status-check.test:443"),
        None,
    )
    check("heartbeat appears in /status", entry is not None)
    if entry:
        check("status is UP", entry.get("status") == "UP")
        check("latency_ms is 7", entry.get("latency_ms") == 7)


def test_incident_appears_in_incidents() -> None:
    print("\n=== Incident -> /incidents round-trip ===")
    payload = {
        "agent_id": "verify-dash-agent",
        "target": "incident-check.test:80",
        "status": "DOWN",
        "latency_ms": None,
        "diagnostics": {
            "ping": "request timed out",
            "dns": "incident-check.test -> NXDOMAIN",
            "error": "TCP connection failed",
        },
    }
    code, _ = post_json("/incident", payload)
    check("POST /incident accepted", code == 200, f"status={code}")
    time.sleep(0.3)

    code2, body2 = get("/incidents")
    check("GET /incidents succeeds after posting", code2 == 200)
    if code2 != 200:
        return
    data = json.loads(body2)
    entry = next(
        (i for i in data["incidents"]
         if i.get("agent_id") == "verify-dash-agent"
         and i.get("target") == "incident-check.test:80"),
        None,
    )
    check("incident appears in /incidents", entry is not None)
    if entry:
        check("status is DOWN", entry.get("status") == "DOWN")
        check("ping field present", bool(entry.get("ping")))
        check("dns field present", bool(entry.get("dns")))
        check("error field present", bool(entry.get("error")))
        check("created_at field present", bool(entry.get("created_at")))


def test_dashboard_html() -> None:
    print("\n=== GET /dashboard — HTML content ===")
    code, body = get("/dashboard")
    check("GET /dashboard returns 200", code == 200, f"status={code}")
    if code != 200:
        return
    html = body.decode("utf-8", errors="replace")
    check("title tag present", "<title>" in html)
    check("Cypher branding present", "Cypher" in html)
    check("fetch('/status') in script", "fetch('/status')" in html)
    check("fetch('/incidents') in script", "fetch('/incidents')" in html)
    check("auto-refresh interval present", "setInterval" in html)
    check("status table rendered dynamically", "renderStatus" in html)
    check("incident table rendered dynamically", "renderIncidents" in html)


def test_dashboard_file_exists() -> None:
    print("\n=== dashboard/index.html — file structure ===")
    import os  # noqa: PLC0415
    path = "dashboard/index.html"
    check("dashboard/index.html exists", os.path.isfile(path))
    if os.path.isfile(path):
        content = open(path, encoding="utf-8").read()
        check("file has DOCTYPE", "<!DOCTYPE html>" in content)
        check("file has meta description", 'name="description"' in content)
        check("auto-refresh constant defined", "REFRESH_INTERVAL" in content)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    test_backend_reachable()
    test_status_endpoint_shape()
    test_incidents_endpoint_shape()
    test_heartbeat_appears_in_status()
    test_incident_appears_in_incidents()
    test_dashboard_html()
    test_dashboard_file_exists()

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
