# -*- coding: utf-8 -*-
"""آیکون‌های برداری SVG (بدون فایل خارجی) با قابلیت تغییر رنگ."""
from __future__ import annotations

import os

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# مسیرهای SVG با viewBox=24 و stroke فعلی
_PATHS = {
    "home": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9.5h13V10"/>'
            '<path d="M10 19.5v-5h4v5"/>',
    "video": '<rect x="3" y="5" width="18" height="14" rx="2.5"/>'
             '<path d="M10 9.2v5.6l4.8-2.8z" fill="currentColor" stroke="none"/>'
             '<path d="M3 9.5h18M3 14.5h18"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "report": '<rect x="5" y="3.5" width="14" height="17" rx="2.5"/>'
              '<path d="M9 8.5h6M9 12.5h6M9 16.5h3.5"/>',
    "play": '<path d="M7.5 5.5v13l11-6.5z" fill="currentColor" stroke="none"/>',
    # نمادهای استاندارد پخش‌کنندهٔ ویدیو: گوشه‌های گِرد و ترازِ نوری درست
    # مثلث کمی به راست جابه‌جا شده تا از نظر نوری وسط دایره بنشیند
    "media_play": '<path d="M8.4 4.7 20.2 12 8.4 19.3z" fill="currentColor" '
                  'stroke="currentColor" stroke-width="2.6"/>',
    "media_pause": '<rect x="7.6" y="4.6" width="3.7" height="14.8" rx="1.7" '
                   'fill="currentColor" stroke="none"/>'
                   '<rect x="12.7" y="4.6" width="3.7" height="14.8" rx="1.7" '
                   'fill="currentColor" stroke="none"/>',
    "media_stop": '<rect x="6.2" y="6.2" width="11.6" height="11.6" rx="3.2" '
                  'fill="currentColor" stroke="none"/>',
    "pause": '<rect x="7" y="5" width="3.6" height="14" rx="1.2" fill="currentColor" stroke="none"/>'
             '<rect x="13.4" y="5" width="3.6" height="14" rx="1.2" fill="currentColor" stroke="none"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" stroke="none"/>',
    "folder": '<path d="M3 7.5a2 2 0 0 1 2-2h4l2 2.2h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "settings": '<circle cx="12" cy="12" r="3.2"/>'
                '<path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4'
                'M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "minus": '<path d="M5 12h14"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "restore": '<rect x="8" y="8" width="11" height="11" rx="2"/>'
               '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v4.5h-4.5"/>',
    "check": '<path d="M4.5 12.5l5 5L19.5 7"/>',
    "warning": '<path d="M12 4 2.8 19.5h18.4z"/><path d="M12 10v4.2"/>'
               '<circle cx="12" cy="17.2" r="1.1" fill="currentColor" stroke="none"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/>'
            '<circle cx="12" cy="7.8" r="1.1" fill="currentColor" stroke="none"/>',
    "export": '<path d="M12 3.5V15"/><path d="m7.5 8 4.5-4.5L16.5 8"/>'
              '<path d="M4.5 14.5V18a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3.5"/>',
    "lock": '<rect x="5.5" y="10.5" width="13" height="10" rx="2.2"/>'
            '<path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
    "wave": '<path d="M2 9c2.2-2.4 4.2-2.4 6.4 0s4.2 2.4 6.4 0 4.2-2.4 6.4 0"/>'
            '<path d="M2 15c2.2-2.4 4.2-2.4 6.4 0s4.2 2.4 6.4 0 4.2-2.4 6.4 0"/>',
    "speed": '<path d="M12 21a8.5 8.5 0 1 1 8.5-8.5"/><path d="M12 12.5 17 8"/>'
             '<circle cx="12" cy="12.5" r="1.6" fill="currentColor" stroke="none"/>',
    "gauge": '<path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l4.5-4.5"/>'
             '<circle cx="12" cy="15" r="1.5" fill="currentColor" stroke="none"/>',
    "body": '<circle cx="12" cy="5" r="2.2"/><path d="M12 7.5v6"/>'
            '<path d="M12 9.5 7.5 12M12 9.5l4.5 2.5M12 13.5l-4 6.5M12 13.5l4 6.5"/>',
    "printer": '<path d="M7 9V4.5h10V9"/>'
               '<rect x="3.5" y="9" width="17" height="7.5" rx="2"/>'
               '<rect x="7" y="14" width="10" height="5.5" rx="1.2"/>'
               '<circle cx="17" cy="11.6" r="0.9" fill="currentColor" stroke="none"/>',
    "pdf": '<path d="M6 3.5h7.5L19 9v11.5H6z"/><path d="M13.5 3.5V9H19"/>'
           '<path d="M9.5 13.5h5M9.5 16.5h3.5"/>',
    "speaker": '<path d="M4 9.5h3.5L12 6v12L7.5 14.5H4z"/>'
               '<path d="M15.5 9a4 4 0 0 1 0 6"/><path d="M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    "speaker_off": '<path d="M4 9.5h3.5L12 6v12L7.5 14.5H4z"/>'
                   '<path d="M16 10l4 4M20 10l-4 4"/>',
    "user": '<circle cx="12" cy="8" r="3.6"/>'
            '<path d="M4.8 20.2c0-3.6 3.2-6.2 7.2-6.2s7.2 2.6 7.2 6.2"/>',
    "music": '<path d="M9 18.5V6.2l9-2.2v12.2"/>'
             '<circle cx="6.8" cy="18.5" r="2.3"/><circle cx="15.8" cy="16.2" r="2.3"/>',
}


