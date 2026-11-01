# -*- coding: utf-8 -*-
"""
موتور پیشنهاد هوشمند: نتایج کمی پایپلاین را به توصیه‌های مربی‌گری فارسی،
همراه با تمرین اصلاحی (Drill) تبدیل می‌کند.
"""
from __future__ import annotations

import warnings

import numpy as np

from .labels import STYLE_FA

_KNEE_LIM = {"CRAWL": (45, 70), "BACK": (45, 70),
             "FLY": (80, 100), "BREAST": (125, 140)}


def _nanmax(x):
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        v = np.nanmax(x)
    return None if np.isnan(v) else float(v)


def _nanmean(x):
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        v = np.nanmean(x)
    return None if np.isnan(v) else float(v)


def _finite(x) -> float | None:
    """مقدار متناهی یا None (برای اعداد NaN/None خروجی پایپلاین)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def build_insights(r) -> list[dict]:
    ev = r.evalr.events
    rf = r.evalr.red_frames
    n = max(1, r.pose.n)
    style = r.style_final
    out: list[dict] = []

    # ۱) افتادگی آرنج ------------------------------------------------------
    elbow_events = ev.get("elbow_L", 0) + ev.get("elbow_R", 0)
    elbow_frames = rf.get("elbow_L", 0) + rf.get("elbow_R", 0)
    if elbow_frames / n > 0.08 or elbow_events >= 4:
        out.append(dict(
            level="red", icon="warning",
            title="افتادگی آرنج در مرحله کشش",
            text="در %d فریم (%d٪) آرنج در وضعیت بحرانی ثبت شد. آرنج افتاده سطح "
                 "مقطع کشش را کم می‌کند و نیروی جلوبرنده به هدر می‌رود."
                 % (elbow_frames, round(100 * elbow_frames / n)),
            drill="تمرین اسکالینگ (Sculling) و دریل کشش آرنج‌بالا (High-Elbow Catch)؛ "
                  "۱۰×۲۵ متر با تمرکز بر عبور آرنج از بالای سطح دست."))
    elif elbow_events > 0:
        out.append(dict(
            level="yellow", icon="info",
            title="مورد پراکنده از افت آرنج",
            text="چند نمونه محدود از زاویه نامناسب آرنج (%d رویداد) دیده شد؛ "
                 "در کل بدنه کشش قابل قبول است اما تثبیت آن تمرین می‌خواهد."
                 % elbow_events,
            drill="دریل Finger-Tip Drag: نوک انگشتان را هنگام ریکاوری روی آب بکشید."))

    # ۲) شیب بدن -----------------------------------------------------------
    pitch_events = ev.get("pitch", 0)
    pitch_mean = _nanmean(r.bio.pitch)
    if pitch_events > 0 or (pitch_mean is not None and abs(pitch_mean) > 15):
        out.append(dict(
            level="red" if pitch_events >= 3 else "yellow",
            icon="body",
            title="شیب نامناسب بدن (پاها فرو می‌روند)",
            text="%d رویداد بحرانی شیب بدن ثبت شد و میانگین زاویه پیتچ %.1f درجه است. "
                 "پایین رفتن پاها مقاومت پسار را به‌شدت بالا می‌برد."
                 % (pitch_events, pitch_mean or 0.0),
            drill="نگاه به کف استخر (نه روبرو)، شنا با تخته و ضربه پا، و تقویت هسته "
                  "(Plank) برای تثبیت خط افقی بدن."))

    # ۳) لگن ---------------------------------------------------------------
    hip_events = ev.get("hipdev", 0)
    hip_mean = _nanmean(np.abs(r.bio.hipdev))
    if hip_events > 0 or (hip_mean is not None and hip_mean > 0.22):
        out.append(dict(
            level="red" if hip_events >= 2 else "yellow",
            icon="body",
            title="نوسان بیش از حد لگن",
            text="انحراف میانگین لگن نسبت به تنه %.2f است. لگن باید در امتداد تنه "
                 "و نزدیک سطح آب بماند." % (hip_mean or 0.0),
            drill="دریل شش ضربه یک کشش (6-Kick Switch) با تمرکز بر چرخش از تنه، "
                  "به‌جای خم کردن کمر."))

    # ۴) تقارن -------------------------------------------------------------
    sym = _finite(r.sym.global_pct)
    if sym is not None:
        if sym < 65:
            out.append(dict(
                level="red", icon="warning",
                title="عدم تقارن محسوس بین دو دست",
                text="شاخص تقارن کشش %.0f٪ است. دست ضعیف‌تر چرخه کشش کوتاه‌تری دارد "
                     "و مسیر شنا را منحرف می‌کند." % sym,
                drill="تمرین یک‌دست (Single-arm Freestyle) و Catch-Up برای متعادل "
                      "کردن قدرت و زمان‌بندی دو دست."))
        elif sym < 80:
            out.append(dict(
                level="yellow", icon="info",
                title="تقارن نسبی دو دست",
                text="شاخص تقارن %.0f٪ است؛ فاصله تا محدوده ایده‌آل (بالای ۸۰٪) کم است."
                     % sym,
                drill="چند ست شنا با تأکید بر گیرش یکسان با هر دو دست."))
        else:
            out.append(dict(
                level="green", icon="check",
                title="تقارن مطلوب دو دست",
                text="شاخص تقارن %.0f٪ — تعادل بسیار خوبی بین کشش چپ و راست برقرار است."
                     % sym,
                drill="این تعادل را با حفظ تمرینات دوره‌ای تثبیت کنید."))

    # ۵) زانو ---------------------------------------------------------------
    warn, crit = _KNEE_LIM[style]
    knee_vals = [x for x in (_nanmax(r.bio.knee["L"]),
                             _nanmax(r.bio.knee["R"])) if x is not None]
    # هر دو آرنج/زانو می‌توانند کاملاً NaN باشند؛ max روی دنباله خالی خطا می‌داد
    knee_max = max(knee_vals) if knee_vals else None
    if knee_max is not None and knee_max > crit and style in ("CRAWL", "BACK"):
        out.append(dict(
            level="yellow", icon="body",
            title="بیش‌خم‌شدن زانو در ضربه پا",
            text="بیشینه خمش زانو به %.0f درجه رسید (حد مطلوب برای %s زیر %d درجه). "
                 "ضربه با زانوی خم از باسن قدرت نمی‌گیرد."
                 % (knee_max, STYLE_FA[style], crit),
            drill="ضربه پا با تخته در حالی که پاها صاف و کشیده نگه داشته می‌شوند؛ "
                  "تمرکز بر حرکت از مفصل ران."))

    # ۶) نرخ ضربه و طول ضربه ------------------------------------------------
    spm = _finite(r.strokes.spm_avg)
    sl = _finite(r.perf.sl_mean)
    if spm and sl:
        if spm > 60 and sl < 1.2:
            out.append(dict(
                level="yellow", icon="gauge",
                title="ضربه‌های کوتاه و پرتکرار",
                text="نرخ ضربه %.0f SPM با طول ضربه میانگین %.2f متر؛ به نظر می‌رسد "
                     "به‌جای کشش کامل، دست‌ها را سریع وارد آب می‌کنید." % (spm, sl),
                drill="شنا با شمارش ضربه (Stroke-Count Golf): هدف کاهش تعداد ضربه در "
                      "هر طول استخر با گلاید طولانی‌تر."))
        elif spm < 28:
            out.append(dict(
                level="info", icon="gauge",
                title="نرخ ضربه پایین",
                text="میانگین نرخ ضربه %.0f SPM است. اگر سرعت میانگین نیز پایین است، "
                     "احتمالاً فاز کشش یا زمان‌بندی نیاز به تمرین دارد." % spm,
                drill="تمرینات تمپو با مترونوم شنا برای یافتن ریتم بهینه."))
        else:
            out.append(dict(
                level="green", icon="check",
                title="تعادل مناسب نرخ و طول ضربه",
                text="نرخ %.0f ضربه در دقیقه در کنار طول ضربه %.2f متری، الگوی متعادلی "
                     "را نشان می‌دهد." % (spm, sl),
                drill="برای ارتقا، هر هفته یک ست را روی افزایش طول ضربه کار کنید."))

    # ۷) کارایی و SWOLF -----------------------------------------------------
    swolf = _finite(r.perf.swolf_est)
    if swolf:
        out.append(dict(
            level="info", icon="chart",
            title="شاخص SWOLF و روند بهبود",
            text="SWOLF تخمینی برابر %.1f است (هرچه کمتر، کارایی بالاتر). این عدد "
                 "را به‌عنوان خط پایه در همین استخر ثبت کنید و در جلسات بعدی کاهش آن "
                 "را هدف بگیرید." % swolf,
            drill="هر جلسه یک طول را با تمام سرعت شنا کنید و SWOLF را در تاریخچه ثبت کنید."))

    # ۸) کیفیت داده و فیلم‌برداری ------------------------------------------
    if r.pose_raw.detect_ratio < 0.6:
        out.append(dict(
            level="yellow", icon="video",
            title="کاهش کیفیت تشخیص اسکلت",
            text="فقط در %.0f٪ فریم‌ها بدن کامل شناسایی شد. دقت نتایج به زاویه دوربین، "
                 "نور و کف استخر وابسته است." % (100 * r.pose_raw.detect_ratio),
            drill="دوربین را ثابت، در ارتفاع لگن و از نمای پهلو، با نور یکنواخت "
                  "و بدون نور پشت‌زمینه قرار دهید."))
    if r.track.dominant_ratio < 0.7:
        out.append(dict(
            level="info", icon="video",
            title="تغییر زاویه دوربین در طول ویدیو",
            text="زاویه غالب فقط در %.0f٪ فریم‌ها پایدار بود؛ زاویه ثابت باعث "
                 "دقت بالاتر تحلیل می‌شود." % (100 * r.track.dominant_ratio),
            drill="در طول ضبط، دوربین را روی یک زاویه ثابت نگه دارید."))

    # کارت جمع‌بندی سبز ------------------------------------------------------
    crit_total = sum(ev.values())
    if crit_total == 0:
        out.insert(0, dict(
            level="green", icon="check",
            title="هیچ خطای تکنیکی بحرانی ثبت نشد",
            text="الگوی حرکتی در محدوده ایمن است. روی افزایش کارایی و سرعت تمرکز کنید.",
            drill="تمرینات سرعتی ۴×۲۵ متر با استراحت کامل."))

    # مرتب‌سازی بر اساس شدت
    order = {"red": 0, "yellow": 1, "info": 2, "green": 3}
    out.sort(key=lambda d: order[d["level"]])
    return out
