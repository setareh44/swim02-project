# -*- coding: utf-8 -*-
"""آزمون سریع رابط کاربری (بدون نیاز به ویدیو).

چرا لازم است؟
    خطاهای ساخت ویجت‌ها فقط روی ویندوزِ خودِ کاربر دیده می‌شوند (در محیط
    توسعه Qt در دسترس نیست). این فایل همان کارهایی را که برنامه هنگام باز
    شدن انجام می‌دهد، گام‌به‌گام امتحان می‌کند و برای هر گام OK/FAIL چاپ
    می‌کند تا دقیقاً مشخص شود کدام بخش مشکل دارد.

اجرا:  دابل‌کلیک روی selftest.bat
"""
from __future__ import annotations

import os
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG = ROOT / "ui_selftest.log"

_lines: list[str] = []
_failures = 0


def say(text: str = "") -> None:
    print(text, flush=True)
    _lines.append(text)


def check(title: str, fn):
    """اجرای یک گام؛ خروجی گام یا None در صورت خطا."""
    global _failures
    try:
        result = fn()
    except BaseException as exc:          # noqa: BLE001 - باید هیچ‌وقت کرش نکند
        _failures += 1
        say("[FAIL] %s" % title)
        detail = "".join(traceback.format_exception(type(exc), exc,
                                                    exc.__traceback__))
        for line in detail.rstrip().splitlines():
            say("       " + line)
        return None
    say("[ OK ] %s" % title)
    return result


def main() -> int:
    say("=" * 62)
    say("  SWIM-AI - آزمون سریع رابط کاربری")
    say("  پایتون: %s" % sys.version.split()[0])
    say("=" * 62)

    os.environ["SWIM_NO_GL"] = os.environ.get("SWIM_NO_GL", "0")

    try:
        from PySide6.QtCore import Qt, QTimer  # noqa: F401
        from PySide6.QtWidgets import QApplication, QLabel
    except BaseException as exc:          # noqa: BLE001
        say("[FAIL] PySide6 نصب نیست یا بارگذاری نشد: %s" % exc)
        return _finish(1)

    from app import about_info
    from app.main_window import MainWindow
    from app.rtl import KEEP_ALIGN, RtlEnforcer
    from app.theme import QSS, apply_font, apply_palette

    app = check("ساخت QApplication", QApplication)
    if app is None:
        return _finish(1)
    app.setApplicationName("SWIM-AI")
    app.setOrganizationName("SWIM-AI")
    app.setLayoutDirection(Qt.RightToLeft)

    check("اعمال فونت", lambda: apply_font(app))
    check("اعمال رنگ‌ها", lambda: apply_palette(app))
    check("اعمال استایل (QSS)", lambda: app.setStyleSheet(QSS))
    check("نصب راست‌چین‌کننده", lambda: RtlEnforcer.install(app))

    win = check("ساخت پنجرهٔ اصلی", MainWindow)
    if win is None:
        return _finish(1)

    check("نمایش پنجره", lambda: (win.show(), _pump(app)))
    check("پس‌زمینهٔ متحرک ساخته شد",
          lambda: _assert(hasattr(win, "bg") and win.bg is not None,
                          "ویجت پس‌زمینه ساخته نشده"))
    check("صفحه‌ها ساخته شدند",
          lambda: _assert(win.stack.count() == 4,
                          "تعداد صفحه‌ها %d است" % win.stack.count()))
    check("جابه‌جایی بین صفحه‌ها", lambda: _pages(win, app))
    check("رسم پنجره (نمونه‌گیری تصویر)", lambda: _grab(win, app))
    check("پنجرهٔ «دربارهٔ نرم‌افزار»", lambda: _about(win, app))
    check("پیام شناور (Toast)", lambda: _toast(win, app))
    check("توقف/ادامهٔ انیمیشن پس‌زمینه", lambda: _pause(win))

    left_aligned = check("راست‌چین بودن متن‌ها",
                         lambda: _alignment_audit(win, app, QLabel, KEEP_ALIGN))
    if left_aligned:
        say("       توجه: %d متن چپ‌چین پیدا شد: %s"
            % (len(left_aligned), "، ".join(left_aligned[:6])))

    bidi_bad = check("جهت پاراگراف متن‌های دوزبانه",
                     lambda: _bidi_audit(win, app, QLabel, KEEP_ALIGN))
    if bidi_bad:
        say("       توجه: %d متن دوزبانه بدون RLM: %s"
            % (len(bidi_bad), "، ".join(bidi_bad[:6])))

    check("بستن پنجره", lambda: win.close())
    say("")
    say("  نسخهٔ برنامه: %s" % about_info.version_line())
    return _finish(0 if _failures == 0 else 1)


def _assert(condition, message: str):
    if not condition:
        raise AssertionError(message)
    return True


def _pump(app, times: int = 6):
    for _ in range(times):
        app.processEvents()
    return True


def _pages(win, app):
    for idx in range(4):
        win.set_page(idx, quiet=True)
        _pump(app, 2)
    win.set_page(0, quiet=True)
    return True


def _grab(win, app):
    _pump(app, 3)
    pix = win.grab()
    _assert(not pix.isNull(), "تصویر پنجره خالی است")
    return True


def _about(win, app):
    from app.about_dialog import AboutDialog

    dlg = AboutDialog(win, first_run=False)
    dlg.show()
    _pump(app, 3)
    dlg.close()
    dlg.deleteLater()
    _pump(app, 2)
    return True


def _toast(win, app):
    from app.toast import Toast

    t = Toast(win, "آزمون پیام", "info")
    t.show()
    _pump(app, 3)
    t.close()
    t.deleteLater()
    _pump(app, 2)
    return True


def _pause(win):
    win.bg.pause()
    win.bg.resume()
    return True


def _alignment_audit(win, app, QLabel, keep_align):
    """متن‌هایی که راست‌چین مطلق نشده‌اند (باید خالی باشد)."""
    from PySide6.QtCore import Qt

    from app.bidi import strip_marks

    _pump(app, 3)
    bad = []
    for lab in win.findChildren(QLabel):
        text = strip_marks(lab.text()).strip()
        if not text or not lab.isVisible() or lab.property(keep_align):
            continue
        align = int(lab.alignment())
        if align & int(Qt.AlignHCenter):
            continue
        if (align & int(Qt.AlignRight)) and (align & int(Qt.AlignAbsolute)):
            continue
        bad.append(text.replace("\n", " ")[:24])
    return bad


def _bidi_audit(win, app, QLabel, keep_align):
    """متن‌هایی که با کلمهٔ لاتین شروع می‌شوند و RLM ندارند."""
    from app.bidi import ensure_rtl_text, strip_marks

    _pump(app, 2)
    bad = []
    for lab in win.findChildren(QLabel):
        text = lab.text()
        if not text.strip() or lab.property(keep_align):
            continue
        if ensure_rtl_text(text) != text:
            bad.append(strip_marks(text)[:24])
    return bad


def _finish(code: int) -> int:
    say("=" * 62)
    if code == 0:
        say("  نتیجه: همهٔ گام‌ها سالم بود. برنامه باید درست باز شود.")
    else:
        say("  نتیجه: مشکلی پیدا شد (بالا را ببینید).")
        say("  فایل گزارش: %s" % LOG)
    say("=" * 62)
    try:
        LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    except Exception:
        pass
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    code = main()
    if "--no-pause" not in sys.argv:
        try:
            input()
        except Exception:
            pass
    sys.exit(code)
