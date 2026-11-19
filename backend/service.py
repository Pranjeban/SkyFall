"""Local FastAPI service for SKYFALL orchestration (stubs)."""

from __future__ import annotations

try:
    from fastapi import FastAPI
    FASTAPI_AVAILABLE = True
except Exception:  # pragma: no cover
    FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore

from audits.audit_logger import AuditLogger


def create_app() -> "FastAPI":
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed")
    app = FastAPI(title="SKYFALL Local Service", version="1.0.1")
    audit = AuditLogger()

    @app.get("/health")
    def health() -> dict:
        audit.log_event("service", action="health_check")
        return {"status": "ok", "version": "1.0.1"}

    @app.get("/audit/recent")
    def recent_audit(count: int = 10) -> dict:
        return {"entries": audit.get_last_entries(count)}

    return app


if __name__ == "__main__":  # pragma: no cover
    if FASTAPI_AVAILABLE:
        import uvicorn

        uvicorn.run(create_app(), host="127.0.0.1", port=8765)