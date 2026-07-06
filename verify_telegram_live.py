"""
verify_telegram_live.py — Live Telegram notification test for Cypher.

Sends a real message to the configured Telegram bot/chat and verifies
that the API returns {"ok": true}.  Requires real credentials set as
environment variables (or hard-coded below for quick local testing).

Usage:
    python verify_telegram_live.py

Exit codes:
    0 — message delivered successfully
    1 — delivery failed (network error, bad credentials, API error)
"""

import asyncio
import json
import os
import sys
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Credentials — override via environment variables or edit here directly.
# ---------------------------------------------------------------------------
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "8852320317:AAFEN3RMbyfyXe7XqLU-ZtjYWuvsHiZ759M")
os.environ.setdefault("TELEGRAM_CHAT_ID", "8814878875")

# Ensure the backend package is importable
sys.path.insert(0, os.path.abspath("backend"))

from app.config import settings  # noqa: E402 — must come after sys.path insert


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def send_and_verify(token: str, chat_id: str, text: str) -> dict:
    """
    Send a Telegram message using the Bot API and return the parsed response.
    Raises RuntimeError on network failure or non-ok API response.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
            result = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise RuntimeError(f"Network error: {exc}") from exc

    if not result.get("ok"):
        raise RuntimeError(f"Telegram API returned not-ok: {result}")

    return result


# ---------------------------------------------------------------------------
# Async wrapper (keeps parity with the rest of the codebase)
# ---------------------------------------------------------------------------

async def test_live() -> None:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        print("FAIL: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.", flush=True)
        sys.exit(1)

    print("Sending live Telegram notification test message...", flush=True)
    message = (
        "🚀 <b>Cypher Live Test Message</b> 🚀\n\n"
        "This is a live test notification from your Cypher monitoring platform setup.\n"
        "Everything is working correctly!"
    )

    try:
        result = await asyncio.to_thread(send_and_verify, token, chat_id, message)
    except RuntimeError as exc:
        print(f"FAIL: {exc}", flush=True)
        sys.exit(1)

    msg_id = result.get("result", {}).get("message_id", "?")
    print(f"OK: Message delivered (message_id={msg_id}).", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(test_live())
