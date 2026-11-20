"""Run the Skyfall test suite using the venv_skyfall interpreter.

Usage:
    python scripts/run_tests.py
    python scripts/run_tests.py tests/unit -v
    python scripts/run_tests.py -- -k integration
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / "venv_skyfall" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    # POSIX fallback
    VENV_PYTHON = REPO_ROOT / "venv_skyfall" / "bin" / "python"


def main() -> int:
    if not VENV_PYTHON.exists():
        print(f"ERROR: interpreter not found: {VENV_PYTHON}")
        print(f"Create it with: py -3.11 -m venv {REPO_ROOT / 'venv_skyfall'}")
        return 2

    args = sys.argv[1:] or ["tests/"]
    cmd = [str(VENV_PYTHON), "-m", "pytest", *args]
    print("Using interpreter:", VENV_PYTHON)
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    print("pytest exit code:", result.returncode)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
