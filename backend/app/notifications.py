import urllib.request
import urllib.parse
import json
import asyncio
from datetime import datetime, timezone
from app.config import settings

# ---------------------------------------------------------------------------
# Sync network helpers (run in threadpools to be non-blocking)
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: dict, description: str) -> None:
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
        print(f"[{description}] request failed: {e}", flush=True)


def send_telegram_sync(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    _post_json(url, payload, "Telegram")


def send_slack_sync(url: str, text: str) -> None:
    payload = {"text": text}
    _post_json(url, payload, "Slack")


def send_teams_sync(url: str, agent_id: str, target: str, status: str, error: str, rca: str) -> None:
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "FF0000" if status == "DOWN" else "00FF00",
        "summary": f"Cypher Incident: {target} is {status}",
        "sections": [{
            "activityTitle": f"Cypher Incident: {target} is {status}",
            "facts": [
                {"name": "Agent", "value": agent_id},
                {"name": "Target", "value": target},
                {"name": "Status", "value": status},
                {"name": "Error", "value": error},
                {"name": "Root Cause", "value": rca or "Under investigation"}
            ],
            "markdown": True
        }]
    }
    _post_json(url, payload, "Teams")


def send_pagerduty_sync(routing_key: str, agent_id: str, target: str, status: str, error: str, rca: str) -> None:
    url = "https://events.pagerduty.com/v2/enqueue"
    payload = {
        "routing_key": routing_key,
        "event_action": "trigger" if status == "DOWN" else "resolve",
        "dedup_key": f"cypher-{agent_id}-{target}",
        "payload": {
            "summary": f"Cypher Alert: {target} is {status} on {agent_id}",
            "source": agent_id,
            "severity": "critical" if status == "DOWN" else "info",
            "component": "Network",
            "custom_details": {
                "error": error,
                "root_cause": rca
            }
        }
    }
    _post_json(url, payload, "PagerDuty")


def send_webhook_sync(url: str, agent_id: str, target: str, status: str, error: str, rca: str) -> None:
    payload = {
        "event": "incident",
        "agent_id": agent_id,
        "target": target,
        "status": status,
        "error": error,
        "root_cause": rca,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    _post_json(url, payload, "Webhook")


# ---------------------------------------------------------------------------
# Public Async Alert Dispatcher
# ---------------------------------------------------------------------------

async def dispatch_alerts(agent_id: str, target: str, status: str, error: str, rca: str) -> None:
    """
    Asynchronously dispatches alerts to all configured notification channels:
    Telegram, Slack, Teams, PagerDuty, and Generic Webhooks.
    """
    tasks = []

    # 1. Telegram
    tg_token = settings.TELEGRAM_BOT_TOKEN
    tg_chat_id = settings.TELEGRAM_CHAT_ID
    if tg_token and tg_chat_id:
        tg_text = (
            f"🚨 <b>Cypher Incident Detected</b> 🚨\n\n"
            f"<b>Agent:</b> {agent_id}\n"
            f"<b>Target:</b> {target}\n"
            f"<b>Status:</b> {status}\n\n"
            f"<b>Error:</b> {error}\n"
            f"<b>Root Cause:</b> {rca or 'Under investigation'}"
        )
        tasks.append(asyncio.to_thread(send_telegram_sync, tg_token, tg_chat_id, tg_text))

    # 2. Slack
    slack_url = settings.SLACK_WEBHOOK_URL
    if slack_url:
        slack_text = (
            f"*🚨 Cypher Incident Detected 🚨*\n"
            f"*Agent:* {agent_id}\n"
            f"*Target:* {target}\n"
            f"*Status:* `{status}`\n"
            f"*Error:* {error}\n"
            f"*Root Cause:* {rca or 'Under investigation'}"
        )
        tasks.append(asyncio.to_thread(send_slack_sync, slack_url, slack_text))

    # 3. Teams
    teams_url = settings.TEAMS_WEBHOOK_URL
    if teams_url:
        tasks.append(asyncio.to_thread(send_teams_sync, teams_url, agent_id, target, status, error, rca))

    # 4. PagerDuty
    pd_key = settings.PAGERDUTY_ROUTING_KEY
    if pd_key:
        tasks.append(asyncio.to_thread(send_pagerduty_sync, pd_key, agent_id, target, status, error, rca))

    # 5. Generic Webhook
    webhook_url = settings.GENERIC_WEBHOOK_URL
    if webhook_url:
        tasks.append(asyncio.to_thread(send_webhook_sync, webhook_url, agent_id, target, status, error, rca))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
