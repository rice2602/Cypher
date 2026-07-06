# syntax=docker/dockerfile:1

# ── Backend Dockerfile ────────────────────────────────────────────────────────
# Build context: repo root (set in docker-compose.yml via context: .)
# Serves the FastAPI API + dashboard on port 8000.

FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies (cached layer — only re-runs when requirements change)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY backend/app/ ./app/

# Copy dashboard so GET /dashboard can read it at ../dashboard/index.html
# The backend resolves: __file__.parent.parent.parent / dashboard / index.html
# Inside the container that is /dashboard/index.html
COPY dashboard/ /dashboard/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
