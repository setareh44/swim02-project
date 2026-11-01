# -*- coding: utf-8 -*-
"""نقطه ورود اپلیکیشن دسکتاپ SWIM-AI."""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

from . import diagnostics

def _log_dir() -> str:
    """پوشه‌ای که همیشه قابل نوشتن است (نسخه نصب‌شده در Program Files نیست)."""
    return diagnostics.log_dir()


CRASH_LOG = os.path.join(_log_dir(), "crash_log.txt")
CRASH_LOG_MAX_BYTES = 1_000_000
_REPEAT_WINDOW_S = 10.0

# وضعیت تشخیص خطاهای تکراری (نظیر خطای رندر در هر فریم)
_last_signature = None
_last_error_at = 0.0
_repeat_count = 0
_last_box_at = 0.0


def _write_crash(exc: BaseException) -> str:
    text = "SWIM-AI crash report - %s\n%s\n" % (
        datetime.now().isoformat(timespec="seconds"), "=" * 60)
    text += "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        with open(CRASH_LOG, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
    return text


def _pause_if_double_clicked() -> None:
    """اگر کاربر run.py را دابل‌کلیک کرده، پنجره را باز نگه دار تا خطا دیده شود.

    run.bat خودش pause می‌کند و SWIM_NO_PAUSE=1 ست می‌کند تا دو بار Enter نخواهیم.
    """
    if os.environ.get("SWIM_NO_PAUSE") == "1":
        return
    if not sys.platform.startswith("win"):
        return
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            input("\nPress Enter to close this window / Enter بزنید...")
    except Exception:
        pass


def _signature(exc_type, tb) -> str:
    """امضای کوتاه خطا: نوع + آخرین قاب، برای تشخیص تکرار.
    """
    frame = ""
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    if tb is not None:
        frame = "%s:%d:%s" % (os.path.basename(tb.tb_frame.f_code.co_filename),
                              tb.tb_lineno, tb.tb_frame.f_code.co_name)
    return "%s|%s" % (getattr(exc_type, "__name__", "?"), frame)


def _rotate_crash_log() -> None:
    """جلوگیری از بزرگ شدن بی‌سقف crash_log.txt."""
    try:
        if os.path.isfile(CRASH_LOG) and os.path.getsize(CRASH_LOG) > CRASH_LOG_MAX_BYTES:
            os.replace(CRASH_LOG, CRASH_LOG + ".1")
    except Exception:
        pass


def _excepthook(exc_type, exc, tb):
    """نمایش و ثبت خطا، با مهار خطاهای تکراری.

    خطاهای رندر (مثلاً در paintGL) ممکن است ۳۰ بار در ثانیه تکرار شوند؛
    قبلاً برای هر تکرار یک فایل و یک پنجره خطا ساخته می‌شد و برنامه
    غیرقابل استفاده می‌شد. اینجا فقط اولین خطا کامل ثبت/نمایش داده
    می‌شود و تکرارهای بعدی به شمارش خلاصه می‌شوند.
    """
    global _last_signature, _last_error_at, _repeat_count, _last_box_at
    import time

    now = time.monotonic()
    sig = _signature(exc_type, tb)
    repeated = (sig == _last_signature and now - _last_error_at < _REPEAT_WINDOW_S)
    _repeat_count = _repeat_count + 1 if repeated else 0
    _last_signature, _last_error_at = sig, now

    if repeated:
        # فقط یک خط کوتاه؛ نه فایل، نه پنجره جدید
        try:
            print("[SWIM-AI] same error repeated %d time(s): %s: %s"
                  % (_repeat_count, exc_type.__name__, exc))
        except Exception:
            pass
        return

    if _repeat_count:
        try:
            print("[SWIM-AI] previous error was repeated %d more time(s)."
                  % _repeat_count)
        except Exception:
            pass
    _repeat_count = 0

    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        sys.stderr.write(text)
        sys.stderr.flush()
    except Exception:
        pass
    _rotate_crash_log()
    try:
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write("\nSWIM-AI unhandled error - %s\n%s\n"
                    % (datetime.now().isoformat(timespec="seconds"), text))
    except Exception:
        pass

    # نمایش حداکثر یک پنجره در ۳۰ ثانیه؛ خودِ خطا قبلاً در کنسول/فایل هست
    if now - _last_box_at < 30.0:
        return
    _last_box_at = now
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        if app is None:
            return
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("خطای برنامه SWIM-AI")
        box.setText("خطای غیرمنتظره‌ای رخ داد. جزئیات در crash_log.txt ذخیره شد.")
        box.setDetailedText(text[:4000])
        box.exec()
    except Exception:
        pass


class _Tee:
    """هم به کنسول و هم به فایل بنویس (برای ثبت پیام‌های Qt/PySide)."""

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]

    def write(self, text):
        for s in self._streams:
            try:
                s.write(text)
                s.flush()
            except Exception:
                pass
        return len(text)

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def fileno(self):
        raise OSError("stream has no fileno")


