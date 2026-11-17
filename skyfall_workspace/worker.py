"""Background workspace scanning worker for the PySide6 desktop UI."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .manager import WorkspaceManager


class WorkspaceScanWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, workspace_ids: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.workspace_ids = list(workspace_ids or [])

    def run(self) -> None:
        try:
            manager = WorkspaceManager()
            if self.workspace_ids:
                results = []
                for workspace_id in self.workspace_ids:
                    try:
                        results.append(manager.scan_workspace(workspace_id))
                    except Exception as exc:
                        results.append({
                            "workspace_id": workspace_id,
                            "scan_status": "failed",
                            "error": f"{type(exc).__name__}: {exc}",
                        })
            else:
                results = manager.scan_all()
            self.completed.emit(results)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
