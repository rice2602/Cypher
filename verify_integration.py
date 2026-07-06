"""
verify_integration.py — Integration, Failure Simulation, and Recovery Tests for Cypher.

This script automates:
1. Spinning up the Cypher FastAPI backend on a test port (8009).
2. Starting a local mock TCP target server.
3. Starting the Cypher agent targeting the mock TCP server.
4. Performing 3 testing stages:
   - Phase 1: Local integration test (verifies UP status is recorded).
   - Phase 2: Failure simulation (stops target, verifies DOWN status + diagnostics).
   - Phase 3: Recovery test (restarts target, verifies recovery to UP).
5. Clean cleanup of all spawned subprocesses.
"""

import os
import sys
import time
import json
import socket
import threading
import subprocess
import urllib.request
import urllib.error
import redis
import asyncpg
import asyncio

# Port configurations
TEST_BACKEND_PORT = 8009
MOCK_TARGET_PORT = 12345
TEST_AGENT_ID = "integration-test-agent"
TEST_TARGET = f"127.0.0.1:{MOCK_TARGET_PORT}"

# Terminal Colors
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

class MockTCPTarget:
    def __init__(self, host="127.0.0.1", port=MOCK_TARGET_PORT):
        self.host = host
        self.port = port
        self.sock = None
        self.thread = None
        self.running = False

    def start(self):
        print(f"Starting mock TCP target on {self.host}:{self.port}...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        self.running = True
        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()

    def _accept_loop(self):
        while self.running:
            try:
                self.sock.settimeout(0.2)
                conn, addr = self.sock.accept()
                conn.close()
            except socket.timeout:
                continue
            except Exception:
                break

    def stop(self):
        print("Stopping mock TCP target...")
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self.thread:
            self.thread.join(timeout=2)
        print("Mock TCP target stopped.")

def make_request(url, data=None, method="GET"):
    req = urllib.request.Request(url, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
        encoded_data = json.dumps(data).encode("utf-8")
    else:
        encoded_data = None
    try:
        with urllib.request.urlopen(req, data=encoded_data, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None
    except Exception as e:
        print(f"Request connection error to {url}: {e}")
        return None, None

async def check_postgres_incident():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/cypher")
    try:
        rows = await conn.fetch(
            "SELECT * FROM incidents WHERE agent_id = $1 AND target = $2 ORDER BY id DESC LIMIT 1;",
            TEST_AGENT_ID, TEST_TARGET
        )
        if not rows:
            return None
        return dict(rows[0])
    finally:
        await conn.close()

def main():
    print("=" * 60)
    print("CYPHER INTEGRATION, FAILURE SIMULATION & RECOVERY TEST")
    print("=" * 60)

    # 1. Start FastAPI backend
    venv_python = os.path.abspath(".venv/Scripts/python")
    backend_env = os.environ.copy()
    backend_env["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/cypher"
    backend_env["REDIS_URL"] = "redis://localhost:6379/0"

    print("Starting FastAPI backend...")
    backend_proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(TEST_BACKEND_PORT)],
        cwd="backend",
        env=backend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for backend to be ready
    time.sleep(3)
    
    # Check if backend successfully started
    if backend_proc.poll() is not None:
        print("Backend failed to start. Logs:")
        out, err = backend_proc.communicate()
        print("STDOUT:", out)
        print("STDERR:", err)
        sys.exit(1)

    # Validate health endpoint
    status_code, health = make_request(f"http://127.0.0.1:{TEST_BACKEND_PORT}/")
    if status_code != 200 or health.get("status") != "ok":
        print(f"Backend health check failed: {health}")
        backend_proc.terminate()
        sys.exit(1)
    print(f"Backend started successfully and healthy on port {TEST_BACKEND_PORT}.")

    # Clear existing Redis status for this target
    r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    r.delete(f"heartbeat:{TEST_AGENT_ID}:{TEST_TARGET}")

    # 2. Start Mock Target
    mock_target = MockTCPTarget()
    mock_target.start()

    # 3. Start Agent targeting mock target
    agent_env = os.environ.copy()
    agent_env["AGENT_ID"] = TEST_AGENT_ID
    agent_env["TARGETS"] = TEST_TARGET
    agent_env["BACKEND_URL"] = f"http://127.0.0.1:{TEST_BACKEND_PORT}"
    agent_env["PROBE_INTERVAL"] = "2"
    agent_env["PROBE_TIMEOUT"] = "1"

    print("Starting Cypher Agent...")
    agent_proc = subprocess.Popen(
        [venv_python, "-m", "agent.main"],
        env=agent_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    tests_failed = False

    try:
        # --- PHASE 1: LOCAL INTEGRATION TEST (UP PATH) ---
        print("\n--- PHASE 1: Local Integration Test (UP Path) ---")
        time.sleep(4)  # Wait for a couple of probes

        code, body = make_request(f"http://127.0.0.1:{TEST_BACKEND_PORT}/status")
        assert code == 200, f"Expected 200 status code, got {code}"
        
        statuses = body.get("statuses", [])
        matched_status = next((s for s in statuses if s.get("agent_id") == TEST_AGENT_ID and s.get("target") == TEST_TARGET), None)
        
        if matched_status and matched_status.get("status") == "UP":
            print(f"[{PASS}] Agent successfully reported UP status to backend.")
            print(f"       Recorded Latency: {matched_status.get('latency_ms')} ms")
        else:
            print(f"[{FAIL}] Agent failed to report UP status. Got statuses: {statuses}")
            tests_failed = True

        # --- PHASE 2: FAILURE SIMULATION (DOWN PATH) ---
        print("\n--- PHASE 2: Failure Simulation (DOWN Path) ---")
        mock_target.stop()
        time.sleep(4)  # Wait for failure detection and diagnostics report

        code, body = make_request(f"http://127.0.0.1:{TEST_BACKEND_PORT}/status")
        assert code == 200, f"Expected 200 status code, got {code}"
        
        statuses = body.get("statuses", [])
        matched_status = next((s for s in statuses if s.get("agent_id") == TEST_AGENT_ID and s.get("target") == TEST_TARGET), None)
        
        if matched_status and matched_status.get("status") == "DOWN":
            print(f"[{PASS}] Agent successfully detected failure and flipped status to DOWN.")
        else:
            print(f"[{FAIL}] Failure not detected or status not updated. Got: {statuses}")
            tests_failed = True

        # Check incidents table in PostgreSQL
        db_incident = asyncio.run(check_postgres_incident())
        if db_incident:
            print(f"[{PASS}] Incident successfully written to PostgreSQL.")
            print(f"       Ping Diagnostic: {db_incident.get('ping_diagnostic')}")
            print(f"       DNS Diagnostic: {db_incident.get('dns_diagnostic')}")
            print(f"       Error: {db_incident.get('error_diagnostic')}")
            
            # Assert diagnostics are filled
            assert db_incident.get("ping_diagnostic") is not None
            assert db_incident.get("dns_diagnostic") is not None
            assert db_incident.get("status") == "DOWN"
        else:
            print(f"[{FAIL}] Incident record not found in PostgreSQL database.")
            tests_failed = True

        # --- PHASE 3: RECOVERY TEST (RECOVERY TO UP) ---
        print("\n--- PHASE 3: Recovery Test ---")
        mock_target.start()
        time.sleep(4)  # Wait for recovery detection

        code, body = make_request(f"http://127.0.0.1:{TEST_BACKEND_PORT}/status")
        assert code == 200, f"Expected 200 status code, got {code}"
        
        statuses = body.get("statuses", [])
        matched_status = next((s for s in statuses if s.get("agent_id") == TEST_AGENT_ID and s.get("target") == TEST_TARGET), None)
        
        if matched_status and matched_status.get("status") == "UP":
            print(f"[{PASS}] Agent successfully detected recovery and status flipped back to UP.")
            print(f"       Recovery Latency: {matched_status.get('latency_ms')} ms")
        else:
            print(f"[{FAIL}] Recovery not detected or status remained DOWN. Got: {statuses}")
            tests_failed = True

    except Exception as e:
        print(f"[{FAIL}] Test execution encountered an exception: {e}")
        tests_failed = True
    finally:
        # Cleanup
        print("\nCleaning up processes...")
        mock_target.stop()
        
        agent_proc.terminate()
        try:
            agent_proc.wait(timeout=2)
        except Exception:
            agent_proc.kill()
            
        backend_proc.terminate()
        try:
            backend_proc.wait(timeout=2)
        except Exception:
            backend_proc.kill()
            
        print("Cleanup completed.")

    if tests_failed:
        print("\nIntegration tests failed.")
        sys.exit(1)
    else:
        print("\nAll integration, failure simulation, and recovery tests passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
