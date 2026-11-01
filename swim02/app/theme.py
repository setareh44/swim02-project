# -*- coding: utf-8 -*-
"""پالت رنگی، فونت و استایل‌شیت سراسری برنامه — تم تیره اقیانوسی."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


# --------------------------------------------------------------------------
# پالت رنگ
# --------------------------------------------------------------------------
class C:
    BG_DEEP = "#030b16"
    BG = "#061425"
    PANEL = "#0a1f36"
    PANEL_2 = "#0d2742"
    SIDEBAR = "#071a2e"
    BORDER = "#16384f"
    BORDER_HI = "#1f5475"

    TEXT = "#e8f3ff"
    MUTED = "#8fb3c9"
    FAINT = "#5d7f96"

    CYAN = "#22d3ee"
    TEAL = "#2dd4bf"
    BLUE = "#38bdf8"
    INDIGO = "#6366f1"
    VIOLET = "#a78bfa"

    GREEN = "#34d399"
    YELLOW = "#fbbf24"
    RED = "#f87171"
    ORANGE = "#fb923c"

    SHADOW = QColor(0, 0, 0, 140)


STATUS_COLOR = {0: C.FAINT, 1: C.GREEN, 2: C.YELLOW, 3: C.RED}

FONT_STACK = ("Vazirmatn", "Vazir", "Tahoma", "Segoe UI", "Iran Sans",
              "DejaVu Sans", "Arial")


def apply_font(app: QApplication) -> None:
    f = QFont()
    f.setFamilies(["Vazirmatn", "Vazir", "Tahoma", "Segoe UI",
                   "Iran Sans", "DejaVu Sans", "Arial"])
    f.setPixelSize(14)
    app.setFont(f)


def apply_palette(app: QApplication) -> None:
    """پالت تیره اقیانوسی برای همه ویجت‌های پیش‌فرض."""
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C.BG_DEEP))
    pal.setColor(QPalette.WindowText, QColor(C.TEXT))
    pal.setColor(QPalette.Base, QColor(C.BG))
    pal.setColor(QPalette.AlternateBase, QColor(C.PANEL))
    pal.setColor(QPalette.ToolTipBase, QColor(C.PANEL_2))
    pal.setColor(QPalette.ToolTipText, QColor(C.TEXT))
    pal.setColor(QPalette.Text, QColor(C.TEXT))
    pal.setColor(QPalette.Button, QColor(C.PANEL_2))
    pal.setColor(QPalette.ButtonText, QColor(C.TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor(C.FAINT))
    pal.setColor(QPalette.Highlight, QColor(C.CYAN))
    pal.setColor(QPalette.HighlightedText, QColor("#04202c"))
    pal.setColor(QPalette.BrightText, QColor(C.RED))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(C.FAINT))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(C.FAINT))
    app.setPalette(pal)


# --------------------------------------------------------------------------
# استایل‌شیت
# --------------------------------------------------------------------------
QSS = """
* {{
    outline: none;
}}
QWidget {{
    color: {text};
    font-family: "Vazirmatn", "Vazir", "Tahoma", "Segoe UI", "DejaVu Sans";
    font-size: 13px;
}}
QToolTip {{
    background: {panel2};
    color: {text};
    border: 1px solid {border_hi};
    padding: 5px 9px;
    border-radius: 6px;
}}
/* ---------- قاب کارت ---------- */
QFrame#card, QFrame#cardSoft {{
    background: rgba(10, 31, 54, 0.78);
    border: 1px solid {border};
    border-radius: 16px;
}}
QFrame#cardSoft {{
    background: rgba(13, 39, 66, 0.55);
}}
QFrame#kpi {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(34, 211, 238, 0.10), stop:1 rgba(99, 102, 241, 0.08));
    border: 1px solid {border};
    border-radius: 14px;
}}
QFrame#kpi:hover {{ border-color: {border_hi}; }}

