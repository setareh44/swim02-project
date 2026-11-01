# -*- coding: utf-8 -*-
"""ویجت‌های مشترک رابط کاربری."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QColor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import icons
from .theme import C

DASH = "—"


def fmt_num(value, spec: str = "%.1f", scale: float = 1.0) -> str:
    """Format a float for the UI, showing an em dash for NaN / None / inf.

    ``scale`` multiplies the value first (e.g. 100 to show a fraction as %).
    """
    try:
        if value is None:
            return DASH
        v = float(value) * scale
    except (TypeError, ValueError):
        return DASH
    if not math.isfinite(v):
        return DASH
    return spec % v


def card(layout_type=QVBoxLayout, spacing: int = 12, margin: int = 18,
         soft: bool = False) -> tuple[QFrame, object]:
    f = QFrame()
    f.setObjectName("cardSoft" if soft else "card")
    lay = layout_type(f)
    lay.setContentsMargins(margin, margin, margin, margin)
    lay.setSpacing(spacing)
    return f, lay


class SectionHeader(QWidget):
    """عنوان بخش با آیکون اختیاری و خط جداکننده ملایم."""

    def __init__(self, text: str, icon_name: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        if icon_name:
            ic = QLabel()
            ic.setPixmap(icons.pixmap(icon_name, C.CYAN, 20))
            lay.addWidget(ic)
        t = QLabel(text)
        t.setObjectName("h3")
        t.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(t)
        lay.addStretch(1)


class KpiTile(QFrame):
    """کاشی شاخص کلیدی با آیکون، مقدار و واحد."""

    def __init__(self, title: str, value: str, unit: str = "",
                 icon_name: str = "gauge", accent: str = C.CYAN,
                 hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("kpi")
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(15, 13, 15, 13)
        lay.setSpacing(6)

        top = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName("muted")
        t.setStyleSheet("font-size:12px;")
        t.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(t)
        top.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, accent, 20))
        top.addWidget(ic)
        lay.addLayout(top)

        row = QHBoxLayout()
        v = QLabel(value)
        v.setObjectName("kpiValue")
        v.setStyleSheet("color:%s;" % accent)
        row.addWidget(v, 0, Qt.AlignBottom)
        if unit:
            u = QLabel(unit)
            u.setObjectName("kpiUnit")
            row.addWidget(u, 0, Qt.AlignBottom)
        row.addStretch(1)
        lay.addLayout(row)

        if hint:
            h = QLabel(hint)
            h.setObjectName("faint")
            h.setStyleSheet("font-size:11px;")
            h.setWordWrap(True)
            lay.addWidget(h)


class StageCard(QFrame):
    """کارت یک مرحله از پایپلاین در صفحه تحلیل."""

    def __init__(self, index: int, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("stageWait")
        self.index = index
        self.setMinimumHeight(58)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)

        self.badge = QLabel(str(index + 1))
        self.badge.setFixedSize(30, 30)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setStyleSheet(
            "background:%s; color:#04202c; border-radius:15px; font-weight:800;"
            % C.BORDER_HI)
        lay.addWidget(self.badge)

        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight:700;")
        self.title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.sub = QLabel("در انتظار…")
        self.sub.setObjectName("faint")
        self.sub.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.sub.setStyleSheet("font-size:11px;")
        col.addWidget(self.title)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)

        self.state_icon = QLabel()
        self.state_icon.setPixmap(icons.pixmap("lock", C.FAINT, 18))
        lay.addWidget(self.state_icon)

    def set_state(self, state: str, sub: str = ""):
        # state: wait | run | done | err
        self.setObjectName({"wait": "stageWait", "run": "stageRun",
                            "done": "stageDone", "err": "stageErr"}[state])
        color = {"wait": C.FAINT, "run": C.CYAN,
                 "done": C.GREEN, "err": C.RED}[state]
        icon_name = {"wait": "lock", "run": "refresh",
                     "done": "check", "err": "warning"}[state]
        bg = "transparent" if state == "wait" else color
        fg = "#04202c" if state in ("run", "done") else C.FAINT
        self.badge.setStyleSheet(
            "background:%s; color:%s; border-radius:15px; font-weight:800;"
            % (bg, fg))
        self.state_icon.setPixmap(icons.pixmap(icon_name, color, 18))
        self.sub.setText(sub or {"wait": "در انتظار…", "run": "در حال اجرا…",
                                 "done": "تکمیل شد", "err": "خطا"}[state])
        self.style().unpolish(self)
        self.style().polish(self)


class QualityBar(QWidget):
    """نوار افقی توزیع فریم‌های سبز/زرد/قرمز برای یک شاخص تکنیک."""

    def __init__(self, name: str, desc: str, counts: list, parent=None):
        super().__init__(parent)
        self.name, self.desc, self.counts = name, desc, counts
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        total = max(1, sum(self.counts))
        colors = [QColor(C.FAINT), QColor(C.GREEN),
                  QColor(C.YELLOW), QColor(C.RED)]
        bar_x, bar_w = 0, w
        bar_h = 12
        y = h - bar_h - 2
        x = bar_x
        radius = 5
        for c, col in zip(self.counts, colors):
            seg = int(bar_w * c / total)
            if c <= 0:
                continue
            path = QPainterPath()
            path.addRoundedRect(float(x), float(y), max(seg - 1, 2), bar_h,
                                radius, radius)
            p.fillPath(path, col)
            x += seg
        # درصد وضعیت بحرانی روی نوار
        p.end()


class Pill(QLabel):
    """برچسب کوچک رنگی."""

    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            "background: rgba(255,255,255,0.04);"
            "color:%s; border:1px solid %s; border-radius:9px;"
            "padding:3px 11px; font-weight:700; font-size:12px;"
            % (color, color))
