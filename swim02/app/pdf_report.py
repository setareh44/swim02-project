# -*- coding: utf-8 -*-
"""ساخت گزارش PDF قابل چاپ — در دو حالت «رنگی» و «سیاه‌وسفید».

ساخت HTML هیچ وابستگی‌ای به Qt ندارد (و در تست‌ها بررسی می‌شود)؛ تبدیل به PDF
با `QPdfWriter` انجام می‌شود که بخشی از خود Qt است، بنابراین هیچ کتابخانهٔ
اضافه‌ای به حجم نسخه نصب‌شده اضافه نمی‌کند.

    export_pdf(path, results, profile, color=True)
"""
from __future__ import annotations

import datetime as _dt
import html
import os
from typing import Any

from . import about_info as AI
from .insights import build_insights
from .jalali import fa_digits, jalali_long, jalali_str
from .labels import (CRITICAL_KEYS, STATUS_NAME, STYLE_FA, TECH_KEYS, VIEW_FA)
from .swimmer import SwimmerProfile

# ---------------------------------------------------------------------------
# پالت گزارش
# ---------------------------------------------------------------------------
_PALETTE_COLOR = {
    "ink": "#10222f",
    "muted": "#44586a",
    "line": "#b9cddb",
    "head_bg": "#0b3552",
    "head_fg": "#ffffff",
    "band": "#e8f4fb",
    "band_alt": "#ffffff",
    "accent": "#0f7ea8",
    "green": "#16794f",
    "yellow": "#9a6a06",
    "red": "#b3202b",
    "grey": "#8b9aa6",
    "soft_green": "#d6f0e3",
    "soft_yellow": "#fbeecd",
    "soft_red": "#fadadd",
    "footer": "#6b7b88",
}

_PALETTE_BW = {
    "ink": "#000000",
    "muted": "#333333",
    "line": "#999999",
    "head_bg": "#000000",
    "head_fg": "#ffffff",
    "band": "#eeeeee",
    "band_alt": "#ffffff",
    "accent": "#000000",
    "green": "#000000",
    "yellow": "#333333",
    "red": "#000000",
    "grey": "#777777",
    "soft_green": "#e6e6e6",
    "soft_yellow": "#d9d9d9",
    "soft_red": "#c9c9c9",
    "footer": "#555555",
}

_FONT = "Tahoma, Vazirmatn, Vazir, DejaVu Sans, Arial"


def _palette(color: bool) -> dict:
    return dict(_PALETTE_COLOR if color else _PALETTE_BW)


def _e(text: Any) -> str:
    return html.escape(str(text), quote=False)


def _num(value, spec: str = "%.1f", unit: str = "") -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v != v or v in (float("inf"), float("-inf")):
        return "—"
    out = fa_digits(spec % v)
    return (out + (" " + unit if unit else "")).strip()


def _int(value) -> str:
    try:
        return fa_digits(str(int(value)))
    except (TypeError, ValueError):
        return "—"


def _view_name(results) -> str:
    try:
        from swim_ai import VIEW_HUD
        return VIEW_HUD[_attr(results, "track.dominant", 0)]
    except Exception:
        return ""


