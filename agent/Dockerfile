# syntax=docker/dockerfile:1

# ── Agent Dockerfile ──────────────────────────────────────────────────────────
# Build context: repo root (set in docker-compose.yml via context: .)
# Runs the lightweight TCP monitoring agent — no third-party dependencies.

FROM python:3.12-slim

WORKDIR /app

# Copy agent package
COPY agent/ ./agent/

# No pip install needed — agent uses stdlib only

# Write a PID file so Docker can detect hangs via kill -0
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import os,signal; signal.alarm(0)" || exit 1

CMD ["python", "-m", "agent.main"]
