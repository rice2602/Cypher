import subprocess
import time
import urllib.request
import urllib.error
import json
import sys
import os
import redis

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
        # 1. Test valid heartbeat
        print("Sending valid heartbeat POST request...")
        payload = {
            "agent_id": "test-agent",
            "target": "google.com",
            "status": "UP",
            "latency_ms": 42
        }
        req = urllib.request.Request(
            "http://127.0.0.1:8000/heartbeat",
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
        stored_raw = r.get("heartbeat:test-agent:google.com")
        assert stored_raw is not None, "Heartbeat not found in Redis"
        
        stored_data = json.loads(stored_raw)
        print("Stored Redis data:", stored_data)
        assert stored_data.get("agent_id") == "test-agent"
        assert stored_data.get("target") == "google.com"
        assert stored_data.get("status") == "UP"
        assert stored_data.get("latency_ms") == 42
        assert "received_at" in stored_data
        
        # 3. Test invalid heartbeat (status DOWN should fail validation)
        print("Sending invalid heartbeat (status=DOWN) POST request...")
        invalid_payload = {
            "agent_id": "test-agent",
            "target": "google.com",
            "status": "DOWN",
            "latency_ms": 42
        }
        req_invalid = urllib.request.Request(
            "http://127.0.0.1:8000/heartbeat",
            data=json.dumps(invalid_payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            urllib.request.urlopen(req_invalid, timeout=5)
            print("Error: Invalid heartbeat request succeeded, but should have failed!")
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