QFrame#titleBar {{
    background: rgba(4, 14, 26, 0.92);
    border-bottom: 1px solid {border};
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
}}
QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #081d33, stop:1 #051322);
    border-left: 1px solid {border};
}}
QFrame#stageDone {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(52, 211, 153, 0.18), stop:1 rgba(52, 211, 153, 0.02));
    border: 1px solid rgba(52, 211, 153, 0.45);
    border-radius: 12px;
}}
QFrame#stageRun {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(34, 211, 238, 0.20), stop:1 rgba(34, 211, 238, 0.02));
    border: 1px solid rgba(34, 211, 238, 0.55);
    border-radius: 12px;
}}
QFrame#stageWait {{
    background: rgba(13, 39, 66, 0.45);
    border: 1px solid {border};
    border-radius: 12px;
}}
QFrame#stageErr {{
    background: rgba(248, 113, 113, 0.12);
    border: 1px solid rgba(248, 113, 113, 0.5);
    border-radius: 12px;
}}

/* ---------- برچسب‌ها ---------- */
QLabel#h1 {{ font-size: 30px; font-weight: 800; color: {text}; }}
QLabel#h2 {{ font-size: 20px; font-weight: 700; color: {text}; }}
QLabel#h3 {{ font-size: 15px; font-weight: 700; color: {text}; }}
QLabel#muted {{ color: {muted}; }}
QLabel#faint {{ color: {faint}; }}
QLabel#brand {{ font-size: 19px; font-weight: 800;
    color: {cyan}; letter-spacing: 1px; }}
QLabel#kpiValue {{ font-size: 24px; font-weight: 800; color: {text}; }}
QLabel#kpiUnit {{ font-size: 12px; color: {muted}; }}
QLabel#badge {{
    background: rgba(34, 211, 238, 0.14);
    color: {cyan};
    border: 1px solid rgba(34, 211, 238, 0.35);
    border-radius: 9px;
    padding: 3px 10px;
    font-weight: 700;
}}
QLabel#dropZone {{
    border: 2px dashed {border_hi};
    border-radius: 18px;
    background: rgba(13, 39, 66, 0.40);
    color: {muted};
}}
QLabel#dropZone[active="true"] {{
    border: 2px solid {cyan};
    background: rgba(34, 211, 238, 0.10);
    color: {text};
}}

/* ---------- دکمه‌ها ---------- */
QPushButton {{
    background: {panel2};
    border: 1px solid {border};
    border-radius: 11px;
    padding: 9px 16px;
    color: {text};
    font-weight: 600;
    /* متن دکمه‌ها هم راست‌چین است (Qt این را برای QPushButton پشتیبانی می‌کند) */
    text-align: right;
}}
QPushButton#primary {{
    text-align: center;
}}
QPushButton:hover {{ border-color: {border_hi}; background: #11355a; }}
QPushButton:pressed {{ background: #0c2945; }}
QPushButton:disabled {{ color: {faint}; border-color: {border};
    background: rgba(13, 39, 66, 0.35); }}

QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {cyan}, stop:1 {blue});
    color: #04202c;
    border: none;
    font-size: 15px;
    font-weight: 800;
    padding: 12px 26px;
    border-radius: 12px;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #54e0f5, stop:1 #67cdf9);
}}
QPushButton#primary:disabled {{
    background: rgba(34, 211, 238, 0.18);
    color: rgba(232, 243, 255, 0.45);
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid {border_hi};
}}
/* دکمه‌های کارت گزارش: هر سه یک اندازه و با فونت یکسان */
QPushButton[rp="pdf"] {{
    font-size: 14px;
    font-weight: 700;
    padding: 0px 12px;
}}
QPushButton#icon {{
    background: transparent; border: none; padding: 7px;
    border-radius: 9px;
}}
QPushButton#icon:hover {{ background: rgba(34, 211, 238, 0.12); }}

/* ---------- کنترل‌های پخش ویدیو ----------
   خودِ دکمه‌ها تصویر گویِ براق دارند (app/assets/media)؛ پس پس‌زمینه و قابِ
   QSS باید کاملاً شفاف باشد تا تصویر دیده شود و فقط با ماوس واکنش دهد. */
