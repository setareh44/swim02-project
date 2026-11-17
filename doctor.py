#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Setargan-Darya environment check ("doctor").

Run it with the *same* interpreter you start the app with:

    python doctor.py

It prints the Python version, whether every dependency is importable, whether
the pose model bundles exist, and whether OpenGL is available. Nothing is
changed on your system; the output can be pasted into a bug report.
"""
from __future__ import annotations

import os
import platform
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def _log_dir() -> str:
    """همان مسیری که خود برنامه برای لاگ استفاده می‌کند."""
    env = os.environ.get("SETARGAN_LOG_DIR",
                         os.environ.get("SWIM_LOG_DIR"))
    if env:
        return env
    if getattr(sys, "frozen", False):
        base = (os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"))
        new = os.path.join(base, "Setargan-Darya")
        old = os.path.join(base, "SWIM-AI")
        # گزارش‌ها ممکن است هنوز در پوشه قبلی باشند
        if os.path.isdir(old) and not os.path.isdir(new):
            return old
        return new
    return ROOT
OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"


def _line(status: str, text: str) -> None:
    print("%s %s" % (status, text))


def check_python() -> bool:
    v = sys.version_info[:3]
    text = "%d.%d.%d  (%s)" % (v + (platform.machine() or "?",))
    if (3, 10) <= v[:2] <= (3, 14):
        _line(OK, "Python " + text)
        return True
    _line(BAD, "Python " + text + "  -> نیاز به Python 3.10 تا 3.14")
    print("       ویندوز: winget install -e --id Python.Python.3.12")
    print("       سپس:   py -3.12 -m venv .venv")
    return False


def check_packages() -> bool:
    mods = [
        ("numpy", "numpy"), ("cv2", "opencv-python-headless"),
        ("mediapipe", "mediapipe"), ("PySide6", "PySide6"),
        ("pyqtgraph", "pyqtgraph"),
    ]
    all_ok = True
    for mod, pkg in mods:
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            _line(OK, "%-12s %-26s %s" % (mod, ver, pkg))
        except Exception as exc:  # noqa: BLE001 - we only report
            all_ok = False
            _line(BAD, "%-12s %-26s (%s: %s)" % (mod, pkg, type(exc).__name__, exc))
    try:                        # اختیاری: فقط برای مقایسه در تست‌ها
        import scipy  # noqa: F401
        _line(OK, "%-12s %-26s %s" % ("scipy", getattr(scipy, "__version__", "?"),
                                      "(اختیاری، لازم نیست)"))
    except Exception:
        _line(OK, "%-12s %-26s %s" % ("scipy", "-", "(نصب نیست و لازم هم نیست)"))
    return all_ok


def check_opencv_version() -> bool:
    """OpenCV 5 با MediaPipe کرش می‌کند؛ باید روی شاخهٔ 4 بماند."""
    try:
        import cv2
    except Exception as exc:                       # noqa: BLE001
        _line(BAD, "OpenCV import نشد: %s" % exc)
        return False
    version = str(getattr(cv2, "__version__", "?"))
    try:
        major = int(version.split(".")[0])
    except Exception:
        major = 0
    dists = []
    try:
        from importlib import metadata
        for name in ("opencv-python", "opencv-contrib-python",
                     "opencv-python-headless",
                     "opencv-contrib-python-headless"):
            try:
                dists.append("%s %s" % (name, metadata.version(name)))
            except Exception:
                continue
    except Exception:
        pass
    if major >= 5:
        _line(BAD, "OpenCV %s -> با MediaPipe ناسازگار است (برنامه در تحلیل "
                   "بسته می‌شود)" % version)
        print("       تعمیر خودکار:  run.bat را دوباره اجرا کنید.")
        print("       یا:  .venv\\Scripts\\python.exe -m pip install -c "
              "constraints.txt --force-reinstall --no-deps "
              "opencv-python-headless")
        return False
    _line(OK, "OpenCV %s (شاخهٔ 4، سازگار)" % version)
    if dists:
        print("       installed: " + ", ".join(dists))
    return True


def check_models() -> bool:
    folder = os.path.join(ROOT, "models")
    names = ("pose_landmarker_lite.task", "pose_landmarker_full.task")
    found = []
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            size = os.path.getsize(path) / 1e6
            _line(OK, "model %-30s %.1f MB" % (name, size))
            found.append(name)
        else:
            _line(WARN, "model %-30s موجود نیست (در اولین اجرا دانلود می‌شود)" % name)
    return bool(found)


def check_opengl() -> None:
    try:
        from PySide6.QtGui import QOpenGLContext
    except Exception as exc:  # noqa: BLE001
        _line(WARN, "OpenGL قابل بررسی نیست (%s) -> حالت نرم‌افزاری" % exc)
        return
    try:
        ctx = QOpenGLContext()
        if ctx.create():
            _line(OK, "OpenGL context ساخته شد")
        else:
            _line(WARN, "OpenGL در دسترس نیست -> برنامه با رندر نرم‌افزاری اجرا می‌شود")
    except Exception as exc:  # noqa: BLE001
        _line(WARN, "OpenGL در دسترس نیست (%s) -> رندر نرم‌افزاری" % exc)


def check_mediapipe_backend() -> None:
    try:
        import mediapipe as mp
    except Exception as exc:  # noqa: BLE001
        _line(BAD, "mediapipe import نشد: %s" % exc)
        return
    if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
        _line(OK, "backend: legacy mp.solutions.pose")
        return
    try:
        from mediapipe.tasks.python import BaseOptions, vision  # noqa: F401
        _line(OK, "backend: PoseLandmarker Tasks API")
        model = os.path.join(ROOT, "models", "pose_landmarker_lite.task")
        if os.path.isfile(model):
            vision.PoseLandmarker.create_from_options(
                vision.PoseLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=model),
                    running_mode=vision.RunningMode.IMAGE)).close()
            _line(OK, "PoseLandmarker با موفقیت ساخته شد")
    except OSError as exc:
        _line(BAD, "PoseLandmarker ساخته نشد: %s" % exc)
        print("       لینوکس: sudo apt-get install -y libegl1 libgl1 libglib2.0-0")
        print("       ویندوز: Visual C++ Redistributable 2015-2022")
    except Exception as exc:  # noqa: BLE001
        _line(WARN, "PoseLandmarker بررسی نشد: %s" % exc)


def main() -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    print("=" * 62)
    print("  Setargan-Darya doctor - %s" % platform.platform())
    print("  interpreter: %s" % sys.executable)
    print("  project    : %s" % ROOT)
    print("=" * 62)
    py_ok = check_python()
    pkgs_ok = check_packages()
    cv_ok = check_opencv_version()
    print("-" * 62)
    check_models()
    if py_ok and pkgs_ok:
        check_mediapipe_backend()
        check_opengl()
    _line(OK, "فایل‌های گزارش: %s" % _log_dir())
    print("=" * 62)
    if py_ok and pkgs_ok and cv_ok:
        print("  نتیجه: محیط آماده است.  اجرا:  python run.py")
        return 0
    print("  نتیجه: محیط آماده نیست؛ موارد [FAIL] بالا را برطرف کنید.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