def _svg(name: str, color: str, width: float = 1.7) -> QByteArray:
    body = _PATHS[name]
    return QByteArray(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        # `color` برای شکل‌هایی است که fill="currentColor" دارند (مثلث پخش،
        # مربع توقف، نقطه‌های هشدار). بدون این، Qt آن‌ها را همیشه **مشکی**
        # رسم می‌کند — همان چیزی که دکمه‌ها را سیاه و زشت نشان می‌داد.
        f'color="{color}" '
        f'fill="none" stroke="{color}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
        .encode("utf-8"))


def pixmap(name: str, color: str = "#e8f3ff", size: int = 22) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    r = QSvgRenderer(_svg(name, color))
    p = QPainter(pm)
    r.render(p)
    p.end()
    return pm


def icon(name: str, color: str = "#e8f3ff", size: int = 22) -> QIcon:
    return QIcon(pixmap(name, color, size))


def styled_icon(name: str, color: str, size: int = 22) -> QIcon:
    """مناسب برای دکمه‌هایی که رنگ ثابت می‌خواهند."""
    base = pixmap(name, color, size)
    disabled = QPixmap(base.size())
    disabled.fill(Qt.transparent)
    p = QPainter(disabled)
    p.setOpacity(0.35)
    p.drawPixmap(0, 0, base)
    p.end()
    ic = QIcon()
    ic.addPixmap(base, QIcon.Normal)
    ic.addPixmap(disabled, QIcon.Disabled)
    return ic

# ---------------------------------------------------------------- media buttons
#: پوشهٔ تصویرهای آمادهٔ دکمه‌های پخش/مکث/توقف
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "media")
_MEDIA_CACHE: dict[tuple[str, str], QPixmap] = {}


def media_pixmap(name: str, variant: str = "normal") -> QPixmap:
    """تصویر دکمهٔ رسانه‌ای (گوی براق) از ``app/assets/media``."""
    file = name if variant == "normal" else "%s_%s" % (name, variant)
    key = (file, variant)
    if key in _MEDIA_CACHE:
        return _MEDIA_CACHE[key]
    path = os.path.join(MEDIA_DIR, "%s.png" % file)
    pm = QPixmap(path)
    if pm.isNull():                       # فایل نبود: جایگزین متنی نگذاریم
        pm = pixmap("media_play", "#1e188a", 64)
    _MEDIA_CACHE[key] = pm
    return pm


def media_icon(name: str) -> QIcon:
    """آیکون سه‌حالته (عادی/هوور/غیرفعال) برای دکمه‌های پخش و توقف."""
    ic = QIcon()
    for variant, state in (("normal", QIcon.Normal), ("hover", QIcon.Active),
                           ("disabled", QIcon.Disabled)):
        base = media_pixmap(name, variant)
        ic.addPixmap(base, state, QIcon.Off)
        # اندازهٔ نمایشی کوچک‌تر هم اضافه می‌شود تا Qt پیکسل‌به‌پیکسل
        # رسم کند و روی نمایشگر HiDPI لبه‌ها نرم و شارپ بمانند
        ic.addPixmap(base.scaled(56, 56, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation), state, QIcon.Off)
    return ic
