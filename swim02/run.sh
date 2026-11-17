#!/usr/bin/env bash
# ============================================================
#  Setargan-Darya launcher for Linux / macOS
#  - Supports Python 3.10 through 3.14 (dual MediaPipe backend)
#  - First run creates .venv and installs all dependencies
# ============================================================
set -e
cd "$(dirname "$0")"

SAFE_ARGS=""
if [ "$1" = "--safe" ] || [ "$1" = "--no-gl" ]; then
    export SETARGAN_NO_GL=1
    SAFE_ARGS="--no-gl"
    echo "[SAFE MODE] Software rendering, OpenGL disabled"
fi

version_ok() {
    "$1" -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if (3,10) <= v <= (3,14) else 1)" >/dev/null 2>&1
}

PYCMD=""
if command -v python3 >/dev/null 2>&1 && version_ok python3; then
    PYCMD="python3"
elif command -v python >/dev/null 2>&1 && version_ok python; then
    PYCMD="python"
else
    for cmd in python3.14 python3.13 python3.12 python3.11 python3.10; do
        if command -v "$cmd" >/dev/null 2>&1 && version_ok "$cmd"; then
            PYCMD="$cmd"
            break
        fi
    done
fi

if [ -z "$PYCMD" ]; then
    echo "[ERROR] No supported Python found."
    echo "Setargan-Darya needs Python 3.10 through 3.14."
    echo "Ubuntu example: sudo apt install python3.12 python3.12-venv"
    exit 1
fi
echo "[OK] Using: $($PYCMD --version)"

if [ -d ".venv" ] && ! .venv/bin/python -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if (3,10) <= v <= (3,14) else 1)" >/dev/null 2>&1; then
    echo "[WARN] Existing .venv uses an incompatible Python; rebuilding..."
    rm -rf .venv
fi
if [ ! -d ".venv" ]; then
    echo "[1/3] Creating virtual environment (.venv)..."
    "$PYCMD" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip -q

if ! python -c "import cv2, numpy, scipy, mediapipe, PySide6, pyqtgraph" >/dev/null 2>&1; then
    echo "[2/3] Installing dependencies, please wait..."
    pip install -r requirements.txt
    pip uninstall -y opencv-contrib-python opencv-python >/dev/null 2>&1 || true
    pip install --force-reinstall --no-deps -q opencv-python-headless
fi

echo "[3/3] Starting Setargan-Darya..."
python run.py $SAFE_ARGS
