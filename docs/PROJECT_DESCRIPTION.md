# Cypher — Comprehensive Project Description

Cypher is a self-hosted, lightweight, push-based synthetic network monitoring platform designed for system administrators, DevOps/Platform engineers, and infrastructure teams. It monitors connectivity of hosts, URLs, subnets, and VMware nodes from within private networks using distributed, lightweight monitoring agents, automatically collects diagnostic reports when a target goes down, and alerts engineers across multiple notification channels.

---

## Table of Contents
1. [System Architecture](#1-system-architecture)
2. [Key Features & Capabilities](#2-key-features--capabilities)
3. [Component Breakdown](#3-component-breakdown)
4. [Data Flow & Lifecycle](#4-data-flow--lifecycle)
5. [Database Schema & Models](#5-database-schema--models)
6. [Agent Security & Authentication](#6-agent-security--authentication)
7. [Notification System](#7-notification-system)
8. [Cloud-Native & Serverless Deployments](#8-cloud-native--serverless-deployments)
9. [Project Directory Structure](#9-project-directory-structure)
10. [Verification & Testing Suite](#10-verification--testing-suite)

---

## 1. System Architecture

Cypher follows a decentralized, push-based monitoring architecture. Instead of the central server polling targets (which fails if the target is behind a NAT or private firewall), lightweight agents run directly inside the targeted private environments and push telemetry back to the backend.

```
                  ┌──────────────────────────────────────────────┐
                  │                 Distributed                  │
                  │                   Agent(s)                   │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         │ Push TCP Status / Diagnostics
                                         │ (Signed with HMAC-SHA256)
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │               FastAPI Backend                │
                  │             (API, Logic, Auth)               │
                  └──────────────┬──────────────┬────────────────┘
                                 │              │
                    Cache status │              │ Write incidents / metrics
                    & rate limit │              │
                                 ▼              ▼
                  ┌──────────────┐              ┌────────────────┐
                  │    Redis     │              │   PostgreSQL   │
                  │ (Live Cache) │              │  (Persistent)  │
                  └──────────────┘              └────────────────┘
                         ▲                              ▲
                         │ Read status                  │ Read incidents
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                  ┌──────────────────────────────────────────────┐
                  │                Web Dashboard                 │
                  │           (Vanilla JS + Tailwind)            │
                  └──────────────────────────────────────────────┘
```

### Core Technologies
*   **Backend:** Python 3.12, FastAPI (Async database connections via `SQLAlchemy` + `asyncpg`).
*   **Database:** PostgreSQL (persistent incidents, daily uptime metrics, credentials) & Redis (live status, rate limiting).
*   **Frontend:** Single Page App (SPA) built using Vanilla JavaScript, HTML5, and TailwindCSS (Glassmorphism, dark-mode styling).
*   **Agent:** Standalone Python script using only standard library modules (`socket`, `subprocess`, `urllib`, `json`, `hmac`, `hashlib`) for lightweight execution.

---

## 2. Key Features & Capabilities

### 📡 Multi-Target Probing
Agents periodically check connectivity using TCP probes. The connection latency is measured in milliseconds. Target formats are defined as `host:port` pairs (e.g. `google.com:443`).

### 🔍 Automated Diagnostics
When a TCP connection probe fails, the agent immediately kicks off an asynchronous diagnostics suite to collect troubleshooting data:
1.  **ICMP Ping:** Runs a platform-appropriate ping command (`ping -n 1 -w 1000` on Windows, `ping -c 1 -W 1` on Linux) to check raw network packet reachability.
2.  **DNS Resolution Check:** Attempts to resolve the hostname to IP addresses via local resolver configuration.
3.  **Traceroute:** Executes a network trace (`tracert -d -h 10` on Windows, `traceroute -n -m 10` or fallback `tracepath` on Linux) capped at 10 hops to isolate the failure hop.
4.  **HTTP/Curl Diagnostic:** If the target port is a standard HTTP/S port (80, 443, 8080, 8443), it sends a GET request to capture the response status, headers, and first 200 bytes of the response body.
5.  **DNS Verification:** Resolves a global control host (e.g., `google.com`) alongside the target. If the control host resolves but the target does not, it confirms a target DNS registry configuration error. If both fail, it points to local agent gateway/network issues.

### 🧠 Smart Incident & Root Cause Analysis (RCA)
When an agent reports a target failure, the backend analyzes heartbeat history across all agents monitoring that target:
*   **Global Outage:** All monitoring agents report the target as `DOWN`.
*   **Localized Issue:** Only 1 agent sees the target as `DOWN`, while others report `UP`.
*   **Partial Outage:** A subset of agents see the target as `DOWN`.
This minimizes alert fatigue and locates local network routing/ISP issues quickly.

### 🔐 Agent Security & Rate Limiting
*   **HMAC-SHA256 Signatures:** Agent payloads are signed using a secret key. The backend validates the signature, ensuring that telemetry cannot be spoofed.
*   **Token Bucket Rate Limiting:** Redis-backed sliding-window rate limiting prevents API abuse and DDoS attacks from rogue agents (default limit: 120 requests/minute).

---

## 3. Component Breakdown

### A. FastAPI Backend (`backend/`)
Exposes REST APIs for CRUD operations on destinations, agent registration, authentication, live status feeds, historical incidents, and uptime statistics. It supports two modes:
1.  **Single-User Mode (Default):** Local-first, zero-auth setup where all endpoints are open, and dashboard authentication is bypassed.
2.  **Auth Mode:** Requires user registration and JWT-based authentication for securing endpoints and scoping data access to individual tenants.

### B. Monitoring Agent (`agent/`)
Can run as a persistent background daemon (polling loop) or as a serverless trigger (single execution cycle).
*   **`agent/main.py`:** Standard loop implementation.
*   **`agent/serverless_agent.py`:** Exposes standard entry points for AWS Lambda, Azure Functions, and Google Cloud Run.
*   **`agent/diagnostics.py` & `agent/probe.py`:** Encapsulates the probing and diagnostic logic with zero third-party dependencies.

### C. Web Dashboard (`dashboard/`)
Served directly by FastAPI at `/dashboard`, the interface provides:
*   Real-time status tiles showing agent status, target address, and latency.
*   A "Destinations" tab for managing targets.
*   An "Agents" tab for registering new agents and displaying their keys.
*   An "Incidents" log containing diagnostic logs, error snippets, and root-cause analysis details.
*   An "Uptime" chart depicting 7-day availability percentages.

---

## 4. Data Flow & Lifecycle

### Agent Loop Lifecycle
```
                 ┌──────────────────────────────────────┐
                 │       Agent fetches TARGETS list     │
                 └──────────────────┬───────────────────┘
                                    │
                                    ▼
                 ┌──────────────────────────────────────┐
                 │     TCP probe to Target:Port         │
                 └──────────┬────────────────┬──────────┘
                            │                │
                    Success │                │ Fail
                            ▼                ▼
        ┌───────────────────────┐        ┌─────────────────────────┐
        │  Send POST /heartbeat │        │ Execute diagnostic suite│
        │  with latency (ms)    │        │ (ping, DNS, traceroute) │
        └───────────────────────┘        └───────────┬──────────────┘
                                                     │
                                                     ▼
                                         ┌─────────────────────────┐
                                         │  Send POST /incident    │
                                         │  with diagnostics       │
                                         └─────────────────────────┘
```

### Backend Alert Lifecycle
1.  `POST /incident` is received and HMAC signature is verified.
2.  Backend stores the status in Redis cache.
3.  Backend performs RCA by inspecting Redis keys.
4.  The incident with diagnostics is logged to PostgreSQL.
5.  An asynchronous background task dispatches alerts to configured notification channels (Telegram, Slack, Teams, PagerDuty, Webhooks).

---

## 5. Database Schema & Models

Cypher uses SQLAlchemy (async engine) to define the schema:

### `destinations`
*   `id` (Integer, Primary Key)
*   `name` (String, e.g., "Main API")
*   `url` (String, e.g., "api.example.com")
*   `type` (String, e.g., "host", "url", "subnet", "vmware", "custom")
*   `port` (Integer, optional)
*   `description` (Text, optional)
*   `tags` (String, optional)
*   `is_active` (Boolean)
*   `created_at` (DateTime)

### `agents`
*   `id` (Integer, Primary Key)
*   `name` (String)
*   `description` (Text)
*   `location` (String, e.g., "us-east-1")
*   `destination_ids` (Text/JSON array, e.g., `"[1, 2]"`)
*   `key_id` (String, links to `AgentKey`)
*   `is_active` (Boolean)
*   `created_at` (DateTime)

### `agent_keys`
*   `id` (Integer, Primary Key)
*   `key_id` (String, Unique)
*   `key_hash` (String, SHA256 hashed secret)
*   `agent_id` (String)
*   `is_active` (Boolean)
*   `expires_at` (DateTime, optional)
*   `created_at` (DateTime)

### `incidents`
*   `id` (Integer, Primary Key)
*   `agent_id` (String)
*   `target` (String)
*   `status` (String, e.g., `DOWN`)
*   `latency_ms` (Integer, null for down)
*   `ping_diagnostic` (Text)
*   `dns_diagnostic` (Text)
*   `error_diagnostic` (Text)
*   `traceroute_diagnostic` (Text)
*   `http_diagnostic` (Text)
*   `dns_verification_diagnostic` (Text)
*   `root_cause_analysis` (Text)
*   `user_key` (String, tenant identifier)
*   `created_at` (DateTime)

### `uptime_metrics`
*   `id` (Integer, Primary Key)
*   `target` (String)
*   `day` (DateTime, normalized to midnight)
*   `up_probes` (Integer)
*   `total_probes` (Integer)
*   `user_key` (String, tenant identifier)

---

## 6. Agent Security & Authentication

HMAC authentication ensures that agent telemetry endpoints (`POST /heartbeat` and `POST /incident`) are fully secure:

1.  **Key Generation:** When an agent is registered via the dashboard, the backend generates an enrollment credential:
    *   `key_id`: A public string starting with `ak_` (e.g. `ak_876b5c...`).
    *   `key_secret`: A secure random hex string.
    *   The database stores `key_id` and the **SHA-256 hash** of the `key_secret`.
2.  **Request Signing:** The agent prepares the JSON request body. It hashes the configured `AGENT_KEY_SECRET` to match the backend's HMAC key, then computes the signature:
    $$\text{Signature} = \text{HMAC-SHA256}(\text{SHA256}(\text{key\_secret}), \text{JSON\_Body})$$
3.  **Transmission:** The agent sends the headers:
    *   `X-Cypher-Key-Id`
    *   `X-Cypher-Signature`
    *   `X-Cypher-Timestamp`
4.  **Verification:** The backend reads the request body, retrieves the stored hash for the given `key_id`, computes the expected signature, and compares them using `hmac.compare_digest`.

---

## 7. Notification System

Alert notifications are dispatched concurrently to all configured channels:

*   **Telegram:** HTML-formatted alerts utilizing a Bot Token and Chat ID.
*   **Slack:** Rich text alerts sent via Incoming Webhooks.
*   **Microsoft Teams:** Visual `MessageCard` payloads featuring a color-coded status bar (Red for `DOWN`, Green for `UP`).
*   **PagerDuty:** V2 Events integration (`/v2/enqueue`) mapping target status to PagerDuty severity (`critical` or `info`). Supports deduplication based on `cypher-{agent_id}-{target}`.
*   **Generic Webhooks:** JSON payload sent to a custom URL containing timestamps, agent details, and diagnostic summaries.

---

## 8. Cloud-Native & Serverless Deployments

Cypher is packaged for multiple execution architectures:

### Local Orchestration (Docker Compose)
*   Builds the backend container and sets up PostgreSQL and Redis.
*   Starts the FastAPI application and configures database migrations on boot.
*   Includes built-in health checks and environment settings for immediate local usage.

### Kubernetes (Helm Charts)
Located under `deployments/helm/cypher-agent/`, the chart deploys the monitoring agent to Kubernetes clusters.
*   Deployable daemonsets or standard deployments.
*   Kubernetes Secret templates store agent keys securely.
*   ConfigMaps map environment target lists and probe settings.

### Serverless Providers
The agent script has wrappers (`serverless_agent.py`) for:
*   **AWS Lambda:** Triggers via EventBridge cron schedules; routes logs.
*   **Azure Functions:** Uses the standard `TimerTrigger` execution.
*   **Google Cloud Run:** Triggered by Cloud Scheduler, running a single probe cycle and shutting down.

---

## 9. Project Directory Structure

```
cypher/
├── .env.example              # Template environment variables
├── docker-compose.yml        # Multi-container orchestration (local use)
├── docker-compose.prod.yml   # Production Compose orchestration config
├── nginx.conf                # Nginx proxy configuration
├── agent/                    # Python-based probing daemon
│   ├── config.py             # Parses environment configuration
│   ├── diagnostics.py        # Probes ping, traceroute, http, dns verification
│   ├── main.py               # Active monitoring loop
│   ├── probe.py              # Lightweight TCP socket probe
│   ├── sender.py             # Signs payloads and sends HTTP reports
│   └── serverless_agent.py   # Wrapper for AWS, Azure, and GCP Cloud Run
├── backend/                  # FastAPI web server
│   ├── requirements.txt      # Python package dependencies
│   ├── Dockerfile            # Container definition for backend
│   └── app/
│       ├── auth.py           # standard bcrypt password hashing & manual JWT
│       ├── config.py         # Backend configuration settings
│       ├── database.py       # SQL Alchemy async session manager
│       ├── main.py           # Application routes, lifespan, and rate-limiting
│       ├── models.py         # SQLAlchemy definitions
│       ├── notifications.py  # Slack, Telegram, Teams, PagerDuty, Webhooks logic
│       ├── redis_client.py   # Redis connection helper
│       └── schemas.py        # Pydantic models
├── dashboard/
│   └── index.html            # SPA dashboard layout (Tailwind + CSS)
├── deployments/              # Kubernetes Helm charts
│   └── helm/
│       └── cypher-agent/
│           ├── Chart.yaml    # Chart metadata
│           ├── values.yaml   # Default configurations
│           └── templates/    # K8s resources (deployment, configmap, etc.)
└── docs/                     # Architectural decisions and tasks
    ├── PRODUCT.txt           # Platform scope and principles
    ├── ARCHITECTURE.txt      # Component interaction diagrams
    ├── TASKS.txt             # Development progress log
    └── DECISIONS.txt         # Architectural records
```

---

## 10. Verification & Testing Suite

Cypher contains automatic verification scripts at the root level to run integration and isolated unit tests on the components:
*   `verify_agent_probe.py`: Tests TCP socket probe functionality against positive and negative targets.
*   `verify_agent_security.py`: Tests HMAC signing and validates request blockages upon wrong signature usage.
*   `verify_agent_sender.py`: Verifies sender functions, validating body payloads.
*   `verify_agent_structure.py`: Validates agent package imports and environment configs.
*   `verify_auth.py`: Tests password encryption and JWT generation/validation.
*   `verify_dashboard.py`: Simulates HTML endpoints and static dashboard content serving.
*   `verify_deployment.py`: Tests local uvicorn and redis connectivity configurations.
*   `verify_diagnostics.py`: Exercises isolated ping, traceroute, dns, and HTTP diagnostics tools.
*   `verify_heartbeat.py`: Simulates active heartbeat routes on the API.
*   `verify_incident.py`: Exercises DOWN event routes on the API.
*   `verify_integration.py`: End-to-end simulation spinning up backend, agent, and mock targets to test the full lifecycle of up, down, and recovery stages.
*   `verify_multitenant_schema.py`: Verifies multi-tenant database constraints (Cascade deletes, User-to-Organization relationships).
*   `verify_rbac.py`: Tests role attributes and permissions checks.
*   `verify_redis.py`: Evaluates Redis performance and token rate-limiters.
*   `verify_telegram.py` & `verify_telegram_live.py`: Validates Telegram API configurations and alert triggers.
