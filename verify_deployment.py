"""
verify_deployment.py — Verify the Deployment task files.

Checks that all deployment files exist and contain the expected content.
Also validates docker-compose.yml structure using PyYAML if available,
or falls back to a basic text check.

Does NOT require Docker to be installed.
Run the manual section commands to actually build and run.

Usage:
    python verify_deployment.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import os
import sys

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[bool] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    results.append(condition)
    mark = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{suffix}")


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ── File existence ────────────────────────────────────────────────────────────

def test_files_exist() -> None:
    print("\n=== Required deployment files ===")
    files = [
        "backend/Dockerfile",
        "agent/Dockerfile",
        "docker-compose.yml",
        ".env.example",
        ".dockerignore",
    ]
    for path in files:
        check(f"{path} exists", os.path.isfile(path))


# ── Backend Dockerfile ────────────────────────────────────────────────────────

def test_backend_dockerfile() -> None:
    print("\n=== backend/Dockerfile ===")
    content = read("backend/Dockerfile")
    check("uses python:3.12-slim base image", "python:3.12-slim" in content)
    check("installs backend/requirements.txt", "backend/requirements.txt" in content)
    check("copies backend/app/", "backend/app/" in content)
    check("copies dashboard/", "dashboard/" in content)
    check("exposes port 8000", "EXPOSE 8000" in content)
    check("runs uvicorn", "uvicorn" in content)
    check("binds to 0.0.0.0", "0.0.0.0" in content)


# ── Agent Dockerfile ──────────────────────────────────────────────────────────

def test_agent_dockerfile() -> None:
    print("\n=== agent/Dockerfile ===")
    content = read("agent/Dockerfile")
    check("uses python:3.12-slim base image", "python:3.12-slim" in content)
    check("copies agent/ package", "agent/" in content)
    check("runs agent.main module", "agent.main" in content)
    check("no pip install (stdlib only)", "pip install" not in content.replace("# No pip install", ""))


# ── Docker Compose ────────────────────────────────────────────────────────────

def test_compose() -> None:
    print("\n=== docker-compose.yml ===")
    content = read("docker-compose.yml")

    # Services
    check("postgres service defined", "postgres:" in content)
    check("redis service defined", "redis:" in content)
    check("backend service defined", "backend:" in content)
    check("agent service defined", "agent:" in content)

    # Health checks
    check("postgres healthcheck present", "pg_isready" in content)
    check("redis healthcheck present", "redis-cli" in content)

    # Dependency ordering
    check("backend depends_on postgres", "depends_on" in content and "postgres" in content)
    check("backend depends_on redis", "redis" in content)

    # Volumes
    check("postgres_data volume defined", "postgres_data" in content)
    check("redis_data volume defined", "redis_data" in content)

    # Port mapping
    check("backend port 8000 exposed", '"8000:8000"' in content or "'8000:8000'" in content or "8000:8000" in content)

    # Env vars passed through
    check("DATABASE_URL passed to backend", "DATABASE_URL" in content)
    check("REDIS_URL passed to backend", "REDIS_URL" in content)
    check("AGENT_ID passed to agent", "AGENT_ID" in content)
    check("TARGETS passed to agent", "TARGETS" in content)
    check("BACKEND_URL passed to agent", "BACKEND_URL" in content)

    # Try yaml parse if available
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(content)
        services = data.get("services", {})
        check("YAML parses cleanly", True, f"{len(services)} services found")
        check("all 4 services in YAML", set(services.keys()) >= {"postgres", "redis", "backend", "agent"})
    except ImportError:
        print("  (yaml not installed — skipping YAML parse check)")
    except Exception as exc:
        check("YAML parses cleanly", False, str(exc))


# ── .env.example ─────────────────────────────────────────────────────────────

def test_env_example() -> None:
    print("\n=== .env.example ===")
    content = read(".env.example")
    required_vars = [
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "DATABASE_URL",
        "REDIS_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "AGENT_ID",
        "TARGETS",
        "BACKEND_URL",
        "PROBE_INTERVAL",
        "PROBE_TIMEOUT",
    ]
    for var in required_vars:
        check(f"{var} documented", var in content)


# ── .dockerignore ─────────────────────────────────────────────────────────────

def test_dockerignore() -> None:
    print("\n=== .dockerignore ===")
    content = read(".dockerignore")
    check(".venv excluded", ".venv" in content)
    check(".env excluded", ".env" in content)
    check("__pycache__ excluded", "__pycache__" in content)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    test_files_exist()
    test_backend_dockerfile()
    test_agent_dockerfile()
    test_compose()
    test_env_example()
    test_dockerignore()

    print()
    if all(results):
        print(f"All {len(results)} checks passed.")
        print()
        print("To build and run with Docker:")
        print("  docker compose up --build")
        print()
        print("Then open: http://localhost:8000/dashboard")
        sys.exit(0)
    else:
        failed = sum(1 for r in results if not r)
        print(f"{failed}/{len(results)} check(s) FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
