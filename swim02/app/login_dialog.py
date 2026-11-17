# -*- coding: utf-8 -*-
"""Login gate: student username/password login, admin master-password login.

Shown once at startup (unless ``SETARGAN_NO_AUTH=1`` / ``--no-auth``). On a
successful student login the motivational engine produces a personalised
quote which is shown (and can be spoken) by :class:`QuoteDialog`.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from . import branding
from .audio import AudioService
from .auth import AuthError, AuthService, Session, SKILL_FA
from .history import HistoryStore
from .motivation import MotivationEngine
from .theme import C


def _label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setAlignment(Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter)
    lab.setWordWrap(True)
    return lab


class QuoteDialog(QDialog):
    """Personalised motivational quote shown right after student login."""

    def __init__(self, quote_fa: str, personal_fa: str, speak_text: str,
                 parent=None):
        super().__init__(parent)
        self._speak_text = speak_text
        self.setWindowTitle("پیام انگیزشی")
        self.setModal(True)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        title = _label("💪 پیام امروز تو")
        title.setObjectName("h3")
        lay.addWidget(title)
        quote = _label("«%s»" % quote_fa)
        quote.setStyleSheet("font-size:16px; color:%s;" % C.CYAN)
        lay.addWidget(quote)
        personal = _label(personal_fa)
        personal.setObjectName("muted")
        lay.addWidget(personal)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_speak = QPushButton("🔊 خواندن با صدا")
        btn_speak.setObjectName("ghost")
        btn_speak.clicked.connect(self._speak)
        row.addWidget(btn_speak)
        btn_ok = QPushButton("شروع ✓")
        btn_ok.setObjectName("primary")
        btn_ok.clicked.connect(self.accept)
        btn_ok.setDefault(True)
        row.addWidget(btn_ok)
        lay.addLayout(row)

    def _speak(self) -> None:
        AudioService().speak(self._speak_text)


class LoginDialog(QDialog):
    """Modal login gate; ``session`` is set on success."""

    def __init__(self, auth: Optional[AuthService] = None, parent=None):
        super().__init__(parent)
        self.auth = auth or AuthService()
        self.history = HistoryStore()
        self.motivation = MotivationEngine()
        self.session: Optional[Session] = None
        self.quote_info: Optional[tuple] = None   # (fa, personal_fa, speak)

        self.setWindowTitle("ورود به %s" % branding.APP_NAME_EN)
        self.setModal(True)
        self.setMinimumSize(440, 380)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        head = _label("🏊 ورود به سامانه %s" % branding.APP_NAME_FA)
        head.setObjectName("h2")
        lay.addWidget(head)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._athlete_tab(), "ورود شاگرد")
        self.tabs.addTab(self._admin_tab(), "ورود مربی / مدیر")
        lay.addWidget(self.tabs)

        self.status = _label("")
        self.status.setStyleSheet("color:%s;" % C.RED)
        lay.addWidget(self.status)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Cancel).setText("خروج")
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # -- student tab ------------------------------------------------------
    def _athlete_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)
        self.login_edit = QLineEdit()
        self.login_edit.setPlaceholderText("نام کاربری یا شناسه (مثلاً ATH-0001)")
        self.login_edit.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        self.login_edit.returnPressed.connect(self._login_athlete)
        self.pin_edit = QLineEdit()
        self.pin_edit.setEchoMode(QLineEdit.Password)
        self.pin_edit.setPlaceholderText("رمز شخصی / PIN")
        self.pin_edit.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        self.pin_edit.returnPressed.connect(self._login_athlete)
        btn = QPushButton("ورود شاگرد ✓")
        btn.setObjectName("primary")
        btn.clicked.connect(self._login_athlete)
        form.addRow(_label("نام کاربری:"), self.login_edit)
        form.addRow(_label("رمز شخصی:"), self.pin_edit)
        form.addRow(_label(""), btn)
        hint = _label("نام کاربری و رمز را از مربی (%s) بگیرید."
                      % branding.ADMIN_NAME)
        hint.setObjectName("faint")
        form.addRow(hint)
        return w

    def _login_athlete(self) -> None:
        login = self.login_edit.text().strip()
        if not login:
            self._fail("نام کاربری را وارد کنید.")
            return
        try:
            session = self.auth.login_athlete(login, self.pin_edit.text())
        except AuthError as exc:
            self._fail("ورود ناموفق: نام کاربری یا رمز اشتباه است. (%s)"
                       % exc)
            return
        self.session = session
        user = self.auth.store.get(session.user_id)
        name = user.name if user else ""
        summaries = self.history.list(session.user_id)
        quote, personal_fa, personal_fn, _ = self.motivation.personalise(
            summaries, athlete_name=name, user_id=session.user_id)
        self.quote_info = (quote.fa, personal_fa, personal_fn)
        AudioService().play_success()
        self.accept()

    # -- admin tab --------------------------------------------------------
    def _admin_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)
        if not self.auth.is_admin_setup():
            info = _label("اولین اجرا: یک رمز مادر (حداقل ۸ کاراکتر ASCII) "
                          "برای %s تعریف کنید." % branding.ADMIN_NAME)
            info.setObjectName("muted")
            form.addRow(info)
            self.admin_new = QLineEdit()
            self.admin_new.setEchoMode(QLineEdit.Password)
            self.admin_new.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
            self.admin_confirm = QLineEdit()
            self.admin_confirm.setEchoMode(QLineEdit.Password)
            self.admin_confirm.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
            btn = QPushButton("ثبت رمز مادر ✓")
            btn.setObjectName("primary")
            btn.clicked.connect(self._setup_admin)
            form.addRow(_label("رمز مادر جدید:"), self.admin_new)
            form.addRow(_label("تکرار رمز:"), self.admin_confirm)
            form.addRow(_label(""), btn)
        else:
            self.admin_pw = QLineEdit()
            self.admin_pw.setEchoMode(QLineEdit.Password)
            self.admin_pw.setPlaceholderText("رمز مادر %s" % branding.ADMIN_NAME)
            self.admin_pw.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
            self.admin_pw.returnPressed.connect(self._login_admin)
            btn = QPushButton("ورود مربی ✓")
            btn.setObjectName("primary")
            btn.clicked.connect(self._login_admin)
            form.addRow(_label("رمز مادر:"), self.admin_pw)
            form.addRow(_label(""), btn)
        return w

    def _setup_admin(self) -> None:
        if self.admin_new.text() != self.admin_confirm.text():
            self._fail("تکرار رمز با رمز جدید یکی نیست.")
            return
        try:
            self.auth.setup_admin(self.admin_new.text())
        except AuthError as exc:
            self._fail("خطا: %s" % exc)
            return
        AudioService().play_success()
        # rebuild the admin tab as a login form
        self.tabs.removeTab(1)
        self.tabs.addTab(self._admin_tab(), "ورود مربی / مدیر")
        self.tabs.setCurrentIndex(1)
        self.status.setText("رمز مادر ثبت شد؛ حالا وارد شوید.")
        self.status.setStyleSheet("color:%s;" % C.GREEN)

    def _login_admin(self) -> None:
        try:
            self.session = self.auth.login_admin(self.admin_pw.text())
        except AuthError:
            self._fail("ورود ناموفق: رمز مادر اشتباه است.")
            return
        AudioService().play_success()
        self.accept()

    # -- helpers ----------------------------------------------------------
    def _fail(self, text: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet("color:%s;" % C.RED)
        AudioService().play_error()

    @staticmethod
    def skill_fa(tier: str) -> str:
        return SKILL_FA.get(tier, tier)
