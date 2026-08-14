"""Application logging setup.

Logs are written to the writable log directory managed by :class:`Paths`
(default ``<app_data>/logs/application.log``) plus the console. Re-calling
:func:`setup_logging` with a different directory reconfigures the root
logger so tests can safely redirect logs to a temporary location.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured_log_dir: Path | None = None


def setup_logging(log_dir: str | Path) -> None:
    global _configured_log_dir

    log_dir = Path(log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    if _configured_log_dir == log_dir:
        return

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    root.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_dir / "application.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    root.addHandler(file_handler)
    root.addHandler(console_handler)
    _configured_log_dir = log_dir

    logging.getLogger(__name__).info("Logging initialized: %s", log_dir / "application.log")
