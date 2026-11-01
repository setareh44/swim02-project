# -*- coding: utf-8 -*-
"""پنجرهٔ «درباره نرم‌افزار».

اولین بار که برنامه اجرا می‌شود همین پنجره باز می‌شود و در گوشهٔ پایین‌راست
یک تیک «دیگر نمایش نده» دارد؛ اگر کاربر تیک بزند، دفعهٔ بعد نمایش داده نمی‌شود.
همیشه از دکمهٔ «درباره» در نوار عنوان هم قابل بازکردن است.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import about_info as AI
from . import icons, prefs
from .rtl import apply_rtl_tree
from .theme import C


class AboutDialog(QDialog):
    """پنجرهٔ درباره با قاب گِرد و محتوای فارسی."""

    def __init__(self, parent=None, first_run: bool = False):
        super().__init__(parent)
        self.first_run = first_run
        self._drag = None
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(620)
        self.setWindowTitle("درباره %s" % AI.APP_NAME)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("aboutCard")
        card.setStyleSheet(
            "QFrame#aboutCard{background:%s;border:1px solid %s;"
            "border-radius:18px;}" % (C.BG_DEEP, C.BORDER_HI))
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---------------- سرصفحه ----------------
        head = QFrame()
        head.setObjectName("aboutHead")
        head.setStyleSheet(
            "QFrame#aboutHead{background:rgba(4,14,26,0.95);"
            "border-top-left-radius:18px;border-top-right-radius:18px;"
            "border-bottom:1px solid %s;}" % C.BORDER)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(22, 16, 12, 16)
        hl.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(icons.pixmap("wave", C.CYAN, 34))
        hl.addWidget(logo)

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(AI.APP_NAME)
        name.setStyleSheet("font-size:22px;font-weight:800;color:%s;"
                           "letter-spacing:1px;" % C.CYAN)
        tag = QLabel(AI.APP_TAGLINE)
        tag.setStyleSheet("color:%s;font-size:12px;" % C.MUTED)
        col.addWidget(name)
        col.addWidget(tag)
        hl.addLayout(col)
        hl.addStretch(1)

        ver = QLabel(AI.version_line())
        ver.setStyleSheet("color:%s;font-size:11px;" % C.FAINT)
        hl.addWidget(ver)

        btn_x = QPushButton()
        btn_x.setObjectName("winBtn")
        btn_x.setFixedSize(38, 32)
        btn_x.setIcon(icons.icon("close", C.MUTED, 16))
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.clicked.connect(self.reject)
        hl.addWidget(btn_x)
        lay.addWidget(head)

        # ---------------- بدنه ----------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(520)
        body = QWidget()
        scroll.setWidget(body)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 18, 24, 18)
        bl.setSpacing(14)

        bl.addWidget(_para(AI.PURPOSE))

        bl.addWidget(_heading("چه کاری انجام می‌دهد؟"))
        for title, desc in AI.FEATURES:
            bl.addWidget(_bullet(title, desc))

        bl.addWidget(_heading("چرا این برنامه؟"))
        for goal in AI.GOALS:
            bl.addWidget(_dash(goal))

        bl.addWidget(_heading("پیش‌نیازها"))
        for req in AI.SYSTEM_REQUIREMENTS:
            bl.addWidget(_dash(req))

        bl.addWidget(_heading("تغییرات نسخه"))
        for line in AI.HIGHLIGHTS:
            bl.addWidget(_dash(line))

        bl.addWidget(_heading("فناوری‌ها"))
        for title, desc in AI.CREDITS:
            bl.addWidget(_bullet(title, desc, color=C.TEAL))

        bl.addWidget(_divider())

        # سازنده / حق انحصاری / سال ساخت
        for title, text in (
                ("سازنده", AI.AUTHOR),
                ("حق انحصاری", "%s — %s" % (AI.COPYRIGHT_HOLDER, AI.LICENSE_NAME)),
                ("سال ساخت", AI.year_label()),
                ("نتیجه", AI.DISCLAIMER)):
            bl.addWidget(_kv(title, text))

        cop = QLabel(AI.copyright_line())
        cop.setWordWrap(True)
        cop.setAlignment(Qt.AlignRight)
        cop.setStyleSheet("color:%s;font-size:11px;font-weight:700;"
                          "padding-top:4px;" % C.FAINT)
        bl.addWidget(cop)
        bl.addStretch(1)

        lay.addWidget(scroll, 1)

        # ---------------- پایین: تیک گوشهٔ راست ----------------
        foot = QFrame()
        foot.setStyleSheet("QFrame{background:rgba(4,14,26,0.72);"
                           "border-bottom-left-radius:18px;"
                           "border-bottom-right-radius:18px;"
                           "border-top:1px solid %s;}" % C.BORDER)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(22, 12, 22, 12)
        fl.setSpacing(10)
        # در چیدمان راست‌به‌چپ اولین ویجت سمت راست است
        self.chk_dont_show = QCheckBox("دیگر نمایش نده")
        self.chk_dont_show.setCursor(Qt.PointingHandCursor)
        self.chk_dont_show.setStyleSheet("color:%s;font-weight:600;" % C.MUTED)
        fl.addWidget(self.chk_dont_show)
        fl.addStretch(1)

        self.btn_ok = QPushButton("  متوجه شدم")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.setIcon(icons.icon("check", "#04202c", 18))
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.clicked.connect(self.accept)
        fl.addWidget(self.btn_ok)
        lay.addWidget(foot)

        # کشیدن پنجره با ماوس (فریم‌لس)
        head.mousePressEvent = self._press
        head.mouseMoveEvent = self._move
        self.resize(680, 700)
        self._apply_rtl()

    # ------------------------------------------------------------------
    def _press(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _move(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    # ------------------------------------------------------------------
    def _apply_rtl(self) -> None:
        """همهٔ متن‌های پنجره را راست‌چین کن (پیش از نمایش، نه با رویداد)."""
        try:
            apply_rtl_tree(self)
        except Exception:                       # noqa: BLE001 - ظاهری است
            pass

    def dont_show_again(self) -> bool:
        return self.chk_dont_show.isChecked()

    def save_preference(self) -> None:
        if self.dont_show_again():
            prefs.set_bool(prefs.KEY_ABOUT_SEEN, True)

    def accept(self) -> None:
        self.save_preference()
        super().accept()

    def reject(self) -> None:
        self.save_preference()
        super().reject()


# ---------------------------------------------------------------------------
# ویجت‌های کمکی متن
# ---------------------------------------------------------------------------
def _heading(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setAlignment(Qt.AlignRight)
    lab.setStyleSheet("font-size:14px;font-weight:800;color:%s;"
                      "padding-top:6px;" % C.CYAN)
    return lab


def _para(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setAlignment(Qt.AlignRight | Qt.AlignTop)
    lab.setStyleSheet("font-size:13px;color:%s;" % C.TEXT)
    return lab


def _bullet(title: str, desc: str, color: str = C.BLUE) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    dot = QLabel("●")
    dot.setStyleSheet("color:%s;font-size:9px;" % color)
    dot.setFixedWidth(12)
    dot.setAlignment(Qt.AlignTop)
    lay.addWidget(dot)
    col = QVBoxLayout()
    col.setSpacing(0)
    t = QLabel(title)
    t.setStyleSheet("font-weight:700;font-size:12px;")
    t.setAlignment(Qt.AlignRight)
    d = QLabel(desc)
    d.setWordWrap(True)
    d.setAlignment(Qt.AlignRight)
    d.setStyleSheet("color:%s;font-size:11px;" % C.MUTED)
    col.addWidget(t)
    col.addWidget(d)
    lay.addLayout(col, 1)
    return w


def _dash(text: str) -> QLabel:
    lab = QLabel("—  " + text)
    lab.setWordWrap(True)
    lab.setAlignment(Qt.AlignRight)
    lab.setStyleSheet("color:%s;font-size:12px;" % C.MUTED)
    return lab


def _kv(title: str, value: str) -> QWidget:
    w = QFrame()
    w.setStyleSheet("QFrame{background:rgba(34,211,238,0.06);"
                    "border:1px solid rgba(34,211,238,0.18);"
                    "border-radius:10px;}")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(10)
    t = QLabel(title)
    t.setStyleSheet("font-weight:800;color:%s;font-size:12px;" % C.CYAN)
    t.setFixedWidth(90)
    t.setAlignment(Qt.AlignRight | Qt.AlignTop)
    v = QLabel(value)
    v.setWordWrap(True)
    v.setAlignment(Qt.AlignRight | Qt.AlignTop)
    v.setStyleSheet("font-size:12px;")
    lay.addWidget(t)
    lay.addWidget(v, 1)
    return w


def _divider() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background:%s;" % C.BORDER)
    return line


def show_about(parent=None, first_run: bool = False) -> bool:
    """نمایش پنجره؛ True اگر کاربر تیک «دیگر نمایش نده» زد."""
    dlg = AboutDialog(parent, first_run=first_run)
    if parent is not None:
        try:
            geo = parent.frameGeometry()
            dlg.move(QPoint(geo.center().x() - 330, geo.center().y() - 320))
        except Exception:
            pass
    dlg.exec()
    return dlg.dont_show_again()
