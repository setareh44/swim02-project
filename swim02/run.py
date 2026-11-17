#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""لانچر Setargan-Darya (ستارگان دریا).

اگر این فایل با هر پایتونی (حتی ۳.۱۵ بدون کتابخانه‌ها) اجرا شود، خودش
تلاش می‌کند برنامه را درست بالا بیاورد:

1) اگر پوشه ``.venv`` پروژه وجود داشته باشد و سالم باشد، دوباره با
   پایتونِ همان محیط اجرا می‌شود (پس ``python run.py`` همیشه کار می‌کند،
   حتی اگر پایتون سیستم ۳.۱۵ باشد).
2) اگر ``.venv`` نباشد، با اولین پایتون سازگار (۳.۱۰ تا ۳.۱۴) می‌سازد و
   کتابخانه‌های ``requirements.txt`` را نصب می‌کند.
3) اگر هیچ پایتون سازگاری نبود، پیام فارسی با دستور دقیق نصب نشان می‌دهد.

ساده‌ترین راه برای کاربر: دابل‌کلیک روی ``run.bat``.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

MIN_VERSION = (3, 10)
MAX_VERSION = (3, 14)
SUPPORTED = "3.10 - 3.14"

ROOT = pathlib.Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
CONSTRAINTS = ROOT / "constraints.txt"
REEXEC_FLAG = "SETARGAN_VENV_REEXEC"
DEPS_CHECK = "import numpy, cv2, mediapipe, PySide6, pyqtgraph"
# membership test on purpose: the same string is also used by run.bat, where
# cmd.exe keeps "<" ">" "^" literally inside quotes and Python would choke
VERSION_CHECK = ("import sys; "
                 "raise SystemExit(0 if sys.version_info[:2] in "
                 "((3,10),(3,11),(3,12),(3,13),(3,14)) else 1)")
SUPPORTED_VERSIONS = ["3.12", "3.13", "3.11", "3.10", "3.14"]


# ---------------------------------------------------------------------------
# پیام‌ها
# ---------------------------------------------------------------------------
def _out(text: str = "") -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    print(text, flush=True)


def _banner(lines) -> None:
    _out("\n============================================================")
    for line in lines:
        _out(line)
    _out("============================================================\n")


def _pause_if_windows() -> None:
    """در ویندوز نگذار پنجره کنسول فوراً بسته شود."""
    if os.environ.get("SETARGAN_NO_PAUSE",
                       os.environ.get("SWIM_NO_PAUSE")) == "1":
        return
    if not sys.platform.startswith("win"):
        return
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            input("\nبرای بستن این پنجره Enter بزنید...")
    except Exception:
        pass


def _venv_python() -> pathlib.Path:
    if sys.platform.startswith("win"):
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


# ---------------------------------------------------------------------------
# تشخیص وضعیت
# ---------------------------------------------------------------------------
def _run_ok(cmd, timeout: int = 180) -> bool:
    """اجرای یک دستور بی‌صدا و برگرداندن True در صورت موفقیت."""
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, timeout=timeout,
                             cwd=str(ROOT))
    except Exception:
        return False
    return res.returncode == 0


def _is_supported(exe) -> bool:
    return _run_ok([str(exe), "-c", VERSION_CHECK], timeout=60)


def _has_deps(exe) -> bool:
    return _run_ok([str(exe), "-c", DEPS_CHECK], timeout=180)


def _candidate_interpreters():
    """پایتون‌های ممکن، به ترتیب اولویت.

    ویندوز: اول لانچر ``py`` با ۳.۱۲ (سازگارترین نسخه برای mediapipe)،
    بعد مسیرهای استاندارد نصب، بعد ``python`` روی PATH.
    """
    out = []
    if sys.platform.startswith("win"):
        for ver in SUPPORTED_VERSIONS:
            out.append(["py", "-" + ver])
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            for ver in SUPPORTED_VERSIONS:
                out.append([os.path.join(local, "Programs", "Python",
                                         "Python" + ver.replace(".", ""),
                                         "python.exe")])
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        for ver in SUPPORTED_VERSIONS:
            out.append([os.path.join(pf, "Python" + ver.replace(".", ""),
                                     "python.exe")])
        out.append([r"C:\Python312\python.exe"])
        out.append(["python"])
    else:
        for ver in SUPPORTED_VERSIONS + ["3"]:
            out.append(["python" + ver])
    return out


