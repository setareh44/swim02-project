# -*- coding: utf-8 -*-
"""پرونده شناگر: مشخصاتی که در سرصفحهٔ گزارش و فایل PDF چاپ می‌شود."""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass, field

from .jalali import jalali_str

GENDERS = ("", "زن", "مرد")

EVENTS = ("", "۵۰ متر آزاد", "۱۰۰ متر آزاد", "۲۰۰ متر آزاد",
          "۵۰ متر کرال پشت", "۱۰۰ متر کرال پشت",
          "۵۰ متر پروانه", "۱۰۰ متر پروانه",
          "۵۰ متر قورباغه", "۱۰۰ متر قورباغه",
          "ترکیبی / تمرین تکنیک")

LEVELS = ("", "مبتدی", "متوسط", "پیشرفته", "حرفه‌ای / مسابقاتی")


@dataclass
class SwimmerProfile:
    """اطلاعات پرونده یک شناگر برای یک جلسهٔ تحلیل."""

    name: str = ""
    date: str = field(default_factory=lambda: jalali_str(_dt.date.today()))
    birth_year: str = ""          # سال تولد شمسی، مثلاً «۱۳۸۷»
    age: str = ""
    gender: str = ""
    club: str = ""
    coach: str = ""
    event: str = ""
    level: str = ""
    session_no: str = ""
    pool_length: str = "۲۵"
    height: str = ""
    notes: str = ""

    # ------------------------------------------------------------------
    def display_name(self) -> str:
        return self.name.strip() or "شناگر (بدون نام)"

    def is_empty(self) -> bool:
        """آیا کاربر هیچ چیزی پر نکرده است؟"""
        base = SwimmerProfile()
        data = asdict(self)
        data.pop("date", None)
        base_data = asdict(base)
        base_data.pop("date", None)
        return data == base_data

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "SwimmerProfile":
        if not data:
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: str(v) for k, v in data.items() if k in known})

    def rows(self) -> list[tuple[str, str]]:
        """ردیف‌های غیرخالی برای نمایش در جدول گزارش (برچسب، مقدار)."""
        pairs = [
            ("نام و نام خانوادگی", self.name),
            ("تاریخ", self.date),
            ("سال تولد", self.birth_year),
            ("سن", self.age and "%s سال" % self.age),
            ("جنسیت", self.gender),
            ("باشگاه / تیم", self.club),
            ("مربی", self.coach),
            ("رویداد", self.event),
            ("سطح", self.level),
            ("شماره جلسه", self.session_no),
            ("طول استخر", self.pool_length and "%s متر" % self.pool_length),
            ("قد", self.height and "%s متر" % self.height),
            ("یادداشت", self.notes),
        ]
        return [(k, str(v).strip()) for k, v in pairs if str(v).strip()]
