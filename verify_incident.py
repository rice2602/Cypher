import subprocess
import time
import urllib.request
import urllib.error
import json
import sys
import os
import redis
import asyncio
import asyncpg

async def check_db():
    print("Connecting to PostgreSQL to check saved incident...")
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/cypher")
    try:
        rows = await conn.fetch("SELECT * FROM incidents ORDER BY id DESC LIMIT 1;")
        if not rows:
            raise AssertionError("No rows found in incidents table")
        row = rows[0]
        print("Database record:", dict(row))
        assert row["agent_id"] == "test-agent-inc", f"Expected test-agent-inc, got {row['agent_id']}"
        assert row["target"] == "google.com", f"Expected google.com, got {row['target']}"
        assert row["status"] == "DOWN", f"Expected DOWN, got {row['status']}"
        assert row["latency_ms"] is None, f"Expected None, got {row['latency_ms']}"
        assert row["ping_diagnostic"] == "ping failed", f"Expected 'ping failed', got {row['ping_diagnostic']}"
        assert row["dns_diagnostic"] == "dns resolution failed", f"Expected 'dns resolution failed', got {row['dns_diagnostic']}"
        assert row["error_diagnostic"] == "Connection Timeout", f"Expected 'Connection Timeout', got {row['error_diagnostic']}"
        print("Database verification successful!")
    finally:
        await conn.close()

def main():
    print("Starting FastAPI server in subprocess...")
    venv_python = os.path.abspath(".venv/Scripts/python")
    proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd="backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait a bit for the server to start
    time.sleep(2)
    
    try:
        # 1. Test valid incident
        print("Sending valid incident POST request...")
        payload = {
            "agent_id": "test-agent-inc",
            "target": "google.com",
            "status": "DOWN",
            "latency_ms": None,
            "diagnostics": {
                "ping": "ping failed",
                "dns": "dns resolution failed",
                "error": "Connection Timeout"
            }
        }
        req = urllib.request.Request(
            "http://127.0.0.1:8000/incident",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        response = urllib.request.urlopen(req, timeout=5)
        data = json.loads(response.read().decode())
        print("Response data:", data)
        assert data.get("status") == "ok", "Expected status 'ok'"
        
        # 2. Verify stored in Redis
        print("Verifying data in Redis...")
        r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
        stored_raw = r.get("heartbeat:test-agent-inc:google.com")
        assert stored_raw is not None, "Telemetry not found in Redis"
        
        stored_data = json.loads(stored_raw)
        print("Stored Redis data:", stored_data)
        assert stored_data.get("agent_id") == "test-agent-inc"
        assert stored_data.get("target") == "google.com"
        assert stored_data.get("status") == "DOWN"
        assert stored_data.get("latency_ms") is None
        assert stored_data.get("diagnostics", {}).get("ping") == "ping failed"
        assert "received_at" in stored_data
        
        # 3. Verify stored in PostgreSQL
        asyncio.run(check_db())
        
        # 4. Test invalid incident validation
        print("Sending invalid incident POST request (latency_ms should not be 20 for DOWN)...")
        invalid_payload = {
            "agent_id": "test-agent-inc",
            "target": "google.com",
            "status": "DOWN",
            "latency_ms": 20,
            "diagnostics": {
                "ping": "ping failed",
                "dns": "dns resolution failed",
                "error": "Connection Timeout"
            }
        }
        req_invalid = urllib.request.Request(
            "http://127.0.0.1:8000/incident",
            data=json.dumps(invalid_payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            urllib.request.urlopen(req_invalid, timeout=5)
            print("Error: Invalid incident request succeeded, but should have failed!")
            sys.exit(1)
        except urllib.error.HTTPError as e:
            assert e.code == 422, f"Expected 422, got {e.code}"
            print("Received expected 422 validation error.")
            
        print("Verification successful!")
        sys.exit(0)
    except Exception as e:
        print("Verification failed:", str(e))
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=2)
            print("Server stdout:", stdout)
            print("Server stderr:", stderr)
        except Exception:
            pass
        sys.exit(1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

if __name__ == "__main__":
    main()
