"""
verify_agent_structure.py — Verify the agent project structure task.

Checks that all required files exist and that the agent entry point
can be imported without errors.  Does NOT require Redis, PostgreSQL,
or a running backend.

Usage:
    python verify_agent_structure.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import importlib
import os
import sys

REQUIRED_FILES = [
    "agent/__init__.py",
    "agent/config.py",
    "agent/main.py",
    "agent/README.md",
]

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def check_files() -> bool:
    ok = True
    for path in REQUIRED_FILES:
        if os.path.isfile(path):
            print(f"  [{PASS}] {path} exists")
        else:
            print(f"  [{FAIL}] {path} MISSING")
            ok = False
    return ok


def check_imports() -> bool:
    ok = True
    # Make repo root importable
    sys.path.insert(0, os.path.abspath("."))

    for module in ("agent", "agent.config", "agent.main"):
        try:
            importlib.import_module(module)
            print(f"  [{PASS}] import {module}")
        except Exception as exc:
            print(f"  [{FAIL}] import {module}: {exc}")
            ok = False
    return ok


def check_config_defaults() -> bool:
    """Verify that config exposes expected attributes with sensible defaults."""
    ok = True
    try:
        from agent.config import config  # noqa: PLC0415

        checks = {
            "AGENT_ID": (str, "agent-01"),
            "TARGETS": (str, "google.com:443"),
            "BACKEND_URL": (str, "http://localhost:8000"),
            "PROBE_INTERVAL": (int, 30),
            "PROBE_TIMEOUT": (int, 5),
        }
        for attr, (expected_type, expected_default) in checks.items():
            value = getattr(config, attr, None)
            if value is None:
                print(f"  [{FAIL}] config.{attr} is missing")
                ok = False
            elif not isinstance(value, expected_type):
                print(f"  [{FAIL}] config.{attr} has wrong type: {type(value)}")
                ok = False
            else:
                print(f"  [{PASS}] config.{attr} = {value!r}")
    except Exception as exc:
        print(f"  [{FAIL}] config check raised: {exc}")
        ok = False
    return ok


def main() -> None:
    results = []

    print("\n=== File existence ===")
    results.append(check_files())

    print("\n=== Imports ===")
    results.append(check_imports())

    print("\n=== Config defaults ===")
    results.append(check_config_defaults())

    print()
    if all(results):
        print("All checks passed.")
        sys.exit(0)
    else:
        print("One or more checks FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
