# syntax=docker/dockerfile:1

# ── Agent Dockerfile ──────────────────────────────────────────────────────────
# Build context: repo root (set in docker-compose.yml via context: .)
# Runs the lightweight TCP monitoring agent — no third-party dependencies.

FROM python:3.12-slim

WORKDIR /app

# Copy agent package
COPY agent/ ./agent/

# No pip install needed — agent uses stdlib only

CMD ["python", "-m", "agent.main"]
