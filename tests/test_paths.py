"""Tests for centralized path management."""

from __future__ import annotations

import os

import pytest

from app.core.paths import Paths

EXPECTED_SUBDIRS = ("data", "backups", "invoices", "reports", "logs", "assets")


def test_project_root_is_detected() -> None:
    paths = Paths()
    assert (paths.project_root / "main.py").exists()
    assert (paths.project_root / "app").is_dir()


def test_app_data_dir_defaults_to_project_root_in_development(tmp_path) -> None:  # noqa: ANN001
    paths = Paths(project_root=tmp_path)
    assert paths.app_data_dir == tmp_path.resolve()


def test_app_data_dir_respects_environment_override(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    data_dir = tmp_path / "custom_app_data"
    monkeypatch.setenv("NCS_APP_DATA", str(data_dir))
    paths = Paths(project_root=tmp_path)
    assert paths.app_data_dir == data_dir.resolve()


def test_all_writable_paths_live_under_app_data_dir(tmp_path) -> None:  # noqa: ANN001
    paths = Paths(project_root=tmp_path)
    for attribute in ("data_dir", "backups_dir", "invoices_dir", "reports_dir", "logs_dir", "assets_dir"):
        resolved = getattr(paths, attribute).resolve()
        assert paths.app_data_dir in resolved.parents


def test_database_file_location(tmp_path) -> None:  # noqa: ANN001
    paths = Paths(project_root=tmp_path)
    assert paths.database_file == paths.data_dir / "hotel.db"


def test_log_file_location(tmp_path) -> None:  # noqa: ANN001
    paths = Paths(project_root=tmp_path)
    assert paths.log_file == paths.logs_dir / "application.log"


def test_ensure_directories_creates_all(tmp_path) -> None:  # noqa: ANN001
    paths = Paths(project_root=tmp_path)
    paths.ensure_directories()
    for name in EXPECTED_SUBDIRS:
        assert (paths.app_data_dir / name).is_dir()


def test_ensure_directories_is_idempotent(tmp_path) -> None:  # noqa: ANN001
    paths = Paths(project_root=tmp_path)
    paths.ensure_directories()
    paths.ensure_directories()
    for name in EXPECTED_SUBDIRS:
        assert (paths.app_data_dir / name).is_dir()


def test_paths_do_not_depend_on_working_directory(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    paths = Paths(project_root=tmp_path)
    assert paths.app_data_dir == tmp_path.resolve()
    assert paths.database_file == paths.data_dir / "hotel.db"


def test_environment_variable_not_leaked_between_instances(tmp_path) -> None:  # noqa: ANN001
    if os.environ.get("NCS_APP_DATA"):
        pytest.skip("NCS_APP_DATA is already set in this environment")
    paths = Paths(project_root=tmp_path)
    assert paths.app_data_dir == tmp_path.resolve()
