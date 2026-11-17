# -*- coding: utf-8 -*-
"""ابزارهای متن دوجهته (bidi) — بدون هیچ وابستگی به Qt.

چرا لازم است؟
    Qt جهت پاراگراف هر متن را از **اولین حرف «قوی»** آن متن تعیین می‌کند،
    نه از تنظیم راست‌چین بودن ویجت. پس متنی که با کلمهٔ لاتین یا شماره شروع
    شود (مثل «Setargan-Darya برای این ساخته شده…» یا «Front Crawl / Freestyle · …»)
    پاراگرافِ چپ‌به‌راست می‌شود: خط‌ها از چپ شمرده می‌شوند و جملهٔ فارسی
    «چپ‌چین / به‌هم‌ریخته» دیده می‌شود — دقیقاً همان چیزی که کاربر گزارش کرد.

راه‌حل استاندارد یونیکد: گذاشتن یک علامت **RLM** (U+200F، «نشانهٔ راست‌به‌چپ»)
در ابتدای متن. این علامت دیده نمی‌شود، ولی جهت پایهٔ پاراگراف را راست‌به‌چپ
می‌کند و ترتیب کلمات درست می‌شود.

این ماژول عمداً هیچ ایمپورتی از Qt ندارد تا بتوان آن را بدون محیط گرافیکی
هم تست کرد (در محیط توسعه Qt نصب نیست).
"""
from __future__ import annotations

#: نشانهٔ راست‌به‌چپ (Right-to-Left Mark) — نامرئی
RLM = "\u200f"
#: نشانهٔ چپ‌به‌راست (Left-to-Right Mark) — نامرئی
LRM = "\u200e"

#: همهٔ نشانه‌های کنترلی دوجهته که ممکن است در متن ظاهر شوند
BIDI_MARKS = (RLM, LRM, "\u200e", "\u200f", "\u202a", "\u202b", "\u202c",
              "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069",
              "\u061c")

_RTL_RANGES = (
    (0x0590, 0x05FF),      # عبری
    (0x0600, 0x06FF),      # عربی / فارسی
    (0x0700, 0x074F),      # سریانی
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB1D, 0xFDFF),      # فرم‌های نمایشی عربی
    (0xFE70, 0xFEFF),
    (0x1EE00, 0x1EEFF),
)

#: حروفی که جهت پاراگراف را تعیین می‌کنند (قوی)
_LTR_RANGES = (
    (0x0041, 0x005A), (0x0061, 0x007A),          # لاتین
    (0x00C0, 0x024F),                            # لاتین تکمیلی
    (0x0370, 0x03FF),                            # یونانی
    (0x0400, 0x04FF),                            # سیریلیک
    (0x0530, 0x058F),                            # ارمنی
)


#: ارقام عربی/فارسی «قوی» نیستند (AN/EN هستند) و جهت را تعیین نمی‌کنند
_NEUTRAL_DIGITS = ((0x0660, 0x0669), (0x06F0, 0x06F9))


def _in(cp: int, ranges) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def _is_strong_rtl(cp: int) -> bool:
    return _in(cp, _RTL_RANGES) and not _in(cp, _NEUTRAL_DIGITS)


def first_strong_direction(text: str) -> str | None:
    """جهت اولین حرف «قوی» متن: ``"rtl"``، ``"ltr"`` یا ``None``.

    ارقام و فاصله و نشانه‌گذاری «قوی» نیستند و نادیده گرفته می‌شوند.
    """
    for ch in text:
        cp = ord(ch)
        if _is_strong_rtl(cp):
            return "rtl"
        if _in(cp, _LTR_RANGES):
            return "ltr"
    return None


def has_persian(text: str) -> bool:
    """آیا متن حرف فارسی/عربی دارد؟ (ارقام فارسی به‌تنهایی حرف نیستند)"""
    return any(_is_strong_rtl(ord(ch)) for ch in text)


def strip_marks(text: str) -> str:
    """حذف نشانه‌های نامرئی دوجهته (برای مقایسه و تست)."""
    for mark in BIDI_MARKS:
        text = text.replace(mark, "")
    return text


def ensure_rtl_text(text: str) -> str:
    """اگر لازم است، RLM را به ابتدای متن اضافه کن تا پاراگراف راست‌به‌چپ شود.

    فقط زمانی کاری می‌کند که:
      * متن حداقل یک حرف فارسی/عربی داشته باشد، و
      * اولین حرف «قوی» آن لاتین باشد (یعنی Qt پاراگراف را چپ‌به‌راست می‌چیند).

    متنی که از قبل با RLM شروع شود، یا متنی که فقط لاتین/عدد است، دست
    نمی‌خورد (مثلاً خروجی گزارش تحلیل باید چپ‌به‌راست بماند).
    """
    if not text or text[0] == RLM:
        return text
    if not has_persian(text):
        return text
    if first_strong_direction(text) != "ltr":
        return text
    return RLM + text


def rtl_safe(text: str) -> str:
    """نسخهٔ راست‌به‌چپ‌شدهٔ متن (نام کوتاه‌تر برای استفاده در کد رابط)."""
    return ensure_rtl_text(text)
