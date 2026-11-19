"""Local FastAPI service skeleton (Phase 4/6). Optional dependency."""

from __future__ import annotations

try:
    from fastapi import FastAPI
except Exception:  # pragma: no cover
    FastAPI = None  # type: ignore


def create_app():
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install fastapi and uvicorn to enable the local service.")
    app = FastAPI(title="SKYFALL Local Service", version="1.0.1")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "skyfall-local", "version": "1.0.1"}

    @app.get("/identity/health")
    def identity_health():
        from skyfall_cloud.identity_service import IdentityService
        return IdentityService().overall_health()

    return app


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8765)
