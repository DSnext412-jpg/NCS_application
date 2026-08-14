"""Reproducible Windows release build for Nashik Comfort Stay.

This script:

1. Verifies the environment (venv python, PyInstaller installed).
2. Runs the full test suite (``pytest``).
3. Runs the headless smoke test.
4. Builds the one-file windowed EXE with PyInstaller.
5. Copies the final EXE (and README) into ``release/``.
6. Prints clear success/failure information.

Safety rules honoured:
* NEVER deletes or modifies production data.
* NEVER touches ``%LOCALAPPDATA%\\NashikComfortStay\\`` (the packaged app's
  writable data directory).
* Only build/working artifacts under ``build/`` and ``dist/`` are cleaned.

Run with::

    python scripts/build_windows.py

Exit codes: 0 = success, 1 = any failure.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

SPEC_FILE = ROOT / "NashikComfortStay.spec"
RELEASE_DIR = ROOT / "release"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"

EXE_NAME = "NashikComfortStay.exe"

# Never these directories anywhere in the process.
_FORBIDDEN = ("LocalAppData",)


def _fail(message: str) -> int:
    print(f"\n[BUILD FAILED] {message}")
    return 1


def _run(cmd: list[str], cwd: Path, label: str) -> bool:
    print(f"\n=== {label} ===")
    print("    ", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout[-4000:])
    if result.returncode != 0:
        print(result.stderr[-4000:])
        print(f"=== {label} FAILED (exit {result.returncode}) ===")
        return False
    print(f"=== {label} OK ===")
    return True


def main() -> int:
    print("Nashik Comfort Stay — Windows release build")
    print(f"Project root : {ROOT}")
    print(f"Python       : {PYTHON}")

    if not PYTHON.exists():
        return _fail("Virtual environment python not found. Run: python -m venv .venv")

    # 1. Environment check ---------------------------------------------------
    check = subprocess.run(
        [str(PYTHON), "-c", "import PyInstaller; print(PyInstaller.__version__)"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if check.returncode != 0:
        return _fail(
            "PyInstaller is not installed in the virtual environment.\n"
            "    Install it with:  .venv\\Scripts\\python.exe -m pip install pyinstaller"
        )
    print(f"PyInstaller version: {check.stdout.strip()}")

    # 2. Tests ---------------------------------------------------------------
    if not _run([str(PYTHON), "-m", "pytest", "-q"], ROOT, "Running test suite"):
        return _fail("Test suite did not pass — release build aborted.")

    # 3. Smoke test ----------------------------------------------------------
    if not _run([str(PYTHON), "scripts/smoke_run.py"], ROOT, "Running smoke test"):
        return _fail("Smoke test did not pass — release build aborted.")

    # 4. Clean previous build artifacts (NEVER touches production data) ------
    print("\n=== Cleaning previous build artifacts ===")
    for folder in (DIST_DIR, BUILD_DIR):
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            print(f"    removed {folder}")
    stale_exe = RELEASE_DIR / EXE_NAME
    if stale_exe.exists():
        stale_exe.unlink()
        print(f"    removed {stale_exe}")

    # 5. PyInstaller build ---------------------------------------------------
    if not _run(
        [str(PYTHON), "-m", "PyInstaller", "--clean", "--noconfirm", "--distpath", str(DIST_DIR), "--workpath", str(BUILD_DIR), str(SPEC_FILE)],
        ROOT, "Building one-file EXE",
    ):
        return _fail("PyInstaller build failed.")

    built_exe = DIST_DIR / EXE_NAME
    if not built_exe.exists():
        return _fail(f"Expected EXE not produced: {built_exe}")

    # 6. Assemble release directory -----------------------------------------
    print("\n=== Assembling release directory ===")
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_exe, RELEASE_DIR / EXE_NAME)
    shutil.copy2(ROOT / "RELEASE_NOTES.txt", RELEASE_DIR / "README.txt")

    size_bytes = (RELEASE_DIR / EXE_NAME).stat().st_size
    print(f"    {RELEASE_DIR / EXE_NAME}  ({size_bytes / 1_000_000:.1f} MB)")

    # 7. Summary -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("RELEASE BUILD COMPLETE")
    print(f"  EXE : {RELEASE_DIR / EXE_NAME}")
    print(f"  Size: {size_bytes / 1_000_000:.1f} MB")
    print("  Tests: PASSED   Smoke: PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())