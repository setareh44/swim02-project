# -*- coding: utf-8 -*-
"""تبدیل تاریخ میلادی به شمسی و اعداد فارسی — بدون وابستگی بیرونی."""
from __future__ import annotations

import datetime as _dt

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
           "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
_WEEKDAYS = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه",
             "جمعه", "شنبه", "یکشنبه")


def fa_digits(text) -> str:
    """۰۱۲۳۴۵۶۷۸۹ به‌جای 0123456789."""
    return str(text).translate(_FA_DIGITS)


def to_jalali(date: _dt.date) -> tuple[int, int, int]:
    """(سال، ماه، روز) شمسی برای یک تاریخ میلادی."""
    gy, gm, gd = date.year, date.month, date.day
    g_days_in_month = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)

    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = (365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100
                + (gy2 + 399) // 400)
    g_day_no += g_days_in_month[gm2] + gd2
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    for i in range(11):
        month_len = 31 if i < 6 else 30
        if j_day_no < month_len:
            return jy, i + 1, j_day_no + 1
        j_day_no -= month_len
    return jy, 12, j_day_no + 1


def jalali_str(date: _dt.date | None = None, with_weekday: bool = False) -> str:
    """«۱۴۰۵/۰۸/۰۷» — با اعداد فارسی و آمادهٔ نمایش در گزارش."""
    day = date or _dt.date.today()
    jy, jm, jd = to_jalali(day)
    out = "%04d/%02d/%02d" % (jy, jm, jd)
    if with_weekday:
        out += "  " + _WEEKDAYS[day.weekday()]
    return fa_digits(out)


def jalali_long(date: _dt.date | None = None) -> str:
    """«۷ آبان ۱۴۰۵»."""
    day = date or _dt.date.today()
    jy, jm, jd = to_jalali(day)
    return fa_digits("%d %s %d" % (jd, _MONTHS[jm - 1], jy))


def today_str() -> str:
    return jalali_str(_dt.date.today())
