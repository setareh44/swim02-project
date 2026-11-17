# -*- coding: utf-8 -*-
"""تست‌های منطق «درباره نرم‌افزار»، تاریخ شمسی و پرونده شناگر.

این ماژول‌ها عمداً به Qt وابسته نیستند تا بدون نمایشگر هم تست شوند.
"""
from __future__ import annotations

import datetime as dt

from app import about_info as AI
from app import prefs
from app.jalali import fa_digits, jalali_long, jalali_str, to_jalali
from app.swimmer import GENDERS, SwimmerProfile


# ------------------------------------------------------------------- تاریخ
def test_jalali_known_dates():
    assert to_jalali(dt.date(2026, 3, 21)) == (1405, 1, 1)     # نوروز ۱۴۰۵
    assert to_jalali(dt.date(2024, 3, 20)) == (1403, 1, 1)     # نوروز ۱۴۰۳
    assert to_jalali(dt.date(2026, 10, 29)) == (1405, 8, 7)


def test_jalali_strings_use_persian_digits():
    s = jalali_str(dt.date(2026, 10, 29))
    assert s == "۱۴۰۵/۰۸/۰۷"
    assert all(ch not in s for ch in "0123456789")
    assert jalali_long(dt.date(2026, 10, 29)) == "۷ آبان ۱۴۰۵"


def test_year_never_decreases():
    """سال شمسی همیشه بزرگ‌تر از ۱۳۹۰ است (شکست در تبدیل اشتباه)."""
    for year in (2020, 2024, 2026, 2030):
        jy, jm, jd = to_jalali(dt.date(year, 6, 15))
        assert jy >= 1390
        assert 1 <= jm <= 12
        assert 1 <= jd <= 31


def test_fa_digits():
    assert fa_digits("1.46 m/s") == "۱.۴۶ m/s"


# ------------------------------------------------------------------ درباره
def test_about_identity():
    assert AI.APP_NAME == "Setargan-Darya"
    assert AI.APP_NAME_FA == "ستارگان دریا"
    assert AI.AUTHOR == "Setareh"
    assert AI.AUTHOR_FA == "ستاره"
    assert AI.COPYRIGHT_HOLDER == "Setareh"
    assert "انحصار" in AI.LICENSE_NAME or "حق" in AI.LICENSE_NAME
    assert AI.APP_VERSION.count(".") == 2


def test_about_year_is_current():
    today = dt.date(2026, 10, 29)
    assert AI.year_label(today) == "۱۴۰۵ / ۲۰۲۶"
    assert "۱۴۰۵" in AI.copyright_line(today)
    # سال واقعی سیستم هم باید شمسی باشد، نه میلادی
    assert AI.build_year() > 1400


def test_about_has_purpose_and_texts():
    assert len(AI.PURPOSE) > 120
    assert len(AI.GOALS) >= 3
    assert len(AI.FEATURES) >= 6
    blocks = dict(AI.about_text_blocks(dt.date(2026, 10, 29)))
    assert "هدف نرم‌افزار" in blocks
    assert blocks["سازنده"] == "Setareh"
    assert "۱۴۰۵" in blocks["سال ساخت"]


def test_about_mentions_the_credits():
    names = " ".join(t for t, _ in AI.CREDITS)
    assert "MediaPipe" in names or any("MediaPipe" in d for _, d in AI.CREDITS)
    assert any("Qt" in d for _, d in AI.CREDITS)


# ------------------------------------------------------------ پرونده شناگر
def test_profile_rows_skip_empty_fields():
    p = SwimmerProfile(name="ستایش محمدی", club="", coach="مربی رضایی")
    rows = dict(p.rows())
    assert rows["نام و نام خانوادگی"] == "ستایش محمدی"
    assert rows["مربی"] == "مربی رضایی"
    assert "باشگاه / تیم" not in rows


def test_profile_units_are_persian_friendly():
    p = SwimmerProfile(pool_length="۲۵", height="۱٫۷۲", age="۱۸")
    rows = dict(p.rows())
    assert rows["طول استخر"] == "۲۵ متر"
    assert rows["قد"] == "۱٫۷۲ متر"
    assert rows["سن"] == "۱۸ سال"


def test_profile_roundtrip_and_defaults():
    p = SwimmerProfile(name="علی", gender=GENDERS[2], session_no="۴")
    q = SwimmerProfile.from_dict(p.to_dict())
    assert q.name == "علی" and q.session_no == "۴"
    assert SwimmerProfile.from_dict(None).name == ""
    assert SwimmerProfile.from_dict({"bogus": 1}).name == ""
    assert SwimmerProfile().display_name() == "شناگر (بدون نام)"
    assert SwimmerProfile().date  # تاریخ امروز به شمسی


def test_prefs_keys_are_stable():
    assert prefs.KEY_ABOUT_SEEN and prefs.KEY_SOUND and prefs.KEY_PROFILE
    # بدون Qt نباید استثنا بدهد (پیش‌فرض برمی‌گردد)
    assert isinstance(prefs.get_bool(prefs.KEY_SOUND, True), bool)
