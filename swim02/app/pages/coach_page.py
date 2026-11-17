# -*- coding: utf-8 -*-
"""پنل مربی/مدیر: مدیریت شناگران، تاریخچه، روند و تخصیص برنامه."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QSplitter, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget)

from ..auth import AuthError, AuthService, Session, SKILL_FA, SKILL_TIERS, User
from ..compliance import ComplianceStore
from ..history import HistoryStore, ProgressTracker
from ..messaging import MessageStore
from ..plans import (MEAL_TEMPLATES, PlanStore, WORKOUT_TEMPLATES,
                     WorkoutPlan, MealPlan)
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


# ---------------------------------------------------------------------------
class AthleteFormDialog(QDialog):
    """Add / edit athlete (name, age, experience, skill, PIN for new)."""

    def __init__(self, user: Optional[User] = None, parent=None):
        super().__init__(parent)
        self._user = user
        self.setWindowTitle("ویرایش شناگر" if user else "شناگر جدید")
        self.setModal(True)
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        form.setSpacing(10)
        self.ed_name = QLineEdit(user.name if user else "")
        self.ed_name.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        self.sp_age = QSpinBox()
        self.sp_age.setRange(0, 100)
        self.sp_age.setValue(user.age if user else 0)
        self.sp_age.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        self.sp_exp = QDoubleSpinBox()
        self.sp_exp.setRange(0, 60)
        self.sp_exp.setSingleStep(0.5)
        self.sp_exp.setValue(user.experience_years if user else 0.0)
        self.sp_exp.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        self.cmb_skill = QComboBox()
        self.cmb_skill.setLayoutDirection(Qt.RightToLeft)
        for tier in SKILL_TIERS:
            self.cmb_skill.addItem(SKILL_FA[tier], tier)
        if user:
            idx = self.cmb_skill.findData(user.skill_tier)
            if idx >= 0:
                self.cmb_skill.setCurrentIndex(idx)
        form.addRow(_lab("نام و نام خانوادگی:"), self.ed_name)
        self.ed_user = QLineEdit(user.username if user else "")
        self.ed_user.setPlaceholderText("مثلاً sara.ahmadi (خالی = شناسه)")
        self.ed_user.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        form.addRow(_lab("نام کاربری:"), self.ed_user)
        form.addRow(_lab("سن:"), self.sp_age)
        form.addRow(_lab("سابقه (سال):"), self.sp_exp)
        form.addRow(_lab("سطح مهارت:"), self.cmb_skill)
        if user is None:
            self.ed_pin = QLineEdit()
            self.ed_pin.setEchoMode(QLineEdit.Password)
            self.ed_pin.setPlaceholderText("PIN (۴ تا ۱۲ رقم)")
            self.ed_pin.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
            form.addRow(_lab("PIN شخصی:"), self.ed_pin)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("ثبت ✓")
        buttons.button(QDialogButtonBox.Cancel).setText("انصراف")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        out = {"name": self.ed_name.text(), "age": self.sp_age.value(),
               "experience_years": self.sp_exp.value(),
               "skill_tier": self.cmb_skill.currentData(),
               "username": self.ed_user.text().strip() or None}
        if self._user is None:
            out["pin"] = self.ed_pin.text()
        return out


class PlanAssignDialog(QDialog):
    """Assign a workout or meal plan from a template (editable)."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind  # "workout" or "meal"
        self.setWindowTitle("برنامه تمرینی جدید" if kind == "workout"
                            else "برنامه غذایی جدید")
        self.setModal(True)
        self.setMinimumSize(480, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(_lab("قالب آماده:"))
        self.cmb_template = QComboBox()
        self.cmb_template.setLayoutDirection(Qt.RightToLeft)
        templates = WORKOUT_TEMPLATES if kind == "workout" else MEAL_TEMPLATES
        self.cmb_template.addItem("— بدون قالب (دستی) —", "")
        for key, tpl in templates.items():
            self.cmb_template.addItem(tpl["title"], key)
        self.cmb_template.currentIndexChanged.connect(self._apply_template)
        lay.addWidget(self.cmb_template)
        lay.addWidget(_lab("عنوان:"))
        self.ed_title = QLineEdit()
        self.ed_title.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        lay.addWidget(self.ed_title)
        lay.addWidget(_lab("جزئیات (هر خط یک مورد؛ عنوان و شرح با «—» جدا شود):"
                           if kind == "workout"
                           else "وعده‌ها (هر خط: نام وعده — شرح):"))
        self.ed_body = QTextEdit()
        self.ed_body.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        self.ed_body.setLayoutDirection(Qt.RightToLeft)
        lay.addWidget(self.ed_body, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("تخصیص ✓")
        buttons.button(QDialogButtonBox.Cancel).setText("انصراف")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _apply_template(self) -> None:
        key = self.cmb_template.currentData()
        templates = WORKOUT_TEMPLATES if self.kind == "workout" \
            else MEAL_TEMPLATES
        tpl = templates.get(key or "")
        if not tpl:
            return
        self.ed_title.setText(tpl["title"])
        if self.kind == "workout":
            lines = ["%s — %s" % (i["title"], i["detail"])
                     for i in tpl["items"]]
            self.ed_body.setPlainText("\n".join(lines))
        else:
            lines = ["%s — %s" % kv for kv in tpl["meals"].items()]
            if tpl.get("hydration_note"):
                lines.append("آب 💧 — %s" % tpl["hydration_note"])
            self.ed_body.setPlainText("\n".join(lines))

    def parsed(self) -> tuple[str, list]:
        rows = []
        for line in self.ed_body.toPlainText().splitlines():
            line = line.strip().lstrip("•-*").strip()
            if not line:
                continue
            if "—" in line:
                title, detail = line.split("—", 1)
            elif "-" in line:
                title, detail = line.split("-", 1)
            else:
                title, detail = line, ""
            rows.append((title.strip(), detail.strip()))
        return self.ed_title.text().strip(), rows


# ---------------------------------------------------------------------------
class CoachPage(QWidget):
    """Admin panel: athletes CRUD, histories, trends, plan assignment."""

    run_for_athlete = Signal(str)   # athlete_id -> main window starts home flow

    def __init__(self, auth: Optional[AuthService] = None, parent=None):
        super().__init__(parent)
        self.auth = auth or AuthService()
        self.history = HistoryStore()
        self.plans = PlanStore()
        self.messages = MessageStore()
        self.compliance = ComplianceStore()
        self._current: Optional[User] = None
        self._inbox_idx = 4

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(12)
        outer.addWidget(SectionHeader("پنل مربی / مدیر", "settings"))

        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)

        # -- right: athlete list (RTL: first widget is on the right) --------
        side = QWidget()
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(8)
        side_lay.addWidget(_lab("شناگران:"))
        self.list = QListWidget()
        self.list.setLayoutDirection(Qt.RightToLeft)
        self.list.currentItemChanged.connect(self._on_select)
        side_lay.addWidget(self.list, 1)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("＋ جدید")
        self.btn_add.setObjectName("primary")
        self.btn_add.clicked.connect(self._add_athlete)
        self.btn_edit = QPushButton("ویرایش")
        self.btn_edit.setObjectName("ghost")
        self.btn_edit.clicked.connect(self._edit_athlete)
        self.btn_del = QPushButton("حذف")
        self.btn_del.setObjectName("danger")
        self.btn_del.clicked.connect(self._del_athlete)
        self.btn_pin = QPushButton("ریست PIN")
        self.btn_pin.setObjectName("ghost")
        self.btn_pin.clicked.connect(self._reset_pin)
        for b in (self.btn_add, self.btn_edit, self.btn_del, self.btn_pin):
            btn_row.addWidget(b)
        side_lay.addLayout(btn_row)
        split.addWidget(side)

        # -- left: details --------------------------------------------------
        detail = QWidget()
        detail_lay = QVBoxLayout(detail)
        detail_lay.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tab_profile = QWidget()
        self.tab_progress = QWidget()
        self.tab_workouts = QWidget()
        self.tab_meals = QWidget()
        self.tab_inbox = QWidget()
        self.tabs.addTab(self.tab_profile, "مشخصات")
        self.tabs.addTab(self.tab_progress, "تاریخچه و روند")
        self.tabs.addTab(self.tab_workouts, "برنامه تمرینی")
        self.tabs.addTab(self.tab_meals, "برنامه غذایی")
        self._inbox_idx = self.tabs.addTab(self.tab_inbox, "صندوق پیام‌ها")
        detail_lay.addWidget(self.tabs)
        split.addWidget(detail)
        split.setSizes([300, 700])
        self.refresh_list()

    # ------------------------------------------------------------------
    def set_auth(self, auth: AuthService) -> None:
        self.auth = auth
        self.refresh_list()

    def refresh_list(self) -> None:
        self.list.clear()
        for u in self.auth.list_athletes():
            item = QListWidgetItem("%s — %s (@%s)%s" % (
                u.name, u.user_id, u.username,
                "" if u.active else " (غیرفعال)"))
            item.setData(Qt.UserRole, u.user_id)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignAbsolute)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._current = None
            self._render_details()
        self.refresh_inbox()

    def _on_select(self, current, _previous) -> None:
        uid = current.data(Qt.UserRole) if current else None
        self._current = self.auth.store.get(uid) if uid else None
        self._render_details()

    # -- CRUD -------------------------------------------------------------
    def _add_athlete(self) -> None:
        dlg = AthleteFormDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        try:
            user = self.auth.create_athlete(
                v["name"], v["pin"], age=v["age"],
                experience_years=v["experience_years"],
                skill_tier=v["skill_tier"], username=v["username"])
        except AuthError as exc:
            QMessageBox.warning(self, "خطا", str(exc))
            return
        notify(self, "شاگرد %s (@%s) ثبت شد" % (user.user_id, user.username),
               "success")
        self.refresh_list()

    def _edit_athlete(self) -> None:
        if not self._current:
            return
        dlg = AthleteFormDialog(self._current, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        try:
            self.auth.update_athlete(self._current.user_id, name=v["name"],
                                     age=v["age"],
                                     experience_years=v["experience_years"],
                                     skill_tier=v["skill_tier"],
                                     username=(v["username"]
                                               or self._current.username))
        except AuthError as exc:
            QMessageBox.warning(self, "خطا", str(exc))
            return
        notify(self, "مشخصات به‌روز شد", "success", 1800)
        self.refresh_list()

    def _del_athlete(self) -> None:
        if not self._current:
            return
        u = self._current
        box = QMessageBox(self)
        box.setWindowTitle("حذف شناگر")
        box.setText("شناگر «%s» (%s) حذف شود؟" % (u.name, u.user_id))
        box.setInformativeText("تاریخچه تحلیل‌ها و برنامه‌ها نگه داشته "
                               "می‌شود؛ فقط حساب کاربری حذف می‌شود.")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.button(QMessageBox.Yes).setText("حذف")
        box.button(QMessageBox.Cancel).setText("انصراف")
        if box.exec() != QMessageBox.Yes:
            return
        try:
            self.auth.remove_athlete(u.user_id)
        except AuthError as exc:
            QMessageBox.warning(self, "خطا", str(exc))
            return
        notify(self, "شناگر حذف شد", "warning")
        self.refresh_list()

    def _reset_pin(self) -> None:
        if not self._current:
            return
        from PySide6.QtWidgets import QInputDialog
        pin, ok = QInputDialog.getText(
            self, "ریست PIN", "PIN جدید (۴ تا ۱۲ رقم):",
            QLineEdit.Password)
        if not ok or not pin.strip():
            return
        try:
            self.auth.admin_reset_pin(self._current.user_id, pin.strip())
        except AuthError as exc:
            QMessageBox.warning(self, "خطا", str(exc))
            return
        notify(self, "PIN جدید ثبت شد", "success")

    # -- details ------------------------------------------------------------
    @staticmethod
    def _clear(widget: QWidget) -> QVBoxLayout:
        old = widget.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
            return old
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(10)
        return lay

    def _render_details(self) -> None:
        u = self._current
        # profile
        lay = self._clear(self.tab_profile)
        if u is None:
            lay.addWidget(_lab("شناگری انتخاب نشده است.", "muted"))
            lay.addStretch(1)
        else:
            f, fl = card()
            fl.addWidget(_lab("نام: %s" % u.name))
            fl.addWidget(_lab("شناسه: %s" % u.user_id))
            fl.addWidget(_lab("نام کاربری: @%s" % u.username))
            fl.addWidget(_lab("سن: %s" % (u.age or "—")))
            fl.addWidget(_lab("سابقه: %s سال" % u.experience_years))
            fl.addWidget(_lab("سطح: %s" % SKILL_FA.get(u.skill_tier, "")))
            fl.addWidget(_lab("آخرین ورود: %s" % (u.last_login[:16] or "—"),
                               "faint"))
            btn_run = QPushButton("🎬 تحلیل ویدیوی جدید برای این شناگر")
            btn_run.setObjectName("primary")
            btn_run.clicked.connect(
                lambda _=False, uid=u.user_id: self.run_for_athlete.emit(uid))
            fl.addWidget(btn_run)
            lay.addWidget(f)
            # compliance overview for this student
            cf, cfl = card(soft=True)
            cfl.addWidget(_lab("انضباط روزانه: %s"
                               % self.compliance.summary_fa(u.user_id)))
            for e in self.compliance.history(u.user_id, 5)[::-1]:
                cfl.addWidget(_lab(
                    "📅 %s — رژیم: %s | تمرین: %s%s" % (
                        e.day, "✓" if e.diet_done else "✗",
                        "✓" if e.workout_done else "✗",
                        " — %s" % e.note if e.note else ""), "muted"))
            lay.addWidget(cf)
            lay.addStretch(1)
        # progress
        lay = self._clear(self.tab_progress)
        if u is None:
            lay.addWidget(_lab("شناگری انتخاب نشده است.", "muted"))
        else:
            summaries = self.history.list(u.user_id)
            tracker = ProgressTracker(summaries)
            lay.addWidget(_lab(tracker.report_text_fa()))
            for s in reversed(summaries[-15:]):
                lay.addWidget(_lab(
                    "📅 %s — %s | SPM %s | SWOLF %s | سرعت %s | تقارن %s%%" % (
                        s.date_iso[:10], s.style or "—",
                        "%.1f" % s.spm if s.spm else "—",
                        "%.1f" % s.swolf if s.swolf else "—",
                        "%.2f" % s.mean_speed if s.mean_speed else "—",
                        "%.0f" % s.symmetry if s.symmetry else "—"),
                    "muted"))
        lay.addStretch(1)
        self._render_plans(self.tab_workouts, "workout")
        self._render_plans(self.tab_meals, "meal")
        self.refresh_inbox()

    def _render_plans(self, tab: QWidget, kind: str) -> None:
        lay = self._clear(tab)
        u = self._current
        if u is None:
            lay.addWidget(_lab("شناگری انتخاب نشده است.", "muted"))
            lay.addStretch(1)
            return
        btn = QPushButton("＋ تخصیص %s جدید" % ("برنامه تمرینی"
                                               if kind == "workout"
                                               else "برنامه غذایی"))
        btn.setObjectName("primary")
        btn.clicked.connect(lambda: self._assign_plan(kind))
        lay.addWidget(btn)
        items: List = (self.plans.workouts(u.user_id) if kind == "workout"
                       else self.plans.meals(u.user_id))
        if not items:
            lay.addWidget(_lab("هنوز برنامه‌ای ثبت نشده است.", "muted"))
        for plan in items:
            f, fl = card(soft=True)
            head = QHBoxLayout()
            title = _lab("%s%s" % (plan.title,
                                   " ✓ (انجام‌شده)" if plan.done else ""))
            title.setStyleSheet("font-weight:700;")
            head.addWidget(title, 1)
            btn_del = QPushButton("حذف")
            btn_del.setObjectName("danger")
            btn_del.clicked.connect(
                lambda _=False, p=plan: self._remove_plan(kind, p))
            head.addWidget(btn_del)
            fl.addLayout(head)
            fl.addWidget(_lab("تاریخ تخصیص: %s" % plan.assigned_at[:16],
                               "faint"))
            if isinstance(plan, WorkoutPlan):
                fl.addWidget(_lab("تمرکز: %s | %s جلسه در هفته" % (
                    plan.style_focus, plan.sessions_per_week), "muted"))
                for item in plan.items:
                    fl.addWidget(_lab("• %s — %s" % (item["title"],
                                                    item["detail"]),
                                     "muted"))
            else:
                assert isinstance(plan, MealPlan)
                for name, desc in plan.meals.items():
                    fl.addWidget(_lab("• %s: %s" % (name, desc), "muted"))
                if plan.hydration_note:
                    fl.addWidget(_lab("💧 %s" % plan.hydration_note, "faint"))
            if plan.notes:
                fl.addWidget(_lab("یادداشت: %s" % plan.notes, "faint"))
            lay.addWidget(f)
        lay.addStretch(1)

    def _assign_plan(self, kind: str) -> None:
        if not self._current:
            return
        dlg = PlanAssignDialog(kind, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        title, rows = dlg.parsed()
        if not title:
            QMessageBox.warning(self, "خطا", "عنوان برنامه خالی است.")
            return
        uid = self._current.user_id
        if kind == "workout":
            self.plans.assign_workout(
                uid, title, [{"title": t, "detail": d} for t, d in rows])
        else:
            self.plans.assign_meal(uid, title, {t: d for t, d in rows})
        notify(self, "برنامه جدید تخصیص داده شد", "success")
        self._render_details()

    def _remove_plan(self, kind: str, plan) -> None:
        if not self._current:
            return
        uid = self._current.user_id
        if kind == "workout":
            self.plans.remove_workout(uid, plan.plan_id)
        else:
            self.plans.remove_meal(uid, plan.plan_id)
        notify(self, "برنامه حذف شد", "warning", 1800)
        self._render_details()

    # -- admin inbox ----------------------------------------------------------
    def refresh_inbox(self) -> None:
        """Render the compliance inbox tab + unread counter in its title."""
        unread = self.messages.unread_count()
        self.tabs.setTabText(
            self._inbox_idx,
            "صندوق پیام‌ها (%d)" % unread if unread else "صندوق پیام‌ها")
        lay = self._clear(self.tab_inbox)
        row = QHBoxLayout()
        row.addWidget(_lab("گزارش‌های روزانه شاگردان (جدیدترین اول):"), 1)
        btn_all = QPushButton("✓ خواندن همه")
        btn_all.setObjectName("ghost")
        btn_all.clicked.connect(self._mark_all_read)
        row.addWidget(btn_all)
        lay.addLayout(row)
        messages = self.messages.inbox()
        if not messages:
            lay.addWidget(_lab("هنوز گزارشی ثبت نشده است.", "muted"))
        for msg in messages[:80]:
            f, fl = card(soft=True)
            title = _lab(("● " if not msg.read else "") + msg.title_fa)
            title.setStyleSheet(
                "font-weight:700; color:%s;"
                % (C.CYAN if not msg.read else C.MUTED))
            fl.addWidget(title)
            fl.addWidget(_lab("از: %s | %s" % (msg.from_name,
                                               msg.created_at[:16]), "faint"))
            btn = QPushButton("مشاهده")
            btn.setObjectName("ghost")
            btn.clicked.connect(
                lambda _=False, m=msg: self._open_message(m.msg_id))
            fl.addWidget(btn, 0, Qt.AlignLeft)
            lay.addWidget(f)
        lay.addStretch(1)

    def _open_message(self, msg_id: str) -> None:
        found = [m for m in self.messages.inbox() if m.msg_id == msg_id]
        if not found:
            return
        msg = found[0]
        box = QMessageBox(self)
        box.setWindowTitle("گزارش روزانه")
        box.setText(msg.title_fa)
        box.setInformativeText("%s\n\nاز: %s (%s)" % (
            msg.body_fa, msg.from_name, msg.created_at[:16]))
        box.addButton("بستن", QMessageBox.AcceptRole)
        box.exec()
        if self.messages.mark_read(msg_id):
            self.refresh_inbox()

    def _mark_all_read(self) -> None:
        count = self.messages.mark_all_read()
        notify(self, "%d پیام خوانده شد" % count if count
               else "پیام خوانده‌نشده‌ای نیست", "success" if count else "info",
               1800)
        self.refresh_inbox()

    # -- access control -----------------------------------------------------
    def set_session(self, session: Optional[Session]) -> None:
        """Enable/disable the panel based on the login role."""
        admin = session is not None and session.is_admin
        for w in (self.btn_add, self.btn_edit, self.btn_del, self.btn_pin,
                  self.tabs):
            w.setEnabled(admin)