QPushButton#playBtn, QPushButton#stopBtn {{
    background: transparent;
    border: none;
    padding: 0px;
}}
QPushButton#playBtn:disabled, QPushButton#stopBtn:disabled {{
    background: transparent;
    border: none;
}}

/* آیتم‌های سایدبار: ویجت سفارشی تا متن همیشه راست‌چین بماند */
QFrame#navItem {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 12px;
}}
QFrame#navItem[hovered="true"] {{
    background: rgba(34, 211, 238, 0.08);
}}
QFrame#navItem[selected="true"] {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(34, 211, 238, 0.22), stop:1 rgba(56, 189, 248, 0.05));
    border: 1px solid rgba(34, 211, 238, 0.30);
}}
QFrame#navItem:disabled {{
    background: transparent;
}}

QPushButton#barBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0px;
}}
QPushButton#barBtn:hover {{ background: rgba(34, 211, 238, 0.14); }}

QPushButton#winBtn, QPushButton#winClose {{
    background: transparent; border: none; border-radius: 0px;
    padding: 0px;
}}
QPushButton#winBtn:hover {{ background: rgba(255,255,255,0.08); }}
QPushButton#winClose:hover {{ background: #e11d48; }}

/* ---------- ورودی‌ها ---------- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: rgba(6, 20, 37, 0.85);
    border: 1px solid {border};
    border-radius: 10px;
    padding: 7px 10px;
    color: {text};
    selection-background-color: {cyan};
    selection-color: #04202c;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{
    border-color: {border_hi};
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 22px;
    background: rgba(34, 211, 238, 0.10);
    border: none;
    border-radius: 6px;
    margin: 1px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: rgba(34, 211, 238, 0.28);
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-bottom: 6px solid {cyan};
    width: 0; height: 0;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {cyan};
    width: 0; height: 0;
}}
QComboBox QAbstractItemView {{
    background: {panel2};
    border: 1px solid {border_hi};
    border-radius: 8px;
    selection-background-color: rgba(34, 211, 238, 0.25);
    padding: 4px;
}}
QCheckBox {{ spacing: 8px; color: {text}; text-align: right; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border-radius: 5px; border: 1px solid {border_hi};
    background: rgba(6, 20, 37, 0.85);
}}
QCheckBox::indicator:checked {{
    background: {cyan};
    border: 1px solid {cyan};
    image: none;
}}

/* ---------- اسلایدر و نوار پیشرفت ---------- */
QSlider::groove:horizontal {{
    height: 5px; background: {border}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {cyan}, stop:1 {blue});
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #eaf7ff;
    width: 15px; height: 15px;
    margin: -6px 0;
    border-radius: 8px;
    border: 2px solid {cyan};
}}
QProgressBar {{
    background: rgba(6, 20, 37, 0.9);
    border: 1px solid {border};
    border-radius: 8px;
    height: 10px;
    text-align: center;
    color: {text};
    font-size: 11px;
}}
QProgressBar::chunk {{
    border-radius: 7px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {teal}, stop:0.5 {cyan}, stop:1 {blue});
}}

/* ---------- کنسول لاگ ---------- */
QPlainTextEdit, QTextEdit {{
    background: rgba(3, 11, 22, 0.88);
    border: 1px solid {border};
    border-radius: 12px;
    color: #9fd8e8;
    font-family: "Cascadia Code", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    padding: 8px;
}}

/* ---------- اسکرول ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {border_hi}; min-height: 34px; border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{ background: #2a6d96; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {border_hi}; min-width: 34px; border-radius: 5px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QStackedWidget, QWidget#pageRoot {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QAbstractItemView {{ background: {panel2}; }}
QSizeGrip {{ image: none; width: 14px; height: 14px; }}
""".format(
    text=C.TEXT, muted=C.MUTED, faint=C.FAINT,
    panel2=C.PANEL_2, border=C.BORDER, border_hi=C.BORDER_HI,
    cyan=C.CYAN, blue=C.BLUE, teal=C.TEAL,
)