def _find_supported_interpreter():
    """اولین پایتون ۳.۱۰-۳.۱۴ نصب‌شده روی سیستم (به‌صورت لیست دستور)."""
    for cmd in _candidate_interpreters():
        if len(cmd) == 1 and os.path.isabs(cmd[0]) and not os.path.isfile(cmd[0]):
            continue        # مسیر نصب پیش‌فرضی که وجود ندارد
        try:
            res = subprocess.run(cmd + ["-c", VERSION_CHECK],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=60)
        except Exception:
            continue
        if res.returncode == 0:
            return cmd
    return None


# ---------------------------------------------------------------------------
# راه‌اندازی
# ---------------------------------------------------------------------------
def _relaunch(exe: pathlib.Path) -> int:
    """اجرای همین اسکریپت با پایتونِ محیط پروژه."""
    env = dict(os.environ)
    env[REEXEC_FLAG] = "1"
    try:
        return subprocess.call([str(exe), str(ROOT / "run.py")] + sys.argv[1:],
                               cwd=str(ROOT), env=env)
    except KeyboardInterrupt:
        return 130


def _install_deps(exe) -> bool:
    """نصب کتابخانه‌ها؛ خروجی pip زنده نمایش داده می‌شود."""
    _out("  نصب کتابخانه‌ها در حال انجام است؛ چند دقیقه طول می‌کشد…")
    _out("  (این مرحله فقط یک بار اجرا می‌شود)\n")
    cmd = [str(exe), "-m", "pip", "install", "--upgrade", "pip", "-q"]
    subprocess.call(cmd, cwd=str(ROOT))
    cmd = [str(exe), "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    if CONSTRAINTS.is_file():
        cmd += ["-c", str(CONSTRAINTS)]
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        return False
    _repair_opencv(exe)
    return _has_deps(exe)


def _opencv_major(exe) -> int | None:
    """نسخهٔ اصلی OpenCV داخل .venv (None اگر نصب نباشد)."""
    try:
        out = subprocess.check_output(
            [str(exe), "-c", "import cv2; print(cv2.__version__)"],
            cwd=str(ROOT), stderr=subprocess.DEVNULL).decode("utf-8", "replace")
        return int(out.strip().split(".")[0])
    except Exception:
        return None


def _repair_opencv(exe) -> bool:
    """OpenCV باید روی شاخهٔ 4 بماند.

    MediaPipe 1.x با OpenCV 4 ساخته شده است؛ با OpenCV 5 هنگام ساخت مدل
    تشخیص، خطای حافظهٔ نیتیو رخ می‌دهد و برنامه **بدون هیچ پیامی** بسته
    می‌شود. این تابع هم نسخهٔ 5 را تعمیر می‌کند و هم (برای سازگاری با
    نسخه‌های قدیمی) build بدون پنجرهٔ OpenCV را دوباره نصب می‌کند.
    """
    major = _opencv_major(exe)
    if major is None:
        return False
    if major >= 5:
        _out("  تعمیر نسخهٔ OpenCV (نسخهٔ 5 با MediaPipe سازگار نیست)…")
        cmd = [str(exe), "-m", "pip", "install", "-q",
               "--force-reinstall", "--no-deps",
               "opencv-python-headless>=4.8,<5"]
        if CONSTRAINTS.is_file():
            cmd[-1:-1] = ["-c", str(CONSTRAINTS)]
        subprocess.call(cmd, cwd=str(ROOT))
        major = _opencv_major(exe)
    return major is not None and major < 5


def _bootstrap_venv() -> int:
    """ساخت .venv از صفر + نصب کتابخانه‌ها."""
    interp = _find_supported_interpreter()
    if interp is None:
        _banner([
            "  Setargan-Darya - هیچ نسخه سازگاری از پایتون پیدا نشد",
            "------------------------------------------------------------",
            "  برنامه با Python %s کار می‌کند، ولی پایتون شما %s است."
            % (SUPPORTED, ".".join(str(x) for x in sys.version_info[:3])),
            "",
            "  فقط یک کار لازم است: Python 3.12 را نصب کنید.",
            "  ۱) Win + R را بزنید، بنویسید  cmd  و Enter بزنید.",
            "  ۲) این خط را کپی و Enter بزنید:",
            "        winget install -e --id Python.Python.3.12",
            "  ۳) بعد از پایان نصب، دوباره روی run.bat دابل‌کلیک کنید.",
            "",
            "  اگر winget نداشتید، از این آدرس نصب کنید:",
            "        https://www.python.org/downloads/",
            "     (هنگام نصب تیک Add python.exe to PATH را بزنید)",
        ])
        return 1

    _banner(["  Setargan-Darya - ساخت محیط اجرا (فقط بار اول)",
             "  استفاده از: %s" % " ".join(interp)])
    _out("  ساخت پوشه .venv …")
    if subprocess.call(interp + ["-m", "venv", str(VENV_DIR)], cwd=str(ROOT)) != 0:
        _banner(["  ساخت محیط مجازی ناموفق بود.",
                 "  لطفاً فایل run.bat را دابل‌کلیک کنید."])
        return 1
    exe = _venv_python()
    if not _install_deps(exe):
        _banner(["  نصب کتابخانه‌ها ناموفق بود.",
                 "  اتصال اینترنت را بررسی کنید و دوباره run.bat را اجرا کنید."])
        return 1
    _out("\n  نصب کامل شد ✓  برنامه اجرا می‌شود…\n")
    return _relaunch(exe)


def main() -> int:
    # ما در محیط پروژه اجرا می‌شویم؟ اگر نه، اول کتابخانه‌ها را چک کن.
    exe = _venv_python()
    in_venv = exe.exists() and pathlib.Path(sys.executable).resolve() == exe.resolve()

    if in_venv:
        # مسیر عادی: OpenCV را چک/تعمیر کن، بعد برنامه را بالا بیاور
        try:
            major = _opencv_major(sys.executable)
            if major is not None and major >= 5:
                _repair_opencv(sys.executable)
        except Exception:
            pass
        try:
            from app.main import main as app_main
        except ModuleNotFoundError as exc:
            rc = _missing_dependency(exc)
            _pause_if_windows()
            return rc
        return app_main()

    if exe.exists() and _is_supported(exe):
        # .venv پروژه آماده است: با آن دوباره اجرا کن (مهم وقتی python سیستم ۳.۱۵ است)
        if not _has_deps(exe):
            _banner(["  Setargan-Darya - تکمیل نصب کتابخانه‌ها در محیط پروژه"])
            if not _install_deps(exe):
                _pause_if_windows()
                return 1
        _out("  Setargan-Darya: اجرا با محیط پروژه (.venv) …")
        rc = _relaunch(exe)
        _pause_if_windows()
        return rc

    if not (MIN_VERSION <= sys.version_info[:2] <= MAX_VERSION):
        # پایتون فعلی قدیمی/جدید است و .venv هم نیست → ساخت محیط
        if os.environ.get(REEXEC_FLAG) == "1":
            rc = _bad_python()
            _pause_if_windows()
            return rc
        rc = _bootstrap_venv()
        _pause_if_windows()
        return rc

    # پایتون سازگار ولی کتابخانه‌ها نصب نیستند
    if not _has_deps(sys.executable):
        if os.environ.get(REEXEC_FLAG) == "1":
            rc = _missing_dependency(ModuleNotFoundError("PySide6"))
            _pause_if_windows()
            return rc
        rc = _bootstrap_venv()
        _pause_if_windows()
        return rc

    try:
        from app.main import main as app_main
    except ModuleNotFoundError as exc:
        rc = _missing_dependency(exc)
        _pause_if_windows()
        return rc
    return app_main()


# ---------------------------------------------------------------------------
# پیام‌های خطا
# ---------------------------------------------------------------------------
def _bad_python() -> int:
    v = ".".join(str(x) for x in sys.version_info[:3])
    _banner([
        "  Setargan-Darya - نسخه پایتون پشتیبانی نمی‌شود",
        "  Unsupported Python version: %s" % v,
        "------------------------------------------------------------",
        "  این برنامه با Python %s کار می‌کند، ولی پایتون شما %s است."
        % (SUPPORTED, v),
        "",
        "  راه‌حل: Python 3.12 را نصب کنید:",
        "     winget install -e --id Python.Python.3.12",
        "  یا از این آدرس: https://www.python.org/downloads/",
        "",
        "  بعد از نصب، فقط روی run.bat دابل‌کلیک کنید.",
        "  (نیازی به تایپ هیچ دستوری نیست)",
    ])
    return 1


def _missing_dependency(exc: ModuleNotFoundError) -> int:
    # ModuleNotFoundError.name is only filled by the import machinery
    pkg = getattr(exc, "name", None) or str(exc) or "?"
    _banner([
        "  Setargan-Darya - کتابخانه لازم نصب نیست: %s" % pkg,
        "------------------------------------------------------------",
        "  ساده‌ترین راه: فایل run.bat را در همین پوشه دابل‌کلیک کنید.",
        "  (همه کتابخانه‌ها خودکار نصب می‌شوند)",
        "",
        "  بررسی کامل محیط:  python doctor.py",
        "  جزئیات خطا در فایل: crash_log.txt",
    ])
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
