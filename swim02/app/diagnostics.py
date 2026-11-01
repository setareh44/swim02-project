# -*- coding: utf-8 -*-
"""تشخیص و ثبت علت بسته‌شدن ناگهانی برنامه.

اگر برنامه در حین تحلیل بدون پیام بسته شود، یعنی خطا در سطح **کد نیتیو**
(MediaPipe / OpenCV / Qt) رخ داده و پایتون فرصت نوشتن Traceback نداشته است.
این ماژول سه کار می‌کند:

1. `faulthandler` را روشن می‌کند: در چنین کرش‌هایی، **آخرین فریم‌های پایتون**
   و آدرس خطا در فایل `fatal.log` نوشته می‌شود (تنها راه دیدن علت واقعی).
2. «نشانگر تحلیل» می‌نویسد: پیش از شروع تحلیل یک فایل کوچک ساخته می‌شود و پس
   از پایان/خطای عادی پاک می‌شود. اگر برنامه کرش کند، این فایل باقی می‌ماند و
   اجرای بعدی می‌فهمد «دفعهٔ قبل وسط تحلیل بسته شد» و پیام فارسی می‌دهد.
3. خطاهای نخ‌های دیگر (`threading.excepthook`) را هم در فایل ثبت می‌کند.

همهٔ توابع این ماژول طوری نوشته شده‌اند که هرگز خودشان باعث خطا نشوند.
"""
from __future__ import annotations

import datetime as _dt
import faulthandler
import os
import sys
import threading
import traceback

_MAX_LOG_BYTES = 2_000_000          # ~۲ مگابایت، بعد از آن چرخش می‌کند
_fault_stream = None                # مرجع زنده؛ نباید جمع‌آوری شود


# ---------------------------------------------------------------------------
# مسیرها
# ---------------------------------------------------------------------------
def log_dir() -> str:
    """پوشه‌ای که همیشه قابل نوشتن است (در نسخه نصب‌شده: %LOCALAPPDATA%)."""
    env = os.environ.get("SWIM_LOG_DIR")
    if env:
        path = env
    elif getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "SWIM-AI")
    else:
        path = os.getcwd()
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        path = os.path.expanduser("~")
    return path


def _path(name: str) -> str:
    return os.path.join(log_dir(), name)


def crash_log_path() -> str:
    return _path("crash_log.txt")


def fatal_log_path() -> str:
    return _path("fatal.log")


def console_log_path() -> str:
    return _path("console.log")


def marker_path() -> str:
    return _path("analysis.state")


def info_path() -> str:
    return _path("system_info.txt")


def _rotate(path: str, limit: int = _MAX_LOG_BYTES) -> None:
    try:
        if os.path.isfile(path) and os.path.getsize(path) > limit:
            os.replace(path, path + ".old")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# نصب هوک‌ها
# ---------------------------------------------------------------------------
def install_faulthandler() -> str:
    """ثبت کرش‌های نیتیو در fatal.log. رشتهٔ مسیر فایل برگردانده می‌شود."""
    global _fault_stream
    path = fatal_log_path()
    try:
        _rotate(path)
        _fault_stream = open(path, "a", encoding="utf-8", errors="replace",
                             buffering=1)
        _fault_stream.write("\n=== SWIM-AI %s ===\n"
                            % _dt.datetime.now().isoformat(timespec="seconds"))
        faulthandler.enable(_fault_stream, all_threads=True)
    except Exception:
        _fault_stream = None
        try:
            faulthandler.enable()          # حداقل روی stderr
        except Exception:
            pass
    return path


def install_thread_excepthook(on_text=None) -> None:
    """خطاهای نخ‌های پایتون را هم در فایل بنویس."""
    def _hook(args) -> None:
        text = "".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback))
        block = ("\n[fatal] thread %s crashed - %s\n%s"
                 % (getattr(args.thread, "name", "?"),
                    _dt.datetime.now().isoformat(timespec="seconds"), text))
        try:
            with open(crash_log_path(), "a", encoding="utf-8") as f:
                f.write(block)
        except Exception:
            pass
        try:
            if on_text is not None:
                on_text(block)
            else:
                sys.stderr.write(block)
        except Exception:
            pass

    try:
        threading.excepthook = _hook
    except Exception:
        pass


# ---------------------------------------------------------------------------
# نشانگر تحلیل (برای فهمیدن کرش ناگهانی)
# ---------------------------------------------------------------------------
def mark_analysis(video: str = "", stage: str = "extract") -> None:
    """پیش از شروع تحلیل اجرا می‌شود."""
    try:
        with open(marker_path(), "w", encoding="utf-8") as f:
            f.write("%s\n%s\n%s\n"
                    % (_dt.datetime.now().isoformat(timespec="seconds"),
                       stage, video or ""))
    except Exception:
        pass


