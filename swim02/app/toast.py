# -*- coding: utf-8 -*-
"""نوتیفیکیشن‌های کوچک (Toast) در گوشهٔ پایین‌راست پنجره.

هر دکمه یا پیام مهم برنامه یک نوتیف کوتاه نشان می‌دهد؛ نوتیف‌ها روی هم
می‌چینند و خودشان محو می‌شوند. هیچ وابستگی بیرونی ندارد و اگر ساخت نوتیف
به هر دلیلی شکست بخورد، فقط پیام در کنسول چاپ می‌شود (رابط کاربری نمی‌شکند).
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from . import icons
from .theme import C

KIND_COLOR = {
    "info": C.CYAN,
    "success": C.GREEN,
    "warning": C.YELLOW,
    "error": C.RED,
}
KIND_ICON = {
    "info": "info",
    "success": "check",
    "warning": "warning",
    "error": "warning",
}

_MARGIN = 22
_GAP = 8
_MAX_WIDTH = 400


class Toast(QFrame):
    """یک کارت نوتیف شیشه‌ای با آیکون و متن."""

    def __init__(self, host: QWidget, text: str, kind: str = "info",
                 timeout: int = 2800):
        super().__init__(host)
        self.setObjectName("toast")
        color = KIND_COLOR.get(kind, C.CYAN)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet(
            "QFrame#toast{background:rgba(8,26,45,0.97);"
            "border:1px solid %s;border-right:4px solid %s;"
            "border-radius:12px;}" % (C.BORDER_HI, color))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(9)

        ic = QLabel()
        ic.setPixmap(icons.pixmap(KIND_ICON.get(kind, "info"), color, 18))
        lay.addWidget(ic)

        self.lab = QLabel(text)
        self.lab.setWordWrap(True)
        self.lab.setStyleSheet("color:%s; font-weight:600;" % C.TEXT)
        lay.addWidget(self.lab, 1)

        # نکته: عمداً از QGraphicsOpacityEffect استفاده نمی‌کنیم. افکت گرافیکی
        # روی پنجره‌ای که یک ویجت OpenGL دارد می‌تواند باعث ناپایداری/کرش
        # شود؛ به‌جایش فقط یک انیمیشن سادهٔ موقعیت (slide) داریم.
        self.setMaximumWidth(_MAX_WIDTH)
        self.adjustSize()
        self._timeout = timeout
        self._slide = None

    # ------------------------------------------------------------------
    def fade_in(self) -> None:
        """نمایش با یک سرسرهٔ کوتاه از راست به جای انیمیشن شفافیت."""
        self.show()
        self.raise_()
        target = self.pos()
        try:
            start = QPoint(target.x() + 26, target.y())
            self.move(start)
            anim = QPropertyAnimation(self, b"pos", self)
            anim.setDuration(170)
            anim.setStartValue(start)
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._slide = anim
        except Exception:
            pass

    def fade_out(self, on_done=None) -> None:
        self._finish(on_done)

    def _finish(self, on_done) -> None:
        if on_done is not None:
            try:
                on_done(self)
            except Exception:
                pass
        self.hide()
        self.deleteLater()


class ToastManager:
    """مدیر نوتیف‌های یک پنجره؛ چیدمان از پایین به بالا."""

    def __init__(self, host: QWidget):
        self.host = host
        self.items: list[Toast] = []

    # ------------------------------------------------------------------
    def show(self, text: str, kind: str = "info", timeout: int = 2800) -> None:
        if not text:
            return
        # نوتیف تکراری پشت سر هم: همان کافی است
        if self.items and self.items[-1].property("toastText") == text:
            return
        toast = Toast(self.host, text, kind, timeout)
        toast.setProperty("toastText", text)
        self.items.append(toast)
        self.reposition()
        toast.fade_in()
        QTimer.singleShot(timeout, lambda t=toast: self.dismiss(t))

    def dismiss(self, toast: Toast) -> None:
        if toast not in self.items:
            return
        self.items.remove(toast)
        try:
            toast.fade_out(lambda _t: self.reposition())
        except RuntimeError:
            pass                      # ویجت پیش‌تر با بسته‌شدن پنجره حذف شده
        self.reposition()

    def clear(self) -> None:
        for t in list(self.items):
            self.dismiss(t)

    # ------------------------------------------------------------------
    def reposition(self) -> None:
        try:
            host = self.host
            bottom = host.height() - _MARGIN
            for toast in reversed(self.items):
                toast.adjustSize()
                w = max(240, min(toast.sizeHint().width(), _MAX_WIDTH))
                toast.setFixedWidth(int(w))
                # ارتفاع دقیق: عرض متن = عرض کارت منهای حاشیه‌ها و آیکون
                inner = max(80, int(w) - 12 - 9 - 18 - 12)
                try:
                    h = toast.lab.heightForWidth(inner) + 18
                except Exception:
                    h = toast.sizeHint().height()
                h = max(44, min(int(h), 260))
                toast.setFixedHeight(int(h))
                x = host.width() - w - _MARGIN
                bottom -= h
                toast.move(int(x), int(bottom))
                toast.raise_()
                bottom -= _GAP
        except Exception:
            pass


def _manager_for(widget: QWidget) -> ToastManager | None:
    host = widget.window() if hasattr(widget, "window") else None
    if host is None:
        return None
    mgr = getattr(host, "_swim_toasts", None)
    if mgr is None:
        mgr = ToastManager(host)
        setattr(host, "_swim_toasts", mgr)
    return mgr


def notify(widget: QWidget | None, text: str, kind: str = "info",
           timeout: int = 2800) -> None:
    """نمایش نوتیف روی پنجرهٔ ویجت داده‌شده (بی‌خطر در برابر خطا)."""
    if widget is None or not text:
        return
    try:
        mgr = _manager_for(widget)
        if mgr is not None:
            mgr.show(text, kind, timeout)
    except Exception:
        try:
            print("[Setargan-Darya] %s" % text)
        except Exception:
            pass
