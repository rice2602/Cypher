# ⚡ Cypher — Network Monitoring Platform

> Self-hosted, lightweight network monitoring for your hosts, URLs, subnets, and VMware nodes.  
> Deploy in minutes. Monitor everything. Get alerted instantly.

---

## What is Cypher?

Cypher is a **self-hosted network monitoring platform** that lets you:

- **Monitor** any host, URL, subnet, or VMware node via lightweight agents
- **Get alerted** when targets go down (Telegram, Slack, Teams, PagerDuty, webhooks)
- **Visualise** live status, incidents, and 7-day uptime from a sleek dashboard
- **Deploy locally** — Single-user mode optimized for local deployment and team monitoring

---

## Quick Start (Docker Compose)

**1. Clone and configure**

```bash
git clone https://github.com/your-org/cypher.git
cd cypher
cp .env.example .env
# Edit .env — configure notification channels if desired
```

**2. Start all services**

```bash
docker compose up --build
```

**3. Open the dashboard**

```
http://localhost:8000/dashboard
```

**4. Create a Destination** — then register an Agent to start monitoring.

---

## Deployment Options

Cypher is optimized for **local deployment**:
- Docker Compose (recommended for local use)
- Kubernetes (via Helm charts in `deployments/helm/`)
- Serverless (AWS Lambda, Azure Functions, Google Cloud Run)

For team access, deploy behind your corporate network or use a reverse proxy with basic auth.

---

## User Onboarding Flow

```
1. Visit your Cypher dashboard (http://localhost:8000/dashboard)
2. Create a Destination (host/URL/subnet/VMware)
3. Register an Agent (requires at least 1 destination)
   → You receive a key_id + key_secret — store them safely
4. Deploy the agent with the credentials:
   AGENT_KEY_ID=<key_id>
   AGENT_KEY_SECRET=<key_secret>
   BACKEND_URL=http://localhost:8000
   TARGETS=your-host.example.com:443
5. Watch the dashboard light up 📡
```

---

## Architecture

```
┌─────────────┐   HMAC-signed   ┌──────────────┐   ┌──────────────┐
│   Agent(s)  │ ──────────────▶ │   FastAPI     │──▶│  PostgreSQL  │
│  (Docker or │                  │   Backend     │   │  (incidents, │
│  serverless)│ ◀────────────── │  + Dashboard  │   │  uptime,     │
└─────────────┘  targets config  └──────┬───────┘   │  agents, etc)│
                                        │            └──────────────┘
                                        ▼
                                  ┌──────────┐
                                  │  Redis   │
                                  │ (live    │
                                  │ status,  │
                                  │ rate lim)│
                                  └──────────┘
```

---

## Agent Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AGENT_ID` | Yes | Unique name for this agent instance |
| `TARGETS` | Yes | Comma-separated `host:port` pairs to probe |
| `BACKEND_URL` | Yes | URL of your Cypher backend |
| `AGENT_KEY_ID` | Yes (prod) | Key ID from the Agents page |
| `AGENT_KEY_SECRET` | Yes (prod) | Key secret shown once at agent creation |
| `PROBE_INTERVAL` | No | Seconds between probes (default: 30) |
| `PROBE_TIMEOUT` | No | TCP timeout per probe (default: 5) |

---

## Backend Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `RATE_LIMIT_PER_MINUTE` | No | Max agent requests/min (default: 120) |
| `CORS_ORIGINS` | No | Allowed CORS origins (default: `*`) |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token for alerts |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID for alerts |
| `SLACK_WEBHOOK_URL` | No | Slack incoming webhook URL |
| `TEAMS_WEBHOOK_URL` | No | Teams incoming webhook URL |
| `PAGERDUTY_ROUTING_KEY` | No | PagerDuty routing key |
| `GENERIC_WEBHOOK_URL` | No | Generic webhook URL |

---

## Project Structure

```
cypher/
├── backend/           FastAPI backend (CRUD, monitoring endpoints)
│   ├── app/
│   │   ├── main.py       All routes
│   │   ├── models.py     SQLAlchemy models
│   │   ├── schemas.py    Pydantic schemas
│   │   ├── config.py     Settings from env vars
│   │   ├── database.py   Async SQLAlchemy engine
│   │   ├── notifications.py  Alert dispatching
│   │   └── redis_client.py
│   ├── Dockerfile
│   └── requirements.txt
├── agent/             Monitoring agent
│   ├── main.py        Probe loop
│   ├── probe.py       TCP/HTTP/DNS probing
│   ├── sender.py      Reports to backend (HMAC-signed)
│   ├── diagnostics.py Detailed failure analysis
│   └── config.py
├── dashboard/         Single-page app
│   └── index.html     Dark SPA (dashboard, CRUD)
├── docker-compose.yml Local deployment
├── deployments/       Helm charts for Kubernetes
└── .env.example       Environment variable template
```

---

## License

MIT
