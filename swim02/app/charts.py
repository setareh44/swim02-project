# -*- coding: utf-8 -*-
"""ساخت نمودارهای تعاملی تحلیل بیومکانیک با pyqtgraph + رادار سفارشی QPainter."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QColor, QFont, QPainter, QPen, QPolygonF)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .labels import CRITICAL_KEYS, STYLE_FA
from .theme import C

pg.setConfigOption("background", "transparent")
pg.setConfigOption("foreground", C.MUTED)
pg.setConfigOption("antialias", True)


# --------------------------------------------------------------------------
# ابزارهای مشترک
# --------------------------------------------------------------------------
class TimeAxis(pg.AxisItem):
    """محور زمان بر حسب ثانیه با برچسب mm:ss."""

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            sec = max(0.0, v * scale)
            out.append("%02d:%02d" % (sec // 60, sec % 60))
        return out


def _ds(y: np.ndarray, x: np.ndarray, limit: int = 1400):
    n = len(y)
    if n <= limit:
        return x, y
    step = max(1, n // limit)
    return x[::step], y[::step]


def _plot(height: int = 250, time_axis: bool = True) -> pg.PlotWidget:
    axis = TimeAxis(orientation="bottom") if time_axis else \
        pg.AxisItem(orientation="bottom")
    pw = pg.PlotWidget(axisItems={"bottom": axis})
    pw.setMinimumHeight(height)
    pw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    pw.showGrid(x=False, y=True, alpha=0.18)
    if time_axis:
        pw.getAxis("bottom").setLabel("زمان", units="s", color=C.MUTED)
    for side in ("left", "bottom"):
        ax = pw.getAxis(side)
        ax.setPen(QPen(QColor(C.BORDER_HI)))
        ax.setTextPen(QPen(QColor(C.MUTED)))
        ax.enableAutoSIPrefix(False)   # جلوگیری از نمایش x0.001 و …
    pw.getPlotItem().setContentsMargins(8, 10, 8, 4)
    pw.setMouseEnabled(x=True, y=False)
    return pw


def _curve(target, x, y, color, width=2.2, name=None, dashed=False, fill=None):
    x, y = _ds(np.asarray(y, float), x)
    pen = pg.mkPen(QColor(color), width=width,
                   style=Qt.DashLine if dashed else Qt.SolidLine)
    kw = dict(pen=pen, connect="finite")
    if name:
        kw["name"] = name
    if fill is not None:
        kw["fillLevel"] = 0.0
        kw["fillBrush"] = pg.mkBrush(QColor(fill))
    item = pg.PlotDataItem(x, y, **kw)
    target.addItem(item)   # هم روی PlotWidget و هم ViewBox کار می‌کند
    return item


def _hline(pw, value: float, color: str, label: str = ""):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return
    line = pg.InfiniteLine(angle=0, movable=False,
                           pen=pg.mkPen(QColor(color), width=1.4,
                                        style=Qt.DashLine))
    line.setValue(value)
    if label:
        line.label = pg.InfLineLabel(line, label, position=0.97,
                                     color=QColor(color), fill=None)
    pw.addItem(line)


# --------------------------------------------------------------------------
# نمودارها — هر تابع یک عنوان و ویجت برمی‌گرداند
# --------------------------------------------------------------------------
def chart_speed(r):
    pw = _plot()
    t = np.arange(r.pose.n) / r.pose.fps
    _curve(pw, t, r.perf.speed, C.CYAN, fill=QColor(34, 211, 238, 38),
           name="سرعت لحظه‌ای (m/s)")
    _hline(pw, r.perf.mean_speed, C.TEAL, "میانگین %.2f" % r.perf.mean_speed)
    _hline(pw, r.perf.max_speed, C.VIOLET, "بیشینه %.2f" % r.perf.max_speed)
    pw.getAxis("left").setLabel("m/s", color=C.MUTED)
    pw.addLegend(offset=(-10, 6))
    return "سرعت لحظه‌ای شناگر", pw


def chart_spm(r):
    pw = _plot()
    t = np.arange(r.pose.n) / r.pose.fps
    _curve(pw, t, r.strokes.spm_inst, C.BLUE, name="نرخ ضربه لحظه‌ای (SPM)")
    _hline(pw, r.strokes.spm_avg, C.YELLOW,
           "میانگین %.1f" % r.strokes.spm_avg)
    pw.getAxis("left").setLabel("SPM", color=C.MUTED)
    pw.addLegend(offset=(-10, 6))
    return "نرخ ضربه (Stroke Rate)", pw


def chart_elbow(r):
    pw = _plot()
    t = np.arange(r.pose.n) / r.pose.fps
    _curve(pw, t, r.bio.elbow["L"], C.CYAN, name="آرنج چپ")
    _curve(pw, t, r.bio.elbow["R"], C.VIOLET, name="آرنج راست")
    _hline(pw, 150, C.YELLOW)
    _hline(pw, 165, C.RED)
    pw.getAxis("left").setLabel("درجه", color=C.MUTED)
    pw.addLegend(offset=(-10, 6))
    return "زاویه آرنج چپ و راست", pw


def chart_knee(r):
    pw = _plot()
    t = np.arange(r.pose.n) / r.pose.fps
    _curve(pw, t, r.bio.knee["L"], C.TEAL, name="زانو چپ")
    _curve(pw, t, r.bio.knee["R"], C.ORANGE, name="زانو راست")
    lim = {"CRAWL": (45, 70), "BACK": (45, 70),
           "FLY": (80, 100), "BREAST": (125, 140)}[r.style_final]
    _hline(pw, lim[0], C.YELLOW)
    _hline(pw, lim[1], C.RED)
    pw.getAxis("left").setLabel("درجه", color=C.MUTED)
    pw.addLegend(offset=(-10, 6))
    return "خمش زانو (حدود آستانه سبک)", pw


def chart_roll_pitch(r):
    pw = _plot()
    t = np.arange(r.pose.n) / r.pose.fps
    _curve(pw, t, r.bio.roll, C.BLUE, name="چرخش شانه (Roll)")
    _curve(pw, t, r.bio.pitch, C.ORANGE, name="شیب بدن (Pitch)")
    fly = r.style_final in ("FLY", "BREAST")
    _hline(pw, 15 * 1.8 if fly else 8, C.YELLOW)
    _hline(pw, 30 * 1.8 if fly else 15, C.RED)
    pw.getAxis("left").setLabel("درجه", color=C.MUTED)
    pw.addLegend(offset=(-10, 6))
    return "چرخش شانه و شیب بدن", pw


def chart_swolf(r):
    pw = _plot()
    t = np.arange(r.pose.n) / r.pose.fps
    _curve(pw, t, r.perf.swolf, C.RED, width=1.8, name="SWOLF تخمینی")
    vb2 = pg.ViewBox()
    pw.showAxis("right")
    pw.scene().addItem(vb2)
    pw.getAxis("right").linkToView(vb2)
    pw.getAxis("right").setLabel("شاخص کارایی", color=C.TEAL)
    vb2.setXLink(pw)
    # بدون تنظیم اولیه، محور دوم تا اولین تغییر اندازه خالی می‌ماند
    vb2.setGeometry(pw.getViewBox().sceneBoundingRect())
    pw.getViewBox().sigResized.connect(
        lambda: vb2.setGeometry(pw.getViewBox().sceneBoundingRect()))
    _curve(vb2, t, r.perf.eff_idx, C.TEAL, name="شاخص کارایی")
    vb2.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
    pw.getAxis("left").setLabel("SWOLF", color=C.MUTED)
    pw.addLegend(offset=(-10, 6))
    return "SWOLF و شاخص کارایی", pw


def chart_stroke_len(r):
    pw = _plot()
    t = np.arange(r.pose.n) / r.pose.fps
    y = np.asarray(r.perf.stroke_len, float)
    _curve(pw, t, y, C.VIOLET,
           fill=QColor(167, 139, 250, 32), name="طول هر ضربه (m)")
    _hline(pw, r.perf.sl_mean, C.CYAN,
           "میانگین %.2f m" % r.perf.sl_mean)
    # محدودکردن محور Y به بازه صدک ۱ تا ۹۹ برای حذف مقادیر پرت
    finite = y[np.isfinite(y)]
    if finite.size > 10:
        lo, hi = np.nanpercentile(finite, 1), np.nanpercentile(finite, 99)
        pad = max(0.05, (hi - lo) * 0.12)
        pw.setYRange(max(0, lo - pad), hi + pad)
    pw.getAxis("left").setLabel("متر", color=C.MUTED)
    pw.addLegend(offset=(-10, 6))
    return "طول ضربه (Stroke Length)", pw


def chart_symmetry(r):
    pw = _plot()
    t = np.arange(r.pose.n) / r.pose.fps
    _curve(pw, t, r.sym.series, C.GREEN, width=2.0, name="تقارن لحظه‌ای (%)")
    _hline(pw, 80, C.GREEN)
    _hline(pw, 65, C.RED)
    pw.setYRange(0, 105)
    pw.getAxis("left").setLabel("٪", color=C.MUTED)
    pw.addLegend(offset=(-10, 6))
    return "تقارن کشش دو دست", pw


TICK_SHORT = {"elbow_L": "آرنج چپ", "elbow_R": "آرنج راست",
              "pitch": "شیب بدن", "hipdev": "موقعیت لگن",
              "sym": "تقارن دو دست"}


def chart_events(r):
    pw = _plot(230, time_axis=False)
    keys = CRITICAL_KEYS
    vals = [r.evalr.events.get(k, 0) for k in keys]
    xs = np.arange(len(keys))
    bg = pg.BarGraphItem(x=xs, height=vals, width=0.55,
                         brush=pg.mkBrush(QColor(248, 113, 113, 210)),
                         pen=pg.mkPen(QColor(C.RED), width=1))
    pw.addItem(bg)
    ticks = [[(i, TICK_SHORT[k]) for i, k in enumerate(keys)]]
    ax = pw.getAxis("bottom")
    ax.setTicks(ticks)
    ax.setStyle(tickFont=QFont("Tahoma", 9))
    pw.getAxis("left").setLabel("تعداد رویداد", color=C.MUTED)
    pw.setMouseEnabled(x=False, y=False)
    top = max(max(vals), 1)
    pw.setYRange(0, top * 1.25)
    for x, v in zip(xs, vals):
        txt = pg.TextItem(str(v), color=QColor(C.TEXT), anchor=(0.5, 1.0))
        font = QFont("Tahoma", 10)
        font.setBold(True)
        txt.setFont(font)
        txt.setPos(x, v + top * 0.04)
        pw.addItem(txt)
    return "رخدادهای بحرانی تکنیک", pw


# --------------------------------------------------------------------------
# رادار سهم سبک‌های شنا (رندر سفارشی QPainter)
# --------------------------------------------------------------------------
class RadarChart(QWidget):
    def __init__(self, shares: dict, parent=None):
        super().__init__(parent)
        self.shares = shares
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setLayoutDirection(Qt.LeftToRight)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 + 6
        radius = min(w, h) / 2 - 52
        keys = ["CRAWL", "BACK", "FLY", "BREAST"]
        angles = [(-90 + i * 90) for i in range(4)]

        # حلقه‌ها
        for ring in (0.25, 0.5, 0.75, 1.0):
            poly = QPolygonF([
                QPointF(cx + radius * ring * np.cos(np.radians(a)),
                        cy + radius * ring * np.sin(np.radians(a)))
                for a in angles])
            p.setPen(QPen(QColor(C.BORDER_HI), 1))
            p.setBrush(QColor(255, 255, 255, 6))
            p.drawPolygon(poly)
        # محورها و برچسب‌ها
        font = QFont("Tahoma", 9)
        p.setFont(font)
        for a, k in zip(angles, keys):
            rad = np.radians(a)
            x, y = cx + radius * np.cos(rad), cy + radius * np.sin(rad)
            p.setPen(QPen(QColor(C.BORDER_HI), 1))
            p.drawLine(QPointF(cx, cy), QPointF(x, y))
            lx = cx + (radius + 26) * np.cos(rad)
            ly = cy + (radius + 26) * np.sin(rad)
            p.setPen(QColor(C.TEXT))
            rect = QRectF(lx - 48, ly - 12, 96, 24)
            p.drawText(rect, Qt.AlignCenter, STYLE_FA[k])

        # چندضلعی داده
        vals = [max(0.0, min(1.0, float(self.shares.get(k, 0.0)))) for k in keys]
        poly = QPolygonF([
            QPointF(cx + radius * v * np.cos(np.radians(a)),
                    cy + radius * v * np.sin(np.radians(a)))
            for v, a in zip(vals, angles)])
        p.setPen(QPen(QColor(C.CYAN), 2.2))
        p.setBrush(QColor(34, 211, 238, 70))
        p.drawPolygon(poly)
        p.setFont(QFont("Tahoma", 9))
        for v, a in zip(vals, angles):
            rad = np.radians(a)
            px, py = cx + radius * v * np.cos(rad), cy + radius * v * np.sin(rad)
            p.setBrush(QColor(C.CYAN))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(px, py), 4.5, 4.5)
            # مقدار عددی داخل یک حباب کوچک کنار رأس
            label = "%d٪" % round(100 * v)
            off = 16
            lx, ly = px + off * np.cos(rad), py + off * np.sin(rad)
            p.setPen(QPen(QColor(C.CYAN), 1))
            p.setBrush(QColor(6, 20, 37, 230))
            rect = QRectF(lx - 24, ly - 11, 48, 22)
            p.drawRoundedRect(rect, 8, 8)
            p.setPen(QColor(C.TEXT))
            p.drawText(rect, Qt.AlignCenter, label)
        p.end()


def chart_radar(r):
    radar = RadarChart(r.style_full.shares)
    return "توزیع احتمال سبک‌های شنا", radar


def build_all(r) -> list[tuple[str, QWidget]]:
    return [
        chart_speed(r),
        chart_spm(r),
        chart_elbow(r),
        chart_knee(r),
        chart_roll_pitch(r),
        chart_swolf(r),
        chart_stroke_len(r),
        chart_symmetry(r),
        chart_events(r),
        chart_radar(r),
    ]
