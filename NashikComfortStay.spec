
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

VERSION_FILE = "NashikComfortStay_version_info.txt"

version_info = None
version_info_path = Path(VERSION_FILE)
if version_info_path.exists():
    version_info = str(version_info_path)

ICON_FILE = "assets/icons/hotel.ico"

icon = None
icon_path = Path(ICON_FILE)
if icon_path.exists():
    icon = str(icon_path)

datas = [("assets", "assets")]

hiddenimports = collect_submodules("reportlab")
hiddenimports += collect_submodules("openpyxl")
hiddenimports += ["sqlalchemy.dialects.sqlite"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NashikComfortStay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version=version_info,
)
