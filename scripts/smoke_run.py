"""Headless launch verification for the PySide6 application.

Runs the real startup path against a temporary data directory, verifies
that the main window opens with the correct title, and exits 0 on
success. Used to confirm the application launches on Windows without a
manual check.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["NCS_APP_DATA"] = tempfile.mkdtemp(prefix="ncs_smoke_")
os.environ["NCS_HEADLESS"] = "1"

from PySide6.QtCore import QTimer  # noqa: E402

from main import initialize_application  # noqa: E402


def run() -> int:
    from app.core.constants import APP_TITLE
    from app.ui.main_window import MainWindow

    initialized = initialize_application()
    if initialized is None:
        print("SMOKE TEST FAILED: application initialization failed", file=sys.stderr)
        return 1

    app, database, paths = initialized
    window = MainWindow(database)
    window.show()

    result = {"ok": False, "reason": ""}

    def verify() -> None:
        if not window.isVisible():
            result["reason"] = "window not visible"
        elif window.windowTitle() != APP_TITLE:
            result["reason"] = f"unexpected title: {window.windowTitle()!r}"
        elif window.sidebar.isVisible():
            result["ok"] = True
        else:
            result["reason"] = "sidebar not visible"
        app.quit()

    QTimer.singleShot(1500, verify)
    app.exec()

    database.dispose()
    if result["ok"]:
        print("SMOKE TEST PASSED")
        return 0
    print(f"SMOKE TEST FAILED: {result['reason']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(run())
