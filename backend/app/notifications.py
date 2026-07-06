import urllib.request
import urllib.parse
import json
import asyncio
from app.config import settings

def send_telegram_sync(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
    except Exception as e:
        print(f"Telegram notification error: {e}", flush=True)

async def send_telegram_notification(text: str) -> None:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        print("Telegram notification skipped: credentials not configured.", flush=True)
        return
    await asyncio.to_thread(send_telegram_sync, token, chat_id, text)
