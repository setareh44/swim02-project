# -*- coding: utf-8 -*-
"""Coach-assigned dry-land / in-pool workout plans and diet/meal plans.

Storage (Qt-free JSON)::

    <data_dir>/plans/<athlete_id>.json   {"workouts": [...], "meals": [...]}

Templates give the coach a one-click starting point per style and level;
every template can be customised before/after assignment.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .auth import alog, data_dir, utcnow_iso

PLANS_DIR = "plans"


# ---------------------------------------------------------------------------
@dataclass
class WorkoutPlan:
    plan_id: str
    athlete_id: str
    title: str
    style_focus: str = "CRAWL"
    level: str = "beginner"
    sessions_per_week: int = 3
    items: List[Dict[str, str]] = field(default_factory=list)
    assigned_at: str = ""
    assigned_by: str = "ADMIN"
    done: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WorkoutPlan":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in (data or {}).items() if k in known}
        obj = cls(plan_id=str(clean.get("plan_id", "")),
                  athlete_id=str(clean.get("athlete_id", "")),
                  title=str(clean.get("title", "")))
        for key, val in clean.items():
            if key in ("plan_id", "athlete_id", "title"):
                continue
            try:
                if key == "sessions_per_week":
                    setattr(obj, key, max(1, int(val or 1)))
                elif key == "done":
                    setattr(obj, key, bool(val))
                elif key == "items":
                    rows = []
                    for row in (val or []):
                        if isinstance(row, dict):
                            rows.append({"title": str(row.get("title", "")),
                                         "detail": str(row.get("detail", ""))})
                        else:
                            rows.append({"title": str(row), "detail": ""})
                    setattr(obj, key, rows)
                else:
                    setattr(obj, key, val)
            except (TypeError, ValueError):
                continue
        return obj


@dataclass
class MealPlan:
    plan_id: str
    athlete_id: str
    title: str
    goal: str = "general"
    meals: Dict[str, str] = field(default_factory=dict)
    hydration_note: str = ""
    assigned_at: str = ""
    assigned_by: str = "ADMIN"
    done: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MealPlan":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in (data or {}).items() if k in known}
        obj = cls(plan_id=str(clean.get("plan_id", "")),
                  athlete_id=str(clean.get("athlete_id", "")),
                  title=str(clean.get("title", "")))
        for key, val in clean.items():
            if key in ("plan_id", "athlete_id", "title"):
                continue
            try:
                if key == "meals":
                    setattr(obj, key, {str(k): str(v) for k, v in
                                       (val or {}).items()})
                elif key == "done":
                    setattr(obj, key, bool(val))
                else:
                    setattr(obj, key, val)
            except (TypeError, ValueError):
                continue
        return obj


# ---------------------------------------------------------------------------
class PlanStore:
    """Assign / list / update / delete workout and meal plans per athlete."""

    def __init__(self, root: Optional[str] = None):
        self.root = root or os.path.join(data_dir(), PLANS_DIR)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, athlete_id: str) -> str:
        safe = "".join(c for c in str(athlete_id) if c.isalnum() or c in "-_")
        return os.path.join(self.root, (safe or "unknown") + ".json")

    def _read(self, athlete_id: str) -> dict:
        path = self._path(athlete_id)
        if not os.path.isfile(path):
            return {"workouts": [], "meals": []}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {"workouts": data.get("workouts") or [],
                        "meals": data.get("meals") or []}
        except (OSError, ValueError):
            pass
        return {"workouts": [], "meals": []}

    def _write(self, athlete_id: str, payload: dict) -> None:
        path = self._path(athlete_id)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except OSError as exc:
            alog("Hoshdar: zakhire plan namovafagh bood: %s" % exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _new_id(self, prefix: str) -> str:
        stamp = utcnow_iso().replace(":", "").replace("+", "z")
        return "%s-%s" % (prefix, stamp)

    # -- workouts ---------------------------------------------------------
    def assign_workout(self, athlete_id: str, title: str,
                       items: Optional[List[Dict[str, str]]] = None,
                       style_focus: str = "CRAWL", level: str = "beginner",
                       sessions_per_week: int = 3, notes: str = "",
                       assigned_by: str = "ADMIN") -> WorkoutPlan:
        plan = WorkoutPlan(
            plan_id=self._new_id("W"), athlete_id=athlete_id, title=title,
            style_focus=style_focus, level=level,
            sessions_per_week=max(1, int(sessions_per_week)),
            items=list(items or []), assigned_at=utcnow_iso(),
            assigned_by=assigned_by, notes=notes)
        payload = self._read(athlete_id)
        payload["workouts"].append(plan.to_dict())
        self._write(athlete_id, payload)
        alog("Workout plan sakhte shod: %s / %s" % (athlete_id, plan.plan_id))
        return plan

    def workouts(self, athlete_id: str) -> List[WorkoutPlan]:
        return [WorkoutPlan.from_dict(d) for d in
                self._read(athlete_id)["workouts"] if isinstance(d, dict)]

    def set_workout_done(self, athlete_id: str, plan_id: str,
                         done: bool = True) -> bool:
        payload = self._read(athlete_id)
        changed = False
        for d in payload["workouts"]:
            if isinstance(d, dict) and d.get("plan_id") == plan_id:
                d["done"] = bool(done)
                changed = True
        if changed:
            self._write(athlete_id, payload)
        return changed

    def remove_workout(self, athlete_id: str, plan_id: str) -> bool:
        payload = self._read(athlete_id)
        before = len(payload["workouts"])
        payload["workouts"] = [d for d in payload["workouts"]
                               if not (isinstance(d, dict) and
                                       d.get("plan_id") == plan_id)]
        if len(payload["workouts"]) != before:
            self._write(athlete_id, payload)
            return True
        return False

    # -- meals ------------------------------------------------------------
    def assign_meal(self, athlete_id: str, title: str,
                    meals: Optional[Dict[str, str]] = None,
                    goal: str = "general", hydration_note: str = "",
                    notes: str = "", assigned_by: str = "ADMIN") -> MealPlan:
        plan = MealPlan(
            plan_id=self._new_id("M"), athlete_id=athlete_id, title=title,
            goal=goal, meals=dict(meals or {}),
            hydration_note=hydration_note, assigned_at=utcnow_iso(),
            assigned_by=assigned_by, notes=notes)
        payload = self._read(athlete_id)
        payload["meals"].append(plan.to_dict())
        self._write(athlete_id, payload)
        alog("Meal plan sakhte shod: %s / %s" % (athlete_id, plan.plan_id))
        return plan

    def meals(self, athlete_id: str) -> List[MealPlan]:
        return [MealPlan.from_dict(d) for d in
                self._read(athlete_id)["meals"] if isinstance(d, dict)]

    def set_meal_done(self, athlete_id: str, plan_id: str,
                      done: bool = True) -> bool:
        payload = self._read(athlete_id)
        changed = False
        for d in payload["meals"]:
            if isinstance(d, dict) and d.get("plan_id") == plan_id:
                d["done"] = bool(done)
                changed = True
        if changed:
            self._write(athlete_id, payload)
        return changed

    def remove_meal(self, athlete_id: str, plan_id: str) -> bool:
        payload = self._read(athlete_id)
        before = len(payload["meals"])
        payload["meals"] = [d for d in payload["meals"]
                            if not (isinstance(d, dict) and
                                    d.get("plan_id") == plan_id)]
        if len(payload["meals"]) != before:
            self._write(athlete_id, payload)
            return True
        return False


# ---------------------------------------------------------------------------
# coach templates (FA for the UI; `finglish` one-liner for the CLI)
# ---------------------------------------------------------------------------
WORKOUT_TEMPLATES: Dict[str, dict] = {
    "crawl-elbow": {
        "title": "اصلاح افتادگی آرنج (کرال سینه)",
        "finglish": "high-elbow catch drills",
        "style_focus": "CRAWL",
        "sessions_per_week": 3,
        "items": [
            {"title": "اسکالینگ جلوی شانه",
             "detail": "۶×۵۰ متر؛ فشار آب به بیرون/داخل با آرنج بالا."},
            {"title": "کشش آرنج‌بالا با تخته",
             "detail": "۸×۲۵ متر؛ عبور آرنج از بالای سطح دست."},
            {"title": "Finger-Tip Drag",
             "detail": "۴×۵۰ متر؛ کشیدن نوک انگشتان روی آب در ریکاوری."},
            {"title": "پلانک + پارو با کش",
             "detail": "خشکی: ۳ ست ۴۵ ثانیه پلانک + ۳×۱۵ پارو."},
        ],
    },
    "crawl-body": {
        "title": "بهبود موقعیت بدن (کرال سینه)",
        "finglish": "body-position drills",
        "style_focus": "CRAWL",
        "sessions_per_week": 3,
        "items": [
            {"title": "شنا با نگاه به کف استخر",
             "detail": "۴×۱۰۰ متر آرام؛ سر ثابت، لگن بالا."},
            {"title": "ضربه پا با تخته",
             "detail": "۶×۵۰ متر؛ ضربه از لگن، نه از زانو."},
            {"title": "Side-Kick Drill",
             "detail": "۸×۲۵ متر هر سمت؛ بدن کشیده روی پهلو."},
            {"title": "تقویت هسته",
             "detail": "خشکی: ددباگ ۳×۱۲ + سوپرمن ۳×۳۰ ثانیه."},
        ],
    },
    "back-rhythm": {
        "title": "ریتم و چرخش شانه (کرال پشت)",
        "finglish": "backstroke rotation rhythm",
        "style_focus": "BACK",
        "sessions_per_week": 3,
        "items": [
            {"title": "شانه‌به‌شانه (6-Kick Switch)",
             "detail": "۸×۲۵ متر؛ مکث ۶ ضربه پا بین هر کشش."},
            {"title": "تک‌دست کرال پشت",
             "detail": "۶×۵۰ متر؛ تمرکز بر ورود دست بالای شانه."},
            {"title": "ضربه پای دلفین به پشت",
             "detail": "۴×۲۵ متر زیر آب؛ موج از سینه."},
        ],
    },
    "breast-timing": {
        "title": "تایمینگ کشش و پا (قورباغه)",
        "finglish": "breaststroke pull-kick timing",
        "style_focus": "BREAST",
        "sessions_per_week": 3,
        "items": [
            {"title": "پا قورباغه با تخته",
             "detail": "۸×۵۰ متر؛ پاشنه به باسن، کف پا به بیرون."},
            {"title": "کشش + مکث سرش (Glide)",
             "detail": "۶×۵۰ متر؛ بعد از هر ضربه ۲ ثانیه سر خوردن."},
            {"title": "۲ پا + ۱ کشش",
             "detail": "۴×۵۰ متر؛ هماهنگی ریتم دست و پا."},
        ],
    },
    "fly-wave": {
        "title": "موج بدن و ریکاوری (پروانه)",
        "finglish": "butterfly body-wave drills",
        "style_focus": "FLY",
        "sessions_per_week": 3,
        "items": [
            {"title": "موج بدن با تخته",
             "detail": "۶×۲۵ متر؛ موج از سینه تا نوک پا."},
            {"title": "تک‌دست پروانه",
             "detail": "۸×۲۵ متر هر دست؛ ریکاوری ریلکس روی آب."},
            {"title": "۳+۱ (سه ضربه + یک کامل)",
             "detail": "۴×۵۰ متر؛ حفظ ریتم تنفس رو به جلو."},
        ],
    },
    "dryland-core": {
        "title": "بدنسازی خشکی عمومی شناگران",
        "finglish": "general dry-land strength",
        "style_focus": "CRAWL",
        "sessions_per_week": 2,
        "items": [
            {"title": "کشش بارفیکس / لت",
             "detail": "۴ ست تا ناتوانی؛ استراحت ۹۰ ثانیه."},
            {"title": "شنا سوئدی + ددلیفت رومانیایی",
             "detail": "۳×۱۵ سوئدی + ۳×۱۰ ددلیفت سبک."},
            {"title": "مدیسن‌بال چرخشی",
             "detail": "۳×۲۰ پرتاب چرخشی هر سمت (چرخش تنه)."},
        ],
    },
}

MEAL_TEMPLATES: Dict[str, dict] = {
    "general": {
        "title": "رژیم پایه شناگر",
        "finglish": "base swimmer diet",
        "goal": "general",
        "meals": {
            "صبحانه": "جو دوسر با شیر + موز + ۱۰ عدد بادام",
            "ناهار": "برنج + مرغ/ماهی + سالاد + ماست",
            "میان‌وعده قبل تمرین": "موز + خرما (۶۰ دقیقه قبل)",
            "شام": "تخم‌مرغ/عدسی + نان سبوس‌دار + سبزیجات",
        },
        "hydration_note": "۲ تا ۳ لیتر آب در روز + ۵۰۰ میلی‌لیتر حین تمرین.",
    },
    "race-week": {
        "title": "هفته مسابقه (بارگیری کربوهیدرات)",
        "finglish": "race-week carb loading",
        "goal": "race",
        "meals": {
            "صبحانه": "پنکیک + عسل + آب پرتقال",
            "ناهار": "پاستا + مرغ کم‌چرب + آبمیوه",
            "میان‌وعده": "برنجک + موز + نوشیدنی ورزشی",
            "شام": "برنج + ماهی + سیب‌زمینی",
        },
        "hydration_note": "نوشیدنی الکترولیت از ۴۸ ساعت قبل از مسابقه.",
    },
    "lean": {
        "title": "کاهش وزن کنترل‌شده",
        "finglish": "controlled lean-out",
        "goal": "lean",
        "meals": {
            "صبحانه": "سفیده تخم‌مرغ + نان جو + گوجه",
            "ناهار": "مرغ گریل + کینوا/برنج کم + سالاد زیاد",
            "میان‌وعده": "ماست یونانی + گردو (کم)",
            "شام": "سوپ سبزیجات + ماهی",
        },
        "hydration_note": "آب کافی؛ حذف نوشابه و آبمیوه صنعتی.",
    },
}
