# -*- coding: utf-8 -*-
"""تست منطق دوجهته (bidi) — بدون نیاز به Qt.

علت اصلی «چپ‌چین شدن» متن‌های فارسی این است که Qt جهت پاراگراف را از اولین
حرف «قوی» متن می‌گیرد. این تست‌ها همان قاعده را قفل می‌کنند.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.bidi import (RLM, ensure_rtl_text, first_strong_direction,  # noqa: E402
                      has_persian, rtl_safe, strip_marks)


def test_persian_text_is_untouched():
    text = "گزارش تحلیل شناگر"
    assert first_strong_direction(text) == "rtl"
    assert ensure_rtl_text(text) == text


def test_latin_first_persian_sentence_gets_rlm():
    # همان جملهٔ ابتدای پنجرهٔ «درباره» که چپ‌به‌راست چیده می‌شد
    text = "Setargan-Darya برای این ساخته شده که تحلیل بیومکانیک شنا را آسان کند"
    assert first_strong_direction(text) == "ltr"
    fixed = ensure_rtl_text(text)
    assert fixed.startswith(RLM)
    assert strip_marks(fixed) == text


def test_report_meta_line_with_numbers_and_latin_is_fixed():
    text = "٪۱۵ نمای مورب  ·  مدت 17.1 ثانیه  ·  Front Crawl / Freestyle"
    assert first_strong_direction(text) in ("ltr", "rtl")
    fixed = ensure_rtl_text(text)
    if first_strong_direction(text) == "ltr":
        assert fixed.startswith(RLM)


def test_pure_latin_and_numbers_are_untouched():
    for text in ("SPM", "3.7", "00:00 / 00:00", "video.mp4",
                 "[1/6] Estekhraj-e Eskelet (Pose): 50%"):
        assert ensure_rtl_text(text) == text, text


def test_rlm_is_never_added_twice():
    text = "Setargan-Darya برای شنا"
    once = ensure_rtl_text(text)
    assert ensure_rtl_text(once) == once
    assert ensure_rtl_text(once).count(RLM) == 1


def test_punctuation_and_digits_do_not_decide_direction():
    assert first_strong_direction("۱۴۰۵/۰۸/۰۷") is None
    assert first_strong_direction("123 · 456") is None
    assert first_strong_direction("") is None
    assert first_strong_direction("(-)") is None


def test_persian_after_latin_is_still_detected():
    assert first_strong_direction("123 آب") == "rtl"
    assert first_strong_direction("abc آب") == "ltr"


def test_has_persian():
    assert has_persian("شنا")
    assert has_persian("Setargan-Darya شنا")
    assert not has_persian("Setargan-Darya 2026")


def test_strip_marks():
    assert strip_marks(RLM + "سلام") == "سلام"
    assert strip_marks("\u200e" + "abc" + RLM) == "abc"


def test_rtl_safe_is_the_same_helper():
    assert rtl_safe("Setargan-Darya شنا") == ensure_rtl_text("Setargan-Darya شنا")


def test_every_ui_string_with_latin_first_is_handled():
    """متن‌های واقعی برنامه که ممکن است با لاتین شروع شوند."""
    samples = [
        "Setargan-Darya برای این ساخته شده که…",
        "MediaPipe PoseLandmarker و مدل سبک و کامل",
        "PDF در اندازهٔ A4 ساخته می‌شود",
    ]
    for text in samples:
        fixed = ensure_rtl_text(text)
        if first_strong_direction(text) == "ltr":
            assert fixed.startswith(RLM), text
        assert strip_marks(fixed) == text
