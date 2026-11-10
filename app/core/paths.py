
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "NashikComfortStay"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


class Paths:
    def __init__(self, project_root: str | os.PathLike[str] | None = None) -> None:
        if project_root is not None:
            self.project_root = Path(project_root).resolve()
        elif is_frozen():
            self.project_root = Path(sys.executable).resolve().parent
        else:
            self.project_root = Path(__file__).resolve().parent.parent.parent

        self.app_data_dir = self._resolve_app_data_dir()

    def _resolve_app_data_dir(self) -> Path:
        override = os.environ.get("NCS_APP_DATA")
        if override:
            return Path(override)
        if is_frozen():
            local = os.environ.get("LOCALAPPDATA")
            if local:
                return Path(local) / APP_DIR_NAME
            return Path.home() / ".nashik_comfort_stay"
        return self.project_root

    def ensure_directories(self) -> None:
        for name in (
            "data",
            "backups",
            "invoices",
            "reports",
            "logs",
            "assets",
        ):
            (self.app_data_dir / name).mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        return self.app_data_dir / "data"

    @property
    def backups_dir(self) -> Path:
        return self.app_data_dir / "backups"

    @property
    def invoices_dir(self) -> Path:
        return self.app_data_dir / "invoices"

    @property
    def reports_dir(self) -> Path:
        return self.app_data_dir / "reports"

    @property
    def logs_dir(self) -> Path:
        return self.app_data_dir / "logs"

    @property
    def assets_dir(self) -> Path:
        return self.app_data_dir / "assets"

    @property
    def database_file(self) -> Path:
        return self.data_dir / "hotel.db"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "application.log"


    @property
    def source_assets_dir(self) -> Path:
        if is_frozen():
            base = Path(getattr(sys, "_MEIPASS", self.project_root))
            return base / "assets"
        return self.project_root / "assets"
