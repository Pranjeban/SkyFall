"""Background Microsoft sign-in jobs used by SKYFALL's conversational tools.

Only non-secret status and discovered account/environment metadata are retained.
Azure credentials remain owned by Azure CLI. Power Platform OAuth caches are
stored per SKYFALL account using OS-protected MSAL Extensions persistence.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable


class AuthenticationJobRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(self, label: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        job_id = f"auth-{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "label": label,
                "status": "running",
                "created_at": now,
                "completed_at": None,
                "result": None,
                "error": None,
            }

        def run() -> None:
            try:
                result = operation()
                status = "completed" if result.get("success") else "failed"
                error = None if status == "completed" else str(result.get("error") or "Authentication did not complete.")[:1000]
                safe_result = result if status == "completed" else {
                    key: value for key, value in result.items()
                    if key not in {"raw_output", "stdout", "stderr", "token", "access_token", "refresh_token"}
                }
            except Exception as exc:  # noqa: BLE001 - surfaced as a safe job failure
                status = "failed"
                error = f"{type(exc).__name__}: {exc}"[:1000]
                safe_result = None
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job["status"] = status
                job["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                job["result"] = safe_result
                job["error"] = error

        thread = threading.Thread(target=run, name=f"skyfall-{job_id}", daemon=True)
        thread.start()
        return {"job_id": job_id, "status": "running", "label": label}

    def get(self, job_id: str) -> dict[str, Any]:
        clean = (job_id or "").strip()
        with self._lock:
            job = self._jobs.get(clean)
            if job is None:
                return {"success": False, "error": "Unknown or expired authentication job ID."}
            return {"success": True, **job}


AUTH_JOBS = AuthenticationJobRegistry()