def _ensure_std_streams() -> None:
    """در بیلد پنجره‌ای (بدون کنسول) sys.stdout برابر None است.

    بدون این محافظ، هر ``print`` در برنامه (گزارش فینگلیش پایپلاین) با
    ``AttributeError: 'NoneType' object has no attribute 'write'`` می‌شکست.
    """
    try:
        log = open(os.path.join(_log_dir(), "console.log"), "a",
                   encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        import io
        log = io.StringIO()

    if sys.stdout is None:
        sys.stdout = log
    elif not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout, log)

    if sys.stderr is None:
        sys.stderr = log
    elif not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr, log)


def _show_startup_error(text: str) -> None:
    """خطای شروع برنامه را به‌صورت پنجرهٔ فارسی هم نشان بده (نه فقط کنسول).

    کاربر ممکن است پنجرهٔ کنسول را نبندد/نبیند؛ این پنجره همیشه دیده می‌شود و
    دقیقاً می‌گوید چه فایلی را برای پشتیبانی بفرستد.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox
    except Exception:
        return
    if QApplication.instance() is None:
        return
    try:
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("SWIM-AI — برنامه باز نشد")
        box.setText("متأسفانه برنامه نتوانست پنجرهٔ اصلی را بسازد و بسته شد.")
        box.setInformativeText(
            "این خطا در فایل زیر ذخیره شد. لطفاً همین فایل را برای پشتیبانی "
            "بفرستید:\n\n%s" % CRASH_LOG)
        box.setDetailedText(text)
        box.setLayoutDirection(Qt.RightToLeft)
        box.exec()
    except Exception:
        pass


def _build_window(cls):
    """پنجرهٔ اصلی را بساز؛ اگر ساخت شکست خورد، یک بار بدون OpenGL تلاش کن.

    تجربه نشان داده بیشتر خطاهای «پنجره باز نمی‌شود» یا از بخش ظاهری است یا
    از OpenGL. این تابع تضمین می‌کند در صورت امکان، برنامه در حالت نرم‌افزاری
    باز شود و خطا هم در کنسول/فایل ثبت شود.
    """
    try:
        return cls()
    except BaseException as exc:            # noqa: BLE001
        print("[SWIM-AI] window construction failed: %r" % (exc,), flush=True)
        traceback.print_exc()
        if os.environ.get("SWIM_NO_GL") == "1":
            raise
        print("[SWIM-AI] retrying with software rendering (no OpenGL) ...",
              flush=True)
        os.environ["SWIM_NO_GL"] = "1"
        return cls()


def main() -> int:
    if "--no-gl" in sys.argv:
        os.environ["SWIM_NO_GL"] = "1"
    _ensure_std_streams()
    sys.excepthook = _excepthook
    # ثبت کرش‌های نیتیو (MediaPipe/OpenCV/Qt) در fatal.log — پیش از هر کار دیگر
    diagnostics.install_faulthandler()
    diagnostics.install_thread_excepthook(lambda text: print(text, flush=True))
    diagnostics.write_system_info()
    # اگر اجرای قبلی وسط تحلیل کرش کرده بود، پیش از پاک‌کردن نشانگر بخوانش
    previous_crash = diagnostics.previous_analysis_crash()
    try:
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import QApplication

        from .main_window import MainWindow
        from .rtl import RtlEnforcer
        from .sound import play_startup_sound
        from .theme import QSS, apply_font, apply_palette

        app = QApplication(sys.argv)
        app.setApplicationName("SWIM-AI")
        app.setOrganizationName("SWIM-AI")
        app.setLayoutDirection(Qt.RightToLeft)
        apply_font(app)
        apply_palette(app)
        app.setStyleSheet(QSS)
        # هر ویجتی که ساخته و نمایش داده شود، راست‌چین می‌شود
        RtlEnforcer.install(app)

        win = _build_window(MainWindow)
        win.show()

        # موزیک کوتاه شروع (تم آب/استخر)؛ اگر کاربر خاموش کرده باشد پخش نمی‌شود
        QTimer.singleShot(120, play_startup_sound)
        # اولین اجرا: پنجرهٔ «درباره» با تیک «دیگر نمایش نده»
        QTimer.singleShot(600, win.maybe_show_first_run)
        # اگر اجرای قبلی وسط تحلیل بسته شده بود، علتش را کامل نشان بده
        if previous_crash:
            diagnostics.clear_analysis_marker()
            QTimer.singleShot(900,
                              lambda: win.show_previous_crash(previous_crash))
        return app.exec()
    except BaseException as exc:  # noqa: BLE001
        text = _write_crash(exc)
        print("\n" + "=" * 60)
        print("  SWIM-AI failed to start. Full error:")
        print("=" * 60)
        print(text)
        print("Log saved to: %s" % CRASH_LOG)
        _show_startup_error(text)
        _pause_if_double_clicked()
        return 1


if __name__ == "__main__":
    sys.exit(main())
