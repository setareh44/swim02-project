# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SWIM-AI (Windows / Linux / macOS).

Build from the project root, using the project virtual environment:

    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm --clean packaging\\swim_ai.spec

or just double-click ``packaging\\build_windows.bat``.

Output
    dist/SWIM-AI/SWIM-AI.exe      portable folder (start the .exe)
    dist/SWIM-AI-Setup.exe        single installer (only if Inno Setup exists)

Why one-folder instead of one-file
    A one-file build unpacks the whole 400+ MB bundle into %TEMP% on *every*
    launch: 10-30 seconds of nothing happening, then a slow start. The folder
    build starts in ~2 s and is what the Inno Setup script packs anyway.

Size notes
    * PySide6-Essentials + only the six Qt modules the UI imports
      (Core, Gui, Widgets, OpenGL, OpenGLWidgets, Svg) - those are ~24 MB.
      Never install the bare ``PySide6`` meta-package: it adds 600 MB of
      QtWebEngine / Qt3D / QtQuick that this app never touches.
    * matplotlib *is* kept: ``mediapipe.tasks.python.vision`` imports it at
      module level (its drawing helpers use pyplot).
    * scipy is not needed at all - the engine uses a NumPy ``find_peaks``.
    * UPX is disabled on purpose: compressing Qt DLLs makes antivirus
      scanners suspicious and occasionally crashes the Qt plugin loader.
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent          # noqa: F821 - set by PyInstaller
APP_NAME = "SWIM-AI"
ICON = ROOT / "packaging" / "swim_ai.ico"

def _submodules(pkg: str):
    """Best effort: a package that cannot be imported here (missing system
    library on the build machine) must not abort the whole build."""
    try:
        return collect_submodules(pkg)
    except Exception as exc:                      # noqa: BLE001
        print("[spec] WARNING: could not list submodules of %r: %s" % (pkg, exc))
        return []


def _datafiles(pkg: str):
    try:
        return collect_data_files(pkg, include_py_files=False)
    except Exception as exc:                      # noqa: BLE001
        print("[spec] WARNING: could not collect data of %r: %s" % (pkg, exc))
        return []


# ---------------------------------------------------------------- data files
datas = []

# pose models are shipped next to the program (no download on first run)
models_dir = ROOT / "models"
if models_dir.is_dir():
    datas += [(str(p), "models") for p in models_dir.glob("*.task")]

# صدای شروع برنامه و آیکون‌های همراه (app/assets)
assets_dir = ROOT / "app" / "assets"
if assets_dir.is_dir():
    datas += [(str(p), "app/assets") for p in assets_dir.iterdir() if p.is_file()]
    # زیرپوشهٔ تصویرهای دکمه‌های پخش/توقف (app/assets/media/*.png)
    media_dir = assets_dir / "media"
    if media_dir.is_dir():
        datas += [(str(p), "app/assets/media")
                  for p in sorted(media_dir.glob("*.png"))]

# mediapipe ships .binarypb / .tflite assets inside the wheel
datas += _datafiles("mediapipe")

# SVG icons / styles used by pyqtgraph
datas += _datafiles("pyqtgraph")

hiddenimports = []
hiddenimports += _submodules("pyqtgraph")
hiddenimports += _submodules("mediapipe.tasks")
hiddenimports += [
    "PySide6.QtSvg",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
]

# ---------------------------------------------------------------- excludes
excludes = [
    # scientific stack the app does not import
    "scipy",
    "pandas",
    "sklearn",
    "sympy",
    "IPython",
    "notebook",
    "jupyter",
    "pytest",
    "pip",
    "wheel",
    # stdlib GUI we do not use
    "tkinter",
    "_tkinter",
    # other Qt bindings (they would conflict with PySide6)
    "PyQt5",
    "PyQt6",
    "PySide2",
    # PySide6 modules that cost hundreds of MB and are never imported
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSerialPort",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    # unused matplotlib backends (each one drags in another toolkit)
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_webagg",
    "matplotlib.backends.backend_gtk3",
    "matplotlib.backends.backend_wxagg",
    "matplotlib.tests",
    "numpy.tests",
]

a = Analysis(
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed; logs go to %LOCALAPPDATA%\SWIM-AI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

# ------------------------------------------------------------- size report
def _report() -> None:
    total = 0
    biggest = []
    root = Path(DISTPATH).resolve() / APP_NAME   # noqa: F821 - PyInstaller
    if not root.is_dir():
        return
    for p in root.rglob("*"):
        if p.is_file():
            size = p.stat().st_size
            total += size
            biggest.append((size, p))
    biggest.sort(reverse=True)
    print("\n" + "=" * 60)
    print("  SWIM-AI bundle: %.1f MB in %d files" % (total / 2**20, len(biggest)))
    for size, p in biggest[:10]:
        print("   %7.1f MB  %s" % (size / 2**20, p.relative_to(root)))
    print("=" * 60)
    if sys.stdout is not None:
        sys.stdout.flush()


_report()
