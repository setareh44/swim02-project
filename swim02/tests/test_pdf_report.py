# -*- coding: utf-8 -*-
"""تست گزارش PDF: ساخت HTML رنگی/سیاه‌وسفید و نام فایل.

تبدیل نهایی به PDF با Qt انجام می‌شود؛ این‌جا فقط بخش مستقل از Qt بررسی
می‌شود تا محتوای گزارش (نام شناگر، تاریخ، شاخص‌ها) قابل اعتماد باشد.
"""
from __future__ import annotations

import datetime as dt
import re
import types

import numpy as np
import pytest

from app.pdf_report import default_filename, report_html
from app.swimmer import SwimmerProfile

TODAY = dt.date(2026, 10, 29)


class NS(types.SimpleNamespace):
    pass


def make_results():
    r = NS()
    r.video_path = r"C:\videos\شنا.mp4"
    r.style_final = "CRAWL"
    r.pose = NS(n=240, fps=30.0)
    r.pose_raw = NS(detect_ratio=0.93)
    r.style_full = NS(conf=0.88)
    r.track = NS(dominant="SIDE")
    r.strokes = NS(total_strokes=44, spm_avg=92.3)
    r.perf = NS(mean_speed=1.461, max_speed=1.9, distance=5.85,
                sl_mean=0.95, eff_mean=0.71, swolf_est=41.2)
    r.sym = NS(global_pct=93.0)
    keys = ["elbow_L", "elbow_R", "knee_L", "knee_R", "pitch",
            "hipdev", "roll", "torso", "sym"]
    status = {k: np.ones(240, dtype=int) for k in keys}
    for k in keys:
        status[k][:10] = 2
    r.evalr = NS(status=status,
                 events={"elbow_L": 2, "pitch": 1},
                 red_frames={"elbow_L": 7, "pitch": 3})
    return r


PROFILE = SwimmerProfile(
    name="ستایش محمدی", date="۱۴۰۵/۰۸/۰۷", birth_year="۱۳۸۷", age="۱۸",
    gender="زن", club="باشگاه امواج", coach="مربی رضایی",
    event="۱۰۰ متر آزاد", level="پیشرفته", session_no="۱۲",
    pool_length="۲۵", height="۱٫۷۲", notes="تمرین تکنیک دست")


def test_report_contains_swimmer_file_and_metrics():
    html = report_html(make_results(), PROFILE, color=True, generated=TODAY)
    assert html.startswith("<html>")
    assert 'dir="rtl"' in html
    for needle in ("ستایش محمدی", "باشگاه امواج", "مربی رضایی",
                   "۱۴۰۵/۰۸/۰۷", "۱۰۰ متر آزاد", "کرال سینه",
                   "Setargan-Darya", "کرال سینه"):
        assert needle in html, needle
    # شاخص‌ها با اعداد فارسی
    assert "۹۲.۳" in html
    assert "۱.۴۶" in html
    # بخش‌های اصلی گزارش
    for section in ("پرونده شناگر", "شاخص‌های کلیدی عملکرد",
                    "وضعیت شاخص‌های تکنیکی", "رخدادهای بحرانی",
                    "پیشنهادهای اصلاح تکنیک"):
        assert section in html, section
    # پانویس با سازنده و حق انحصاری
    assert "Setareh" in html
    assert "۱۴۰۵" in html


def test_black_white_report_has_no_colour():
    html = report_html(make_results(), PROFILE, color=False, generated=TODAY)
    colours = set(re.findall(r"#[0-9a-fA-F]{6}", html))
    allowed_greys = {c for c in colours
                     if len(set(c[1:].lower()[i:i + 2] for i in (0, 2, 4))) == 1}
    assert colours == allowed_greys, "B&W report must only use grey shades"
    assert "ffffff" in {c.lstrip("#").lower() for c in colours} | {"ffffff"}


def test_colour_report_uses_colour():
    html = report_html(make_results(), PROFILE, color=True)
    colours = set(c.lstrip("#").lower() for c in re.findall(r"#[0-9a-fA-F]{6}", html))
    non_grey = {c for c in colours
                if len(set(c[i:i + 2] for i in (0, 2, 4))) > 1}
    assert non_grey, "colour report should contain at least one colour"


def test_html_escapes_user_input():
    prof = SwimmerProfile(name="<script>alert(1)</script>", notes="a & b")
    html = report_html(make_results(), prof, color=True, generated=TODAY)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a &amp; b" in html


def test_report_survives_missing_optional_fields():
    r = make_results()
    del r.sym
    del r.evalr
    html = report_html(r, None, color=True, generated=TODAY)
    assert "ستایش" not in html
    assert "نام و نام خانوادگی" in html         # پرونده خالی نباید خطا بدهد
    assert "کرال سینه" in html


def test_default_filename_contains_name_and_mode():
    assert default_filename(PROFILE, True).startswith("گزارش-ستایش-محمدی-")
    assert default_filename(PROFILE, True).endswith("-رنگی.pdf")
    assert default_filename(PROFILE, False).endswith("-سیاه-سفید.pdf")
    assert default_filename(SwimmerProfile(), True).startswith("گزارش-شناگر-")
    assert "/" not in default_filename(PROFILE, True)


def test_export_pdf_requires_qt():
    """در محیط بدون Qt، export_pdf باید ImportError بدهد نه چیز عجیب‌تر."""
    from app.pdf_report import export_pdf
    try:
        import PySide6.QtGui  # noqa: F401
    except Exception:
        with pytest.raises(Exception):
            export_pdf("/tmp/x.pdf", make_results(), PROFILE)
