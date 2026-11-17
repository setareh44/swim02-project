# -*- coding: utf-8 -*-
"""صفحه پرونده شناگر: مشخصات، برنامه‌ها، تاریخچه و پیام انگیزشی."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..audio import AudioService
from ..auth import Session, SKILL_FA, User
from ..history import HistoryStore, ProgressTracker
from ..plans import PlanStore
from ..theme import C
from ..toast import notify
from ..widgets import card, KpiTile, SectionHeader


def _lab(text: str, obj: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setAlignment(Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter)
    lab.setWordWrap(True)
    if obj:
        lab.setObjectName(obj)
    return lab


class AthletePage(QWidget):
    """Athlete dashboard (own profile, plans, history, quote)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user: Optional[User] = None
        self._history = HistoryStore()
        self._plans = PlanStore()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("pageScroll")
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setSpacing(14)

        self.lay.addWidget(SectionHeader("پرونده شناگر", "user"))
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        self.lay.addLayout(self.grid)
        self._cards: list = []

    # ------------------------------------------------------------------
    def refresh(self, session: Optional[Session],
                auth=None) -> None:
        """Rebuild the page for the logged-in athlete (or chosen athlete)."""
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        user = None
        if session is not None and session.is_athlete and auth is not None:
            user = auth.store.get(session.user_id)
        if user is None:
            f, lay = card()
            lay.addWidget(_lab("برای دیدن پرونده، با PIN شناگر وارد شوید."))
            self.lay.addWidget(f)
            self._cards.append(f)
            return
        self._user = user
        uid = user.user_id
        summaries = self._history.list(uid)
        tracker = ProgressTracker(summaries)

        # KPI row
        last = summaries[-1] if summaries else None
        kpis = [
            ("جلسات ثبت‌شده", str(len(summaries)), "", "report", C.CYAN),
            ("آخرین SWOLF",
             "%.1f" % last.swolf if last and last.swolf else "—",
             "", "gauge", C.TEAL),
            ("آخرین SPM",
             "%.1f" % last.spm if last and last.spm else "—",
             "", "wave", C.BLUE),
            ("روند کلی",
             {"improving": "رو به بهبود ↑", "declining": "نیازمند توجه ↓",
              "stable": "ثابت →"}[tracker.overall()] if summaries else "—",
             "", "chart",
             {"improving": C.GREEN, "declining": C.RED,
              "stable": C.YELLOW}[tracker.overall()] if summaries else C.MUTED),
        ]
        for i, (t, v, u, ic, ac) in enumerate(kpis):
            self.grid.addWidget(KpiTile(t, v, u, ic, ac), 0, i)

        # profile + progress
        f, lay = card()
        lay.addWidget(SectionHeader("مشخصات", "user"))
        lay.addWidget(_lab("نام: %s" % user.name))
        lay.addWidget(_lab("شناسه: %s" % user.user_id))
        lay.addWidget(_lab("سن: %s" % (user.age or "—")))
        lay.addWidget(_lab("سابقه: %s سال" % user.experience_years))
        lay.addWidget(_lab("سطح: %s" % SKILL_FA.get(user.skill_tier, "")))
        self.lay.addWidget(f)
        self._cards.append(f)

        f, lay = card()
        lay.addWidget(SectionHeader("روند پیشرفت", "chart"))
        lay.addWidget(_lab(tracker.report_text_fa()))
        self.lay.addWidget(f)
        self._cards.append(f)

        # workouts
        f, lay = card()
        lay.addWidget(SectionHeader("برنامه‌های تمرینی من", "report"))
        workouts = self._plans.workouts(uid)
        if not workouts:
            lay.addWidget(_lab("هنوز برنامه‌ای از طرف مربی ثبت نشده است.",
                               "muted"))
        for plan in workouts:
            row = QHBoxLayout()
            chk = QCheckBox("انجام شد")
            chk.setLayoutDirection(Qt.RightToLeft)
            chk.setChecked(plan.done)
            chk.toggled.connect(
                lambda on, p=plan: self._mark_workout(p.plan_id, on))
            title = _lab("🏋 %s (%s جلسه در هفته)%s" % (
                plan.title, plan.sessions_per_week,
                " ✓" if plan.done else ""))
            title.setStyleSheet("font-weight:700;")
            row.addWidget(title, 1)
            row.addWidget(chk)
            lay.addLayout(row)
            for item in plan.items:
                lay.addWidget(_lab("• %s — %s" % (item["title"],
                                                 item["detail"]), "muted"))
            if plan.notes:
                lay.addWidget(_lab("یادداشت مربی: %s" % plan.notes, "faint"))
        self.lay.addWidget(f)
        self._cards.append(f)

        # meals
        f, lay = card()
        lay.addWidget(SectionHeader("برنامه‌های غذایی من", "report"))
        meals = self._plans.meals(uid)
        if not meals:
            lay.addWidget(_lab("هنوز برنامه غذایی ثبت نشده است.", "muted"))
        for plan in meals:
            row = QHBoxLayout()
            chk = QCheckBox("انجام شد")
            chk.setLayoutDirection(Qt.RightToLeft)
            chk.setChecked(plan.done)
            chk.toggled.connect(
                lambda on, p=plan: self._mark_meal(p.plan_id, on))
            title = _lab("🥗 %s%s" % (plan.title, " ✓" if plan.done else ""))
            title.setStyleSheet("font-weight:700;")
            row.addWidget(title, 1)
            row.addWidget(chk)
            lay.addLayout(row)
            for name, desc in plan.meals.items():
                lay.addWidget(_lab("• %s: %s" % (name, desc), "muted"))
            if plan.hydration_note:
                lay.addWidget(_lab("💧 %s" % plan.hydration_note, "faint"))
        self.lay.addWidget(f)
        self._cards.append(f)

        # history
        f, lay = card()
        lay.addWidget(SectionHeader("تاریخچه تحلیل‌ها", "report"))
        if not summaries:
            lay.addWidget(_lab("هنوز تحلیلی ثبت نشده است.", "muted"))
        for s in reversed(summaries[-12:]):
            lay.addWidget(_lab(
                "📅 %s — سبک %s | SPM %s | SWOLF %s | سرعت %s | تقارن %s%%" % (
                    s.date_iso[:10], s.style or "—",
                    "%.1f" % s.spm if s.spm else "—",
                    "%.1f" % s.swolf if s.swolf else "—",
                    "%.2f" % s.mean_speed if s.mean_speed else "—",
                    "%.0f" % s.symmetry if s.symmetry else "—"),
                "muted"))
        self.lay.addWidget(f)
        self._cards.append(f)

    # ------------------------------------------------------------------
    def show_quote_card(self, quote_fa: str, personal_fa: str,
                        speak_text: str) -> None:
        f, lay = card()
        lay.addWidget(SectionHeader("پیام انگیزشی امروز", "info"))
        q = _lab("«%s»" % quote_fa)
        q.setStyleSheet("font-size:15px; color:%s;" % C.CYAN)
        lay.addWidget(q)
        lay.addWidget(_lab(personal_fa, "muted"))
        btn = QPushButton("🔊 خواندن با صدا")
        btn.setObjectName("ghost")
        btn.clicked.connect(lambda: AudioService().speak(speak_text))
        lay.addWidget(btn, 0, Qt.AlignLeft)
        self.lay.insertWidget(1, f)
        self._cards.append(f)

    def _mark_workout(self, plan_id: str, on: bool) -> None:
        if self._user and self._plans.set_workout_done(self._user.user_id,
                                                       plan_id, on):
            notify(self, "وضعیت برنامه تمرینی ثبت شد", "success", 1800)

    def _mark_meal(self, plan_id: str, on: bool) -> None:
        if self._user and self._plans.set_meal_done(self._user.user_id,
                                                    plan_id, on):
            notify(self, "وضعیت برنامه غذایی ثبت شد", "success", 1800)
