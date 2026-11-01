# -*- coding: utf-8 -*-
"""راست‌چین کردن اجباری همهٔ متن‌های رابط کاربری (فارسی، راست‌به‌چپ).

چرا لازم است؟
    Qt برای ویجت‌های استاندارد (QLabel، QLineEdit، ...) فقط زمانی متن را
    آینه می‌کند که *همهٔ* لایه‌ها راست‌به‌چپ باشند. در برنامه‌ای با ویجت
    فریم‌لس، QSS و ویجت‌های سفارشی، این زنجیره در چند نقطه می‌شکند و متن‌ها
    چپ‌چین می‌مانند. این ماژول به‌جای تکیه بر آن زنجیره، ترازِ هر ویجت متنی
    را صریحاً روی «راست» می‌گذارد — چه ویجت در استارتاپ ساخته شود و چه
    بعداً (مثل کارت‌های گزارش یا نوتیف‌ها).

نحوهٔ استفاده:
    app = QApplication(...)
    RtlEnforcer.install(app)      # همهٔ ویجت‌های آینده را هم پوشش می‌دهد
    apply_rtl_tree(window)        # ویجت‌های موجود را فوراً درست می‌کند

ویجت‌هایی که باید چپ‌چین بمانند (مثلاً نوار عنوان) با این دو خصیصه
مستثنا می‌شوند:
    widget.setProperty("keepAlign", True)      # تراز دست نمی‌خورد
    widget.setProperty("keepDirection", True)  # جهت چیدمان دست نمی‌خورد
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QLabel, QLineEdit, QWidget

from .bidi import ensure_rtl_text

KEEP_ALIGN = "keepAlign"
KEEP_DIRECTION = "keepDirection"
_DONE = "_rtlApplied"

#: فقط ویجت‌های «یک‌خطی/متن کوتاه». جعبه‌های چندخطی (گزارش اجرا، کد) عمداً
#: بیرون هستند: خروجی آن‌ها لاتین و چپ‌به‌راست است.
_TEXT_WIDGETS = (QLabel, QLineEdit, QAbstractSpinBox)


def aligned_right(value) -> int:
    """تراز را به «راست» تبدیل کن، ولی وسط‌چین و justify را نگه دار.

    نکتهٔ مهم (علت اصلی «چپ‌چین ماندن» متن‌ها):
        در Qt، ``Qt.AlignLeft`` و ``Qt.AlignRight`` به‌طور پیش‌فرض **نسبی**
        هستند: در یک ویجتِ راست‌به‌چپ، ``AlignRight`` به «لبهٔ انتهایی» یعنی
        **چپِ** تصویر ترجمه می‌شود. برای همین درخواست «راست‌چین» می‌توانست
        برعکس عمل کند. با افزودن ``Qt.AlignAbsolute`` تراز **مطلق** می‌شود و
        همیشه یعنی سمت راستِ واقعی — مستقل از جهت چیدمان.
    """
    a = int(value)
    if a & int(Qt.AlignHCenter):
        return a
    if a & int(Qt.AlignJustify):
        return a
    # فقط تراز افقی را عوض می‌کنیم و تراز عمودی را دست نمی‌زنیم
    keep_vertical = a & (int(Qt.AlignTop) | int(Qt.AlignVCenter)
                         | int(Qt.AlignBottom) | int(Qt.AlignBaseline))
    return int(Qt.AlignRight) | int(Qt.AlignAbsolute) | keep_vertical


def is_right_aligned(value) -> bool:
    return bool(int(value) & int(Qt.AlignRight))


def is_absolute(value) -> bool:
    return bool(int(value) & int(Qt.AlignAbsolute))


def fix_widget(widget: QWidget) -> bool:
    """یک ویجت را راست‌چین کن. True اگر چیزی عوض شد."""
    if widget is None or widget.property(KEEP_ALIGN):
        return False

    changed = False
    # عمداً جهت چیدمانِ هیچ ویجتی را عوض نمی‌کنیم: جهتِ سراسری برنامه از
    # `QApplication.setLayoutDirection` می‌آید و تغییر تک‌تک ویجت‌ها باعث
    # می‌شد بعضی ردیف‌ها برعکس بقیه بچینند (همان ناهماهنگیِ دیده‌شده).
    # ویجت‌هایی که باید چپ‌به‌راست بمانند خودشان setLayoutDirection می‌کنند.

    if isinstance(widget, QLabel):
        # متن‌هایی که با کلمهٔ لاتین شروع می‌شوند، پاراگراف‌شان در Qt
        # چپ‌به‌راست می‌شد و «به‌هم‌ریخته» دیده می‌شد؛ با RLM درست می‌شود.
        try:
            text = widget.text()
            fixed = ensure_rtl_text(text)
            if fixed != text:
                widget.setText(fixed)
                changed = True
        except (RuntimeError, AttributeError):
            pass

    if isinstance(widget, _TEXT_WIDGETS):
        try:
            current = widget.alignment()
        except (AttributeError, TypeError):
            return changed
        new = aligned_right(current)
        if new != int(current):
            widget.setAlignment(Qt.AlignmentFlag(new))
            changed = True
    return changed


def apply_rtl_tree(root: QWidget) -> int:
    """راست‌چین کردن یک ویجت و همهٔ فرزندانش. تعداد ویجت‌های اصلاح‌شده."""
    if root is None:
        return 0
    count = 0
    widgets = [root] + list(root.findChildren(QWidget))
    for w in widgets:
        try:
            if fix_widget(w):
                count += 1
        except RuntimeError:      # ویجت پیش‌تر حذف شده است
            continue
    return count


class RtlEnforcer(QObject):
    """فیلتر رویداد سراسری: هر ویجتی که نمایش داده شود، راست‌چین می‌شود."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False

    @classmethod
    def install(cls, app) -> "RtlEnforcer":
        enforcer = cls(app)
        app.installEventFilter(enforcer)
        app._swim_rtl_enforcer = enforcer      # جلوگیری از جمع‌آوری زباله
        return enforcer

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:      # noqa: N802 (Qt API)
        if self._busy:
            return False
        kind = event.type()
        if kind == QEvent.Show:
            try:
                if isinstance(obj, QWidget) and not obj.property(_DONE):
                    self._busy = True
                    try:
                        obj.setProperty(_DONE, True)
                        fix_widget(obj)
                    finally:
                        self._busy = False
            except RuntimeError:
                pass
        elif kind == QEvent.ChildAdded:
            try:
                child = event.child()
                if isinstance(child, QWidget) and not child.property(_DONE):
                    self._busy = True
                    try:
                        child.setProperty(_DONE, True)
                        fix_widget(child)
                    finally:
                        self._busy = False
            except (RuntimeError, AttributeError):
                pass
        elif kind in (QEvent.ContentsRectChange, QEvent.StyleChange):
            # متنی که بعد از ساخت ویجت عوض می‌شود (مثل زیرنویس مراحل تحلیل)
            # دوباره بررسی می‌شود تا پاراگرافش راست‌به‌چپ بماند.
            try:
                if isinstance(obj, QLabel) and not obj.property(KEEP_ALIGN):
                    text = obj.text()
                    fixed = ensure_rtl_text(text)
                    if fixed != text:
                        self._busy = True
                        try:
                            obj.setText(fixed)
                        finally:
                            self._busy = False
            except RuntimeError:
                pass
        return False