def _attr(obj, path: str, default=None):
    """خواندن ایمن یک ویژگی (حتی تودرتو)؛ اگر نبود مقدار پیش‌فرض."""
    cur = obj
    for part in path.split("."):
        try:
            cur = getattr(cur, part)
        except Exception:
            return default
        if cur is None:
            return default
    return cur


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
def report_html(results, profile: SwimmerProfile | None = None,
                color: bool = True, generated: _dt.date | None = None) -> str:
    """HTML کامل گزارش (بدون جاوااسکریپت) — قابل چاپ در A4."""
    p = _palette(color)
    profile = profile or SwimmerProfile()
    generated = generated or _dt.date.today()

    r = results
    style_raw = _attr(r, "style_final", "") or ""
    style_fa = STYLE_FA.get(style_raw, style_raw or "—")
    duration = 0.0
    frames = 0
    detect = 0.0
    try:
        frames = int(_attr(r, "pose.n", 0) or 0)
        duration = frames / float(_attr(r, "pose.fps", 30.0) or 30.0)
        detect = 100.0 * float(_attr(r, "pose_raw.detect_ratio", 0.0) or 0.0)
    except Exception:
        pass

    parts: list[str] = []
    add = parts.append

    add('<html><head><meta charset="utf-8"><style>'
        'body{font-family:%s;color:%s;font-size:9pt;}' % (_FONT, p["ink"]))
    add('h1{font-size:17pt;margin:0;color:%s;}' % p["head_bg"])
    add('h2{font-size:11pt;margin:14pt 0 4pt 0;color:%s;'
        'border-bottom:1pt solid %s;padding-bottom:2pt;}' % (p["accent"], p["line"]))
    add('table{border-collapse:collapse;width:100%;}')
    add('td,th{border:0.6pt solid %s;padding:3.2pt 5pt;font-size:8.6pt;}'
        % p["line"])
    add('th{background:%s;color:%s;font-weight:bold;}' % (p["head_bg"], p["head_fg"]))
    add('.k{background:%s;font-weight:bold;width:26%%;}' % p["band"])
    add('.m{background:%s;}' % p["band_alt"])
    add('.meta{color:%s;font-size:8.4pt;}' % p["muted"])
    add('.note{background:%s;border:0.6pt solid %s;padding:6pt;font-size:8.6pt;}'
        % (p["band"], p["line"]))
    add('.foot{color:%s;font-size:7.6pt;}' % p["footer"])
    add('</style></head><body dir="rtl">')

    # ---------------- سرصفحه ----------------
    add('<table><tr>'
        '<td style="border:none;width:70%%">'
        '<h1>گزارش تحلیل بیومکانیک شنا</h1>'
        '<div class="meta">%s — %s</div>'
        '</td>'
        '<td style="border:none;text-align:left">'
        '<div class="meta">تاریخ گزارش: %s (%s)</div>'
        '<div class="meta">نسخه برنامه: %s</div>'
        '</td></tr></table>' % (_e(AI.APP_NAME), _e(AI.APP_TAGLINE),
                               _e(jalali_long(generated)),
                               _e(jalali_str(generated)), _e(AI.APP_VERSION)))

    # ---------------- پرونده شناگر ----------------
    add('<h2>پرونده شناگر</h2>')
    add('<table>')
    rows = profile.rows()
    if not profile.name.strip():
        # نام خالی نباید ردیف را حذف کند؛ در برگهٔ چاپی باید جایش معلوم باشد
        rows = [("نام و نام خانوادگی", "—")] + rows
    rows = rows + [("تاریخ تحلیل", jalali_str(generated))]
    for i in range(0, len(rows), 2):
        add('<tr>')
        for label, value in rows[i:i + 2]:
            add('<td class="k">%s</td><td class="m">%s</td>'
                % (_e(label), _e(value)))
        if len(rows[i:i + 2]) == 1:
            add('<td class="k"></td><td class="m"></td>')
        add('</tr>')
    add('</table>')

    # ---------------- ویدیو ----------------
    video = os.path.basename(str(_attr(r, "video_path", "") or "—"))
    add('<h2>مشخصات ویدیو</h2>')
    add('<table><tr>'
        '<td class="k">فایل</td><td class="m">%s</td>'
        '<td class="k">مدت</td><td class="m">%s</td>'
        '</tr><tr>'
        '<td class="k">تعداد فریم</td><td class="m">%s</td>'
        '<td class="k">دقت تشخیص اسکلت</td><td class="m">%s</td>'
        '</tr><tr>'
        '<td class="k">سبک شنا</td><td class="m">%s</td>'
        '<td class="k">زاویه دوربین</td><td class="m">%s</td>'
        '</tr></table>' % (
            _e(video),
            _num(duration, "%.1f", "ثانیه"),
            _int(frames),
            _num(detect, "%.0f", "٪"),
            _e(style_fa),
            _e(VIEW_FA.get(_view_name(r), _view_name(r) or "—")),
        ))

    # ---------------- شاخص‌های کلیدی ----------------
    add('<h2>شاخص‌های کلیدی عملکرد</h2>')
    metrics = [
        ("تعداد کل ضربه‌ها", _int(_attr(r, "strokes.total_strokes", 0))),
        ("نرخ ضربه میانگین", _num(_attr(r, "strokes.spm_avg"), "%.1f", "SPM")),
        ("سرعت میانگین", _num(_attr(r, "perf.mean_speed"), "%.2f", "m/s")),
        ("بیشینه سرعت", _num(_attr(r, "perf.max_speed"), "%.2f", "m/s")),
        ("مسافت تخمینی", _num(_attr(r, "perf.distance"), "%.1f", "متر")),
        ("طول ضربه", _num(_attr(r, "perf.sl_mean"), "%.2f", "متر/ضربه")),
        ("شاخص کارایی", _num(_attr(r, "perf.eff_mean"), "%.2f")),
        ("SWOLF تخمینی", _num(_attr(r, "perf.swolf_est"), "%.1f")),
        ("تقارن دو دست", _num(_attr(r, "sym.global_pct"), "%.0f", "٪")),
        ("اطمینان تشخیص سبک",
         _num(100.0 * (_attr(r, "style_full.conf", 0.0) or 0.0), "%.0f", "٪")),
    ]
    add('<table>')
    for i in range(0, len(metrics), 2):
        add('<tr>')
        for label, value in metrics[i:i + 2]:
            add('<td class="k">%s</td><td class="m">%s</td>' % (_e(label), _e(value)))
        if len(metrics[i:i + 2]) == 1:
            add('<td class="k"></td><td class="m"></td>')
        add('</tr>')
    add('</table>')

    # ---------------- وضعیت تکنیک ----------------
    add('<h2>وضعیت شاخص‌های تکنیکی</h2>')
    add('<table><tr><th>شاخص</th><th>مطلوب</th><th>هشدار</th>'
        '<th>بحرانی</th><th>نامشخص</th></tr>')
    status = _attr(r, "evalr.status", {}) or {}
    for key, (name, _desc) in TECH_KEYS.items():
        arr = status.get(key)
        if arr is None:
            continue
        try:
            total = max(1, len(arr))
            counts = [int((arr == k).sum()) for k in range(4)]
        except Exception:
            continue
        pct = [100.0 * c / total for c in counts]
        add('<tr><td class="k">%s</td>'
            '<td class="m" style="background:%s">%s</td>'
            '<td class="m" style="background:%s">%s</td>'
            '<td class="m" style="background:%s">%s</td>'
            '<td class="m">%s</td></tr>' % (
                _e(name),
                p["soft_green"], _num(pct[1], "%.0f", "٪"),
                p["soft_yellow"], _num(pct[2], "%.0f", "٪"),
                p["soft_red"], _num(pct[3], "%.0f", "٪"),
                _num(pct[0], "%.0f", "٪"),
            ))
    add('</table>')
    add('<div class="meta">راهنما: %s / %s / %s — درصد فریم‌های هر وضعیت در طول ویدیو.'
        % (_e(STATUS_NAME[1]), _e(STATUS_NAME[2]), _e(STATUS_NAME[3])))
    add('</div>')

    # ---------------- رخدادهای بحرانی ----------------
    events = _attr(r, "evalr.events", {}) or {}
    red_frames = _attr(r, "evalr.red_frames", {}) or {}
    add('<h2>رخدادهای بحرانی</h2>')
    add('<table><tr><th>رخداد</th><th>تعداد</th><th>فریم قرمز</th></tr>')
    for key in CRITICAL_KEYS:
        add('<tr><td class="k">%s</td><td class="m">%s</td><td class="m">%s</td></tr>'
            % (_e(TECH_KEYS[key][0]), _int(events.get(key, 0)),
               _int(red_frames.get(key, 0))))
    add('</table>')

    # ---------------- پیشنهادها ----------------
    add('<h2>پیشنهادهای اصلاح تکنیک</h2>')
    try:
        items = build_insights(r)
    except Exception:
        items = []
    if not items:
        add('<div class="note">برای این جلسه پیشنهاد خاصی ثبت نشد؛ '
            'شاخص‌ها در محدودهٔ مطلوب هستند.</div>')
    for item in items:
        level = item.get("level", "info")
        bg = {"red": p["soft_red"], "yellow": p["soft_yellow"],
              "green": p["soft_green"]}.get(level, p["band"])
        fg = {"red": p["red"], "yellow": p["yellow"],
              "green": p["green"]}.get(level, p["accent"])
        add('<div style="background:%s;border:0.6pt solid %s;padding:5pt;'
            'margin:3pt 0;">' % (bg, p["line"]))
        add('<b style="color:%s">%s</b><br/>' % (fg, _e(item.get("title", ""))))
        add('%s' % _e(item.get("text", "")))
        if item.get("drill"):
            add('<br/><b>تمرین پیشنهادی:</b> %s' % _e(item["drill"]))
        add('</div>')

    # ---------------- پانویس ----------------
    add('<h2>یادداشت مربی / شناگر</h2>')
    add('<div class="note" style="height:46pt">'
        '<br/><br/>امضا: ____________________________ &nbsp;&nbsp; '
        'تاریخ: ____________</div>')
    add('<br/><div class="foot">%s</div>' % _e(AI.copyright_line()))
    add('<div class="foot">%s — %s</div>'
        % (_e(AI.APP_NAME), _e(AI.year_label())))
    add('</body></html>')
    return "".join(parts)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def export_pdf(path: str, results, profile: SwimmerProfile | None = None,
               color: bool = True, margin_mm: float = 12.0) -> str:
    """نوشتن گزارش در فایل PDF و برگرداندن مسیر فایل.

    فقط از ماژول QtGui استفاده می‌کند (QPdfWriter + QTextDocument)، بنابراین
    هیچ کتابخانه یا ماژول اضافه‌ای (مثل QtPrintSupport) لازم نیست.
    خطاها بالا می‌روند تا رابط کاربری پیام فارسی نشان دهد.
    """
    from PySide6.QtCore import QMarginsF, QRectF, QSizeF
    from PySide6.QtGui import (QFont, QPageLayout, QPageSize, QPainter,
                               QPdfWriter, QTextDocument)

    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)

    dpi = 150
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    # حاشیه را خودمان اعمال می‌کنیم تا مختصات قابل پیش‌بینی باشد
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
    writer.setResolution(dpi)
    writer.setTitle("SWIM-AI - %s" % (profile.display_name()
                                      if profile else "analysis report"))
    writer.setCreator(AI.APP_NAME)

    margin = margin_mm / 25.4 * dpi
    page_w = float(writer.width())
    page_h = float(writer.height())
    content_w = page_w - 2 * margin
    content_h = page_h - 2 * margin

    doc = QTextDocument()
    font = QFont("Tahoma")
    font.setPointSize(9)
    doc.setDefaultFont(font)
    doc.setDocumentMargin(0)
    doc.setPageSize(QSizeF(content_w, content_h))
    doc.setHtml(report_html(results, profile, color=color))

    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        pages = max(1, int(doc.pageCount()))
        clip = QRectF(margin, margin, content_w, content_h)
        for i in range(pages):
            if i:
                writer.newPage()
            painter.setClipRect(clip)
            painter.save()
            painter.translate(margin, margin - i * content_h)
            doc.drawContents(painter)
            painter.restore()
        painter.setClipping(False)
    finally:
        painter.end()
    return path


def default_filename(profile: SwimmerProfile | None = None,
                     color: bool = True) -> str:
    """نام پیشنهادی فایل: گزارش-نام-تاریخ-رنگی.pdf"""
    who = (profile.name.strip() if profile and profile.name.strip() else "شناگر")
    who = who.replace(" ", "-").replace("/", "-").replace("\\", "-")
    tag = "رنگی" if color else "سیاه-سفید"
    return "گزارش-%s-%s-%s.pdf" % (who, jalali_str().replace("/", "-"), tag)
