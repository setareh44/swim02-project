# -*- coding: utf-8 -*-
"""Daily diet/workout compliance tracker (Qt-free).

Each student submits one entry per day from their panel::

    <data_dir>/compliance/<athlete_id>.json   {"entries": [...]}

An entry records whether the prescribed diet and workout were followed
(Yes/No) plus an optional short note. Every submit also notifies the
coach through :mod:`app.messaging` (see :class:`ComplianceNotifier`).

Dates are local calendar days (``YYYY-MM-DD``) - a "day" means the day
on the student's own machine.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from .auth import alog, data_dir

COMPLIANCE_DIR = "compliance"


def today_iso() -> str:
    return date.today().isoformat()


@dataclass
class ComplianceEntry:
    day: str                       # YYYY-MM-DD (local)
    diet_done: bool = False
    workout_done: bool = False
    note: str = ""
    submitted_at: str = ""
    source: str = "app"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ComplianceEntry":
        data = data or {}
        try:
            datetime.strptime(str(data.get("day", "")), "%Y-%m-%d")
            day = str(data["day"])
        except (ValueError, TypeError):
            day = today_iso()
        return cls(day=day,
                   diet_done=bool(data.get("diet_done")),
                   workout_done=bool(data.get("workout_done")),
                   note=str(data.get("note", "") or "")[:500],
                   submitted_at=str(data.get("submitted_at", "") or ""),
                   source=str(data.get("source", "") or "app"))

    @property
    def full_day(self) -> bool:
        return self.diet_done and self.workout_done


class ComplianceStore:
    """Per-student archive of daily compliance entries."""

    def __init__(self, root: Optional[str] = None):
        self.root = root or os.path.join(data_dir(), COMPLIANCE_DIR)
        os.makedirs(self.root, exist_ok=True)

    # -- persistence ------------------------------------------------------
    def _path(self, athlete_id: str) -> str:
        safe = "".join(c for c in str(athlete_id) if c.isalnum() or c in "-_")
        return os.path.join(self.root, (safe or "unknown") + ".json")

    def _read(self, athlete_id: str) -> List[ComplianceEntry]:
        path = self._path(athlete_id)
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        items = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [ComplianceEntry.from_dict(d) for d in items
                if isinstance(d, dict)]

    def _write(self, athlete_id: str, entries: List[ComplianceEntry]) -> None:
        path = self._path(athlete_id)
        tmp = path + ".tmp"
        payload = {"entries": [e.to_dict() for e in
                               sorted(entries, key=lambda x: x.day)]}
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except OSError as exc:
            alog("Hoshdar: zakhire compliance namovafagh bood: %s" % exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    # -- CRUD -------------------------------------------------------------
    def submit(self, athlete_id: str, diet_done: bool, workout_done: bool,
               note: str = "", day: Optional[str] = None) -> ComplianceEntry:
        """Create or replace the entry for ``day`` (default: today)."""
        day = day or today_iso()
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError("Rooze namotabar: %s" % day)
        entries = [e for e in self._read(athlete_id) if e.day != day]
        entry = ComplianceEntry(
            day=day, diet_done=bool(diet_done),
            workout_done=bool(workout_done),
            note=str(note or "").strip()[:500],
            submitted_at=datetime.now().isoformat(timespec="seconds"))
        entries.append(entry)
        # keep the file bounded: two years of daily entries is plenty
        entries = sorted(entries, key=lambda x: x.day)[-730:]
        self._write(athlete_id, entries)
        alog("Gozaresh-e roozane sabt shod: %s / %s (diet=%s, workout=%s)"
             % (athlete_id, day, entry.diet_done, entry.workout_done))
        return entry

    def get_day(self, athlete_id: str, day: Optional[str] = None):
        day = day or today_iso()
        for e in self._read(athlete_id):
            if e.day == day:
                return e
        return None

    def history(self, athlete_id: str,
                days: int = 30) -> List[ComplianceEntry]:
        entries = sorted(self._read(athlete_id), key=lambda x: x.day)
        return entries[-max(1, days):]

    # -- analytics --------------------------------------------------------
    def _by_day(self, athlete_id: str) -> Dict[str, ComplianceEntry]:
        return {e.day: e for e in self._read(athlete_id)}

    def streak(self, athlete_id: str, kind: str = "both") -> int:
        """Consecutive compliant days ending today (or yesterday if today
        is not submitted yet). ``kind``: both / diet / workout."""
        table = self._by_day(athlete_id)
        if kind not in ("both", "diet", "workout"):
            kind = "both"

        def ok(entry) -> bool:
            if entry is None:
                return False
            if kind == "diet":
                return entry.diet_done
            if kind == "workout":
                return entry.workout_done
            return entry.full_day

        cursor = date.today()
        if not ok(table.get(cursor.isoformat())):
            cursor -= timedelta(days=1)     # today still open: start yesterday
        count = 0
        while ok(table.get(cursor.isoformat())):
            count += 1
            cursor -= timedelta(days=1)
        return count

    def week_rate(self, athlete_id: str) -> Dict[str, float]:
        """Compliance % over the last 7 days (diet / workout / both)."""
        table = self._by_day(athlete_id)
        days = [(date.today() - timedelta(days=i)).isoformat()
                for i in range(7)]
        diet = sum(1 for d in days
                   if table.get(d) is not None and table[d].diet_done)
        work = sum(1 for d in days
                   if table.get(d) is not None and table[d].workout_done)
        both = sum(1 for d in days
                   if table.get(d) is not None and table[d].full_day)
        return {"diet": 100.0 * diet / 7, "workout": 100.0 * work / 7,
                "both": 100.0 * both / 7, "submitted": sum(
                    1 for d in days if d in table)}

    # -- human-readable summaries -----------------------------------------
    def summary_fa(self, athlete_id: str) -> str:
        rate = self.week_rate(athlete_id)
        return ("رکورد روزهای کامل: %d روز | هفته اخیر: رژیم %.0f%%، تمرین %.0f%% "
                "(%d روز ثبت‌شده)" % (
                    self.streak(athlete_id), rate["diet"], rate["workout"],
                    int(rate["submitted"])))

    def summary_finglish(self, athlete_id: str) -> str:
        rate = self.week_rate(athlete_id)
        return ("streak=%d, week: diet=%.0f%% workout=%.0f%% (%d/7 submitted)"
                % (self.streak(athlete_id), rate["diet"], rate["workout"],
                   int(rate["submitted"])))
