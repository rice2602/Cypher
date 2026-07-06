import asyncio
from unittest.mock import patch, MagicMock
import sys
import os
import json

# 1. Set environment variables BEFORE importing any app components
os.environ["TELEGRAM_BOT_TOKEN"] = "mock_bot_token"
os.environ["TELEGRAM_CHAT_ID"] = "mock_chat_id"

# Set sys.path so we can import app
sys.path.insert(0, os.path.abspath("backend"))

from app.schemas import IncidentCreate
from app.main import receive_incident
from fastapi import BackgroundTasks

async def async_test():
    # 1. Create a valid IncidentCreate model
    incident_data = {
        "agent_id": "test-agent-tg",
        "target": "google.com",
        "status": "DOWN",
        "latency_ms": None,
        "diagnostics": {
            "ping": "ping timed out",
            "dns": "google.com -> 8.8.8.8",
            "error": "TimeoutError"
        }
    }
    incident = IncidentCreate(**incident_data)
    
    # 2. Setup mocks
    mock_db = MagicMock()
    async def dummy_commit():
        pass
    mock_db.commit = dummy_commit
    
    # Setup BackgroundTasks
    background_tasks = BackgroundTasks()
    
    # 3. Patch redis_client and urllib.request.urlopen
    with patch("app.main.redis_client.set", new_callable=MagicMock) as mock_redis_set, \
         patch("urllib.request.urlopen") as mock_urlopen:
        
        async def dummy_redis_set(key, val):
            pass
        mock_redis_set.side_effect = dummy_redis_set
        
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok": true}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        # 4. Call the receive_incident endpoint function
        print("Calling receive_incident in-process...")
        response = await receive_incident(
            incident=incident, 
            background_tasks=background_tasks, 
            db=mock_db
        )
        assert response == {"status": "ok"}, f"Expected status ok, got {response}"
        
        # 5. Run the background tasks
        print("Executing queued background tasks...")
        for task in background_tasks.tasks:
            await task.func(*task.args)
            
        # 6. Assertions
        assert mock_redis_set.called, "redis_client.set was not called"
        redis_key, redis_val = mock_redis_set.call_args[0]
        assert redis_key == "heartbeat:test-agent-tg:google.com"
        
        assert mock_urlopen.called, "urllib.request.urlopen was not called to send Telegram notification"
        
        # Check urlopen request properties
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://api.telegram.org/botmock_bot_token/sendMessage"
        assert req.get_header("Content-type") == "application/json"
        
        # Check payload
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["chat_id"] == "mock_chat_id"
        assert "Cypher Incident Detected" in payload["text"]
        assert "test-agent-tg" in payload["text"]
        assert "google.com" in payload["text"]
        assert "ping timed out" in payload["text"]
        
        print("Verification successful!")

def main():
    asyncio.run(async_test())

if __name__ == "__main__":
    main()
