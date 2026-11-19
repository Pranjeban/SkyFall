"""Safe subprocess helper for local Microsoft CLI discovery.

Commands are passed as argument arrays (never through a shell). Output is
bounded and sensitive token-like values are redacted before being returned.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence


_MAX_OUTPUT_CHARS = 2_000_000


@dataclass(frozen=True)
class CommandResult:
    executable: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def redact_sensitive_text(value: str) -> str:
    """Redact common token/secret formats from CLI output before display/storage."""
    if not value:
        return value
    text = value[:_MAX_OUTPUT_CHARS]
    # JWT-like bearer tokens.
    text = re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*",
        "Bearer [REDACTED]",
        text,
    )
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        "[REDACTED_TOKEN]",
        text,
    )
    # JSON / key-value token fields.
    text = re.sub(
        r'(?i)("?(?:access_?token|refresh_?token|id_?token|client_?secret|password|secret)"?\s*[:=]\s*")([^"\r\n]+)(")',
        r"\1[REDACTED]\3",
        text,
    )
    text = re.sub(
        r"(?i)(\b(?:access_?token|refresh_?token|id_?token|client_?secret|password|secret)\b\s*[:=]\s*)([^\s,;]+)",
        r"\1[REDACTED]",
        text,
    )
    return text


def run_cli(
    executable: str,
    arguments: Sequence[str],
    *,
    timeout_seconds: int = 45,
    env_overrides: Mapping[str, str | None] | None = None,
) -> CommandResult:
    """Run a local CLI command safely and return redacted output.

    `env_overrides` values of None remove an environment variable; string
    values set it. No command is ever executed through cmd.exe or PowerShell.
    """
    if os.environ.get("SKYFALL_TEST_MODE") == "1":
        return CommandResult(
            executable=executable,
            returncode=125,
            stdout="",
            stderr="External CLI execution is disabled in SKYFALL_TEST_MODE.",
        )
    resolved = shutil.which(executable)
    if not resolved:
        raise FileNotFoundError(f"Required command was not found on PATH: {executable}")

    env = os.environ.copy()
    for key, value in (env_overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    try:
        completed = subprocess.run(
            [resolved, *[str(arg) for arg in arguments]],
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return CommandResult(
            executable=resolved,
            returncode=completed.returncode,
            stdout=redact_sensitive_text(completed.stdout or ""),
            stderr=redact_sensitive_text(completed.stderr or ""),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return CommandResult(
            executable=resolved,
            returncode=-1,
            stdout=redact_sensitive_text(str(stdout)),
            stderr=redact_sensitive_text(str(stderr)),
            timed_out=True,
        )
