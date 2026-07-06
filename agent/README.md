Cypher Agent
============

Lightweight push-based monitoring agent for Cypher.

Runs inside a private network and periodically probes configured TCP
targets, reporting heartbeats (UP) or incidents (DOWN) to the Cypher
backend API.

## Requirements

- Python 3.12+
- No third-party dependencies (uses stdlib only)

## Running the agent

From the repository root:

    python -m agent.main

## Configuration (environment variables)

| Variable        | Default                   | Description                              |
|-----------------|---------------------------|------------------------------------------|
| AGENT_ID        | agent-01                  | Unique name for this agent instance      |
| TARGETS         | google.com:443            | Comma-separated host:port pairs to probe |
| BACKEND_URL     | http://localhost:8000     | Cypher backend API base URL              |
| PROBE_INTERVAL  | 30                        | Seconds between probe runs               |
| PROBE_TIMEOUT   | 5                         | TCP connection timeout in seconds        |

## Project structure

    agent/
    ├── __init__.py   — package marker
    ├── config.py     — environment-based configuration
    └── main.py       — entry point and probe loop
