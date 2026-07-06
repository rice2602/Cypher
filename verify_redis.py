import subprocess
import time
import urllib.request
import urllib.error
import json
import sys
import os

def main():
    print("Starting FastAPI server in subprocess...")
    # We run the command with backend as the working directory,
    # using the virtual environment python executable.
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
        print("Sending request to http://127.0.0.1:8000/...")
        response = urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5)
        data = json.loads(response.read().decode())
        print("Response data:", data)
        
        assert data.get("status") == "ok", "Expected status 'ok'"
        assert data.get("redis") == "connected", "Expected redis 'connected'"
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