def update_marker_stage(stage: str) -> None:
    try:
        path = marker_path()
        if not os.path.isfile(path):
            return
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        while len(lines) < 3:
            lines.append("")
        lines[1] = stage
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines[:3]) + "\n")
    except Exception:
        pass


def clear_analysis_marker() -> None:
    try:
        if os.path.isfile(marker_path()):
            os.remove(marker_path())
    except Exception:
        pass


def previous_analysis_crash() -> dict | None:
    """اگر اجرای قبلی وسط تحلیل کرش کرده باشد، اطلاعات آن را برمی‌گرداند."""
    path = marker_path()
    if not os.path.isfile(path):
        return None
    data = {"started": "", "stage": "", "video": "", "fatal": "",
            "crash_log": ""}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        data["started"] = lines[0] if len(lines) > 0 else ""
        data["stage"] = lines[1] if len(lines) > 1 else ""
        data["video"] = lines[2] if len(lines) > 2 else ""
    except Exception:
        pass
    try:
        data["fatal"] = tail(fatal_log_path(), 40)
    except Exception:
        pass
    try:
        data["crash_log"] = tail(crash_log_path(), 40)
    except Exception:
        pass
    return data


def tail(path: str, lines: int = 30) -> str:
    """آخرین خطوط یک فایل متنی (بدون خواندن کل فایل)."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 16000))
            chunk = f.read().decode("utf-8", "replace")
        out = chunk.splitlines()[-lines:]
        return "\n".join(out).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# گزارش وضعیت سیستم و کد خروج
# ---------------------------------------------------------------------------
def system_info() -> str:
    lines = ["SWIM-AI diagnostics - %s"
             % _dt.datetime.now().isoformat(timespec="seconds")]
    lines.append("python      : %s" % sys.version.replace("\n", " "))
    lines.append("executable  : %s" % sys.executable)
    lines.append("frozen      : %s" % bool(getattr(sys, "frozen", False)))
    lines.append("platform    : %s" % sys.platform)
    lines.append("log_dir     : %s" % log_dir())
    for mod in ("numpy", "cv2", "mediapipe", "PySide6", "pyqtgraph", "scipy"):
        try:
            m = __import__(mod)
            lines.append("%-12s: %s" % (mod, getattr(m, "__version__", "?")))
        except Exception as exc:                       # noqa: BLE001
            lines.append("%-12s: MISSING (%s)" % (mod, exc))
    try:                                   # کدام بستهٔ OpenCV نصب است
        from importlib import metadata
        dists = []
        for name in ("opencv-python", "opencv-contrib-python",
                     "opencv-python-headless", "opencv-contrib-python-headless"):
            try:
                dists.append("%s %s" % (name, metadata.version(name)))
            except Exception:
                continue
        lines.append("opencv dists: %s" % (", ".join(dists) or "-"))
    except Exception:
        pass
    return "\n".join(lines)


def write_system_info() -> str:
    path = info_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(system_info() + "\n")
    except Exception:
        pass
    return path


_EXIT_HINTS = {
    3221225477: "خطای دسترسی به حافظه (Access Violation) در یک کتابخانهٔ "
                "نیتیو — معمولاً MediaPipe یا OpenCV",
    3221225725: "سرریز پشته (Stack Overflow) — اغلب در مدل تشخیص",
    3221226505: "برنامه توسط خود ویندوز بسته شد (بدون امکان ادامه)",
    3221225781: "کتابخانهٔ DLL لازم پیدا نشد",
}


def exit_code_text(code: int) -> str:
    """توضیح انسانی کد خروج ویندوز/لینوکس."""
    code = int(code or 0)
    if code < 0:                       # سیگنال در لینوکس/مک
        sig = -code
        names = {4: "SIGILL (دستور نامعتبر CPU)",
                 6: "SIGABRT (توقف اجباری)",
                 8: "SIGFPE (خطای محاسباتی)",
                 11: "SIGSEGV (خطای حافظه)"}
        return names.get(sig, "سیگنال %d" % sig)
    if code in _EXIT_HINTS:
        return _EXIT_HINTS[code]
    if code == 0:
        return "پایان عادی"
    return "کد خروج %d" % code


def crash_summary(data: dict | None) -> str:
    """متن فارسی کوتاه برای نمایش به کاربر."""
    if not data:
        return ""
    stage = {"extract": "استخراج اسکلت", "analyze": "محاسبات بیومکانیک",
             "render": "رندر ویدیوی خروجی", "export": "ذخیرهٔ خروجی",
             "start": "آغاز تحلیل"}.get(data.get("stage", ""), data.get("stage"))
    parts = ["دفعهٔ قبل برنامه در حین تحلیل بسته شد"]
    if stage:
        parts.append("مرحله: %s" % stage)
    if data.get("fatal"):
        last = [ln for ln in data["fatal"].splitlines() if ln.strip()]
        if last:
            parts.append("آخرین خط لاگ: %s" % last[-1][:160])
    parts.append("فایل گزارش: %s" % fatal_log_path())
    return " — ".join(parts)
