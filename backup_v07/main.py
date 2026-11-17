"""SKYFALL desktop application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.desktop.main_window import MainWindow
from app.desktop.theme import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SKYFALL")
    app.setOrganizationName("SKYFALL")
    app.setApplicationVersion("0.6.0")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
