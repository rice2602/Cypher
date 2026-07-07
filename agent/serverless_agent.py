"""
serverless_agent.py — Serverless wrapper for Cypher agent.

Designed for:
- AWS Lambda (triggered by EventBridge / CloudWatch events cron)
- Azure Functions (triggered by TimerTrigger)
- Google Cloud Run (triggered by Cloud Scheduler / cron)

Runs a single probe cycle over all targets and exits.
Uses only Python stdlib (socket + time + urllib + json) — no third-party libs.
"""

import os
import sys
import json

# Ensure agent package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.config import config
from agent.probe import tcp_probe
from agent.diagnostics import collect
from agent.sender import send_heartbeat, send_incident


def run_single_probe_cycle() -> dict:
    """
    Performs a single E2E connectivity check for all configured targets.
    Reports UP (heartbeat) or DOWN (incidents + diagnostics) to the backend.
    """
    targets = [t.strip() for t in config.TARGETS.split(",") if t.strip()]
    results = []

    print(f"Cypher Serverless Agent execution starting (id={config.AGENT_ID})", flush=True)
    print(f"Targets: {targets}", flush=True)
    print(f"Backend: {config.BACKEND_URL}", flush=True)

    for target in targets:
        try:
            host, port_str = target.rsplit(":", 1)
            port = int(port_str)
        except ValueError:
            err = f"Invalid target format: {target} (expected host:port)"
            print(f"[probe] {err}", flush=True)
            results.append({"target": target, "status": "ERROR", "detail": err})
            continue

        reachable, latency_ms = tcp_probe(host, port, config.PROBE_TIMEOUT)

        if reachable:
            print(f"[probe] {target}  UP  {latency_ms} ms", flush=True)
            send_heartbeat(config.AGENT_ID, target, latency_ms)
            results.append({"target": target, "status": "UP", "latency": latency_ms})
        else:
            print(f"[probe] {target}  DOWN", flush=True)
            diag = collect(host, port, error="TCP connection failed")
            send_incident(config.AGENT_ID, target, diag)
            results.append({"target": target, "status": "DOWN", "diagnostics": diag})

    return {
        "agent_id": config.AGENT_ID,
        "timestamp": os.getenv("AWS_LAMBDA_LOG_STREAM_NAME") or os.getenv("COMPUTERNAME") or "serverless",
        "results": results
    }


def lambda_handler(event, context):
    """
    AWS Lambda entry point.
    """
    print(f"AWS Lambda trigger event: {json.dumps(event)}", flush=True)
    report = run_single_probe_cycle()
    return {
        "statusCode": 200,
        "body": json.dumps(report)
    }


def azure_handler(req):
    """
    Azure Functions HTTP/Timer trigger entry point.
    """
    import logging
    logging.info("Azure Function triggered.")
    report = run_single_probe_cycle()
    
    # Return response assuming HTTP function structure,
    # if TimerTrigger is used it will run and log.
    try:
        import azure.functions as func
        return func.HttpResponse(json.dumps(report), mimetype="application/json", status_code=200)
    except ImportError:
        return report


def main_serverless():
    """
    Cloud Run / Serverless CLI trigger entry point.
    """
    report = run_single_probe_cycle()
    print("Execution completed. Report Summary:", json.dumps(report), flush=True)


if __name__ == "__main__":
    main_serverless()
