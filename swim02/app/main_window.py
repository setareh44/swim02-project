# -*- coding: utf-8 -*-
"""پنجره اصلی: فریم‌لس با نوار عنوان سفارشی، سایدبار، پس‌زمینه OpenGL و ناوبری."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, QThread, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QBoxLayout, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from . import about_info, diagnostics, icons, prefs
from .about_dialog import show_about
from .auth import AuthService, Session
from .history import HistoryStore
from .rtl import apply_rtl_tree
from .gl_background import PoolBackground, _GLCanvas
from .pipeline_worker import AnalysisWorker
from .sound import play_startup_sound
from .theme import C
from .toast import notify
from .pages.analyze_page import AnalyzePage
from .pages.athlete_page import AthletePage
from .pages.charts_page import ChartsPage
from .pages.coach_page import CoachPage
from .pages.home_page import HomePage, VIDEO_EXTS
from .pages.report_page import ReportPage

_EDGE = 7


class NavItem(QFrame):
    """آیتم سایدبار: آیکون در سمت چپ، متن راست‌چین در سمت راست.

    این ویجت جای QPushButton نشسته تا چیدمان مستقل از جهت‌گیری سراسری باشد
    (در RTL ویجت‌های استاندارد آیکون و متن را جابه‌جا می‌کنند و متن از لبهٔ
    راست فاصله می‌گیرد).
    """

    clicked = Signal()

    def __init__(self, text: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("navItem")
        self.icon_name = icon_name
        # جهت‌گیری خود ویجت هم چپ‌به‌راست است تا Qt هنگام تغییر جهت سراسری،
        # جای آیکون و متن را جابه‌جا نکند.
        self.setLayoutDirection(Qt.LeftToRight)
        self.setProperty("keepDirection", True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setProperty("selected", False)
        self.setProperty("hovered", False)
        self.setMinimumHeight(46)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(10)
        lay.setDirection(QBoxLayout.LeftToRight)    # آیکون چپ، متن راست

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(22, 22)
        lay.addWidget(self.icon_lbl, 0, Qt.AlignVCenter)

        self.text_lbl = QLabel(text)
        self.text_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.text_lbl.setStyleSheet("font-size:14px; font-weight:600;")
        lay.addWidget(self.text_lbl, 1)

        self._apply_colors()

    # ------------------------------------------------------------------
    def set_active(self, on: bool) -> None:
        self.setProperty("selected", bool(on))
        self._refresh()
        self._apply_colors()

    def set_disabled(self, off: bool) -> None:
        self.setProperty("disabled", bool(off))
        self.setEnabled(not off)
        self._refresh()
        self._apply_colors()

    def _apply_colors(self) -> None:
        # ممکن است پیش از ساخت فرزندان (در زمان تنظیم ویژگی‌ها) صدا زده شود
        if not hasattr(self, "icon_lbl") or not hasattr(self, "text_lbl"):
            return
        if not self.isEnabled():
            color = C.FAINT
        elif self.property("selected"):
            color = C.CYAN
        elif self.property("hovered"):
            color = C.TEXT
        else:
            color = C.MUTED
        self.icon_lbl.setPixmap(icons.pixmap(self.icon_name, color, 20))
        self.text_lbl.setStyleSheet(
            "font-size:14px; font-weight:%s; color:%s;"
            % ("800" if self.property("selected") else "600", color))

    def _refresh(self) -> None:
        if not hasattr(self, "icon_lbl"):
            return
        self.style().unpolish(self)
        self.style().polish(self)

    # ------------------------------------------------------------------
    def setText(self, text: str) -> None:      # سازگاری با کد قبلی
        self.text_lbl.setText(text)

    def text(self) -> str:
        return self.text_lbl.text()

    def enterEvent(self, e):
        self.setProperty("hovered", True)
        self._refresh()
        self._apply_colors()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setProperty("hovered", False)
        self._refresh()
        self._apply_colors()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def changeEvent(self, e):
        super().changeEvent(e)
        self._apply_colors()


class MainWindow(QWidget):
    def __init__(self, session: Session | None = None,
                 auth: AuthService | None = None,
                 auth_required: bool = False):
        super().__init__()
        self.setWindowTitle("SWIM-AI — تحلیل بیومکانیک شنا")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1320, 840)
        self.setMinimumSize(1120, 720)
        self.setAcceptDrops(True)

        self.results = None
        self._thread = None
        self._worker = None
        self._drag_pos = None
        self._resize_edge = None
        self._resize_geo = None

        # RBAC session (None => legacy no-auth mode, everything unlocked)
        self.session = session
        self.auth = auth or AuthService()
        self.auth_required = bool(auth_required)
        self.history = HistoryStore()
        # admin flow: analysis started from the coach panel for this athlete
        self.pending_athlete_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)

        self.frame = QFrame()
        self.frame.setObjectName("rootFrame")
        self.frame.setStyleSheet(
            "#rootFrame{background:%s; border:1px solid %s; border-radius:18px;}"
            % (C.BG_DEEP, C.BORDER))
        root.addWidget(self.frame)
        fl = QVBoxLayout(self.frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)

        # قالب اصلی (سایدبار چپ + محتوا) عمداً چپ‌به‌راست می‌ماند تا با نوار
        # عنوانِ سفارشی هم‌راستا باشد؛ فقط *متنِ* داخل ویجت‌ها راست‌چین می‌شود
        # (توسط app/rtl.py). اگر این‌جا RTL شود، سایدبار و محتوا جای هم می‌افتند.
        self.setProperty("keepDirection", True)

        self._build_titlebar(fl)
        self._build_body(fl)
        apply_rtl_tree(self)

    # ------------------------------------------------------------------
    def _build_titlebar(self, parent_layout: QVBoxLayout):
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(52)
        # چیدمان نوار عنوان عمداً چپ‌به‌راست است تا نام برنامه در سمت چپ و
        # دکمه‌های پنجره در سمت راست بمانند (مستقل از RTL بودن کل برنامه).
        bar.setLayoutDirection(Qt.LeftToRight)
        bar.setProperty("keepDirection", True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 8, 0)
        lay.setDirection(QBoxLayout.LeftToRight)
        lay.setSpacing(6)

        brand = QLabel(about_info.APP_NAME)
        brand.setObjectName("brand")
        brand.setProperty("keepAlign", True)
        brand.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title = QLabel(about_info.APP_TAGLINE)
        title.setObjectName("faint")
        title.setProperty("keepAlign", True)
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size:12px;")
        lay.addWidget(brand)
        lay.addSpacing(10)
        lay.addWidget(title)
        lay.addStretch(1)

        # دکمه‌های کمکی (از چپ به راست: درباره، صدا) و سپس دکمه‌های پنجره
        self.btn_about = self._bar_btn("info", "دربارهٔ نرم‌افزار",
                                       lambda: self.show_about_dialog())
        self.btn_sound = self._bar_btn(
            "speaker" if prefs.get_bool(prefs.KEY_SOUND, True) else "speaker_off",
            "روشن/خاموش کردن موزیک شروع", lambda: self._toggle_sound())
        lay.addWidget(self.btn_about)
        lay.addWidget(self.btn_sound)
        lay.addSpacing(6)

        self.btn_min = self._win_btn("minus", C.MUTED, self.showMinimized)
        self.btn_max = self._win_btn("maximize", C.MUTED, self._toggle_max)
        self.btn_close = self._win_btn("close", C.MUTED, self.close)
        self.btn_min.setObjectName("winBtn")
        self.btn_max.setObjectName("winBtn")
        self.btn_close.setObjectName("winClose")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setFixedSize(44, 36)
            lay.addWidget(b)
        parent_layout.addWidget(bar)
        bar.mousePressEvent = self._bar_press
        bar.mouseMoveEvent = self._bar_move
        bar.mouseDoubleClickEvent = lambda e: self._toggle_max()

    def _win_btn(self, icon_name: str, color: str, slot) -> QPushButton:
        b = QPushButton()
        b.setIcon(icons.icon(icon_name, color, 17))
        b.setToolTip({"minus": "کوچک کردن", "maximize": "بزرگ کردن",
                      "close": "بستن"}.get(icon_name, ""))
        b.clicked.connect(slot)
        b.setCursor(QCursor(Qt.PointingHandCursor))
        return b

    def _bar_btn(self, icon_name: str, tip: str, slot) -> QPushButton:
        b = QPushButton()
        b.setObjectName("barBtn")
        b.setIcon(icons.icon(icon_name, C.MUTED, 18))
        b.setToolTip(tip)
        b.setFixedSize(36, 32)
        b.setCursor(QCursor(Qt.PointingHandCursor))
        b.clicked.connect(slot)
        return b

    # ------------------------------------------------------------------
    def show_about_dialog(self, first_run: bool = False):
        dont = show_about(self, first_run=first_run)
        if dont:
            prefs.set_bool(prefs.KEY_ABOUT_SEEN, True)
        notify(self, "SWIM-AI — ساختهٔ %s" % about_info.AUTHOR, "info")
        return dont

    def maybe_show_first_run(self) -> None:
        """اولین اجرا: پنجرهٔ «درباره» با تیک «دیگر نمایش نده»."""
        if prefs.get_bool(prefs.KEY_ABOUT_SEEN, False):
            return
        self.show_about_dialog(first_run=True)

    def _toggle_sound(self) -> None:
        on = not prefs.get_bool(prefs.KEY_SOUND, True)
        prefs.set_bool(prefs.KEY_SOUND, on)
        self.btn_sound.setIcon(icons.icon("speaker" if on else "speaker_off",
                                          C.MUTED, 18))
        if on:
            play_startup_sound()
            notify(self, "موزیک شروع روشن شد", "success")
        else:
            notify(self, "موزیک شروع خاموش شد", "info")

    def _bar_press(self, e):
        if e.button() == Qt.LeftButton and not self.isMaximized():
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _bar_move(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setIcon(icons.icon("maximize", C.MUTED, 17))
        else:
            self.showMaximized()
            self.btn_max.setIcon(icons.icon("restore", C.MUTED, 17))

    # ------------------------------------------------------------------
    def _build_body(self, parent_layout: QVBoxLayout):
        body = QWidget()
        lay = QHBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # سایدبار (در چیدمان RTL سمت راست قرار می‌گیرد)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(232)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(14, 20, 14, 16)
        sl.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(icons.pixmap("wave", C.CYAN, 30))
        logo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        logo_t = QLabel("داشبورد تحلیل")
        logo_t.setObjectName("h3")
        logo_t.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.addWidget(logo)
        sl.addWidget(logo_t)
        sl.addSpacing(10)

        self.navs = []
        for i, (name, icn) in enumerate((
                ("خانه و ویدیو", "home"),
                ("اجرای تحلیل", "wave"),
                ("نمودارها", "chart"),
                ("گزارش و پیشنهاد", "report"),
                ("پرونده شناگر", "user"),
                ("پنل مربی", "settings"))):
            b = NavItem(name, icn)
            b.clicked.connect(lambda idx=i: self.set_page(idx))
            self.navs.append(b)
            sl.addWidget(b)
        sl.addStretch(1)

        # logged-in user + logout (only in auth mode)
        self.user_lbl = QLabel()
        self.user_lbl.setObjectName("faint")
        self.user_lbl.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        self.user_lbl.setStyleSheet("font-size:11px; padding:2px;")
        self.user_lbl.setWordWrap(True)
        sl.addWidget(self.user_lbl)
        self.btn_logout = QPushButton("  خروج از حساب")
        self.btn_logout.setObjectName("ghost")
        self.btn_logout.setLayoutDirection(Qt.RightToLeft)
        self.btn_logout.setIcon(icons.icon("lock", C.YELLOW, 17))
        self.btn_logout.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_logout.clicked.connect(self._logout)
        sl.addWidget(self.btn_logout)

        # دکمهٔ درباره در پایین سایدبار (همان پنجرهٔ نوار عنوان)
        self.btn_about_side = QPushButton("  دربارهٔ نرم‌افزار")
        self.btn_about_side.setObjectName("ghost")
        self.btn_about_side.setLayoutDirection(Qt.RightToLeft)
        self.btn_about_side.setIcon(icons.icon("info", C.CYAN, 17))
        self.btn_about_side.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_about_side.clicked.connect(lambda: self.show_about_dialog())
        sl.addWidget(self.btn_about_side)

        foot = QLabel("ساختهٔ %s\n%s" % (about_info.AUTHOR,
                                         about_info.version_line()))
        foot.setObjectName("faint")
        foot.setAlignment(Qt.AlignRight)
        foot.setStyleSheet("font-size:10px; padding:4px 2px;")
        sl.addWidget(foot)

        self.gl_badge = QLabel()
        self.gl_badge.setWordWrap(True)
        self.gl_badge.setObjectName("faint")
        self.gl_badge.setAlignment(Qt.AlignRight)
        self.gl_badge.setStyleSheet("font-size:11px; padding:8px;")
        sl.addWidget(self.gl_badge)
        lay.addWidget(self.sidebar)

        # ناحیه محتوا: پس‌زمینه GL و صفحات شفاف روی یک سلول گرید (روی هم)
        content = QWidget()
        cg = QGridLayout(content)
        cg.setContentsMargins(0, 0, 0, 0)
        cg.setSpacing(0)
        self.bg = PoolBackground(content)
        self.stack = QStackedWidget()
        self.home = HomePage()
        self.analyze = AnalyzePage()
        self.charts = ChartsPage()
        self.report = ReportPage()
        self.athlete = AthletePage()
        self.coach = CoachPage(self.auth)
        for p in (self.home, self.analyze, self.charts, self.report,
                  self.athlete, self.coach):
            self.stack.addWidget(p)
        cg.addWidget(self.bg, 0, 0)
        cg.addWidget(self.stack, 0, 0)
        self.stack.raise_()
        lay.addWidget(content, 1)
        parent_layout.addWidget(body, 1)

        # اتصال سیگنال‌ها
        self.home.start_requested.connect(self._start)
        self.analyze.goto_charts.connect(lambda: self.set_page(2))
        self.analyze.goto_report.connect(lambda: self.set_page(3))
        self.analyze.retry.connect(self._retry)
        self.analyze.cancel_requested.connect(self._cancel_analysis)
        self.coach.run_for_athlete.connect(self._run_for_athlete)
        self.set_page(0, quiet=True)
        self.set_session(self.session)
        self._update_gl_badge()

    def _update_gl_badge(self):
        if isinstance(self.bg.canvas, _GLCanvas):
            self.gl_badge.setText("● موتور رندر: OpenGL GLSL\nپس‌زمینه متحرک استخر فعال است")
            self.gl_badge.setStyleSheet(
                "font-size:11px; padding:8px; color:%s;" % C.TEAL)
        else:
            self.gl_badge.setText("● موتور رندر: نرم‌افزاری (QPainter)\n"
                                  "OpenGL در این سیستم در دسترس نیست")
            self.gl_badge.setStyleSheet(
                "font-size:11px; padding:8px; color:%s;" % C.YELLOW)

    # ------------------------------------------------------------------
    PAGE_NAMES = ("خانه و ویدیو", "اجرای تحلیل", "نمودارها", "گزارش و پیشنهاد",
                  "پرونده شناگر", "پنل مربی")

    def _page_allowed(self, idx: int) -> bool:
        """RBAC gate for sidebar pages."""
        if idx in (2, 3) and self.results is None:
            return False
        if not self.auth_required:
            return True
        if self.session is None:
            return idx not in (4, 5)
        if idx == 4:
            return True                      # athlete page: own view / hint
        if idx == 5:
            return self.session.is_admin     # coach panel: admin only
        return True

    def _refresh_nav_access(self) -> None:
        for i, b in enumerate(self.navs):
            ok = self._page_allowed(i)
            if i in (2, 3):
                ok = ok and self.results is not None
            b.setEnabled(ok)

    def set_page(self, idx: int, quiet: bool = False):
        if idx in (2, 3) and self.results is None:
            notify(self, "برای دیدن این بخش، اول یک تحلیل را کامل کنید",
                   "warning")
            return
        if not self._page_allowed(idx):
            if idx == 5:
                notify(self, "پنل مربی فقط برای مدیر/مربی است", "warning")
            elif idx == 4:
                notify(self, "برای دیدن پرونده، وارد حساب شوید", "warning")
            return
        if idx == 4:
            self.athlete.refresh(self.session, self.auth)
        elif idx == 5:
            self.coach.set_auth(self.auth)
            self.coach.refresh_list()
            self.coach.set_session(self.session)
        self.stack.setCurrentIndex(idx)
        if not quiet:
            notify(self, "صفحهٔ «%s»" % self.PAGE_NAMES[idx], "info", 1600)
        for i, b in enumerate(self.navs):
            b.set_active(i == idx)
        self._refresh_nav_access()

    # ------------------------------------------------------------------
    # RBAC session handling
    # ------------------------------------------------------------------
    def set_session(self, session: Session | None) -> None:
        self.session = session
        self.coach.set_auth(self.auth)
        if session is None:
            self.user_lbl.setText("")
            self.btn_logout.setVisible(False)
        else:
            role = "مدیر/مربی" if session.is_admin else "شناگر"
            self.user_lbl.setText("👤 %s\n(%s)" % (session.display_name,
                                                  role))
            self.btn_logout.setVisible(self.auth_required)
        self._refresh_nav_access()

    def _logout(self) -> None:
        from .login_dialog import LoginDialog, QuoteDialog
        dlg = LoginDialog(self.auth, self)
        if dlg.exec() != dlg.Accepted or dlg.session is None:
            notify(self, "نشست قبلی حفظ شد", "info", 1800)
            return
        self.set_session(dlg.session)
        notify(self, "خوش آمدید، %s ✓" % dlg.session.display_name,
               "success")
        if dlg.session.is_athlete and dlg.quote_info:
            fa, personal, speak = dlg.quote_info
            self.athlete.refresh(dlg.session, self.auth)
            self.athlete.show_quote_card(fa, personal, speak)
            QuoteDialog(fa, personal, speak, self).exec()
            self.set_page(4, quiet=True)

    # ------------------------------------------------------------------
    def _run_for_athlete(self, athlete_id: str) -> None:
        """Coach panel shortcut: run the next analysis for this athlete."""
        self.pending_athlete_id = athlete_id
        user = self.auth.store.get(athlete_id)
        name = user.name if user else athlete_id
        notify(self, "تحلیل بعدی برای «%s» ثبت می‌شود" % name, "info")
        self.set_page(0, quiet=True)

    def _start(self, settings: dict):
        if self._thread is not None and self._thread.isRunning():
            return
        # RBAC: uploading / running analyses is a coach (admin) grant
        if (self.auth_required and self.session is not None
                and self.session.is_athlete):
            notify(self, "اجرای تحلیل فقط برای مربی/مدیر است", "warning")
            return
        self.results = None
        self.set_page(1, quiet=True)
        notify(self, "تحلیل آغاز شد؛ بسته به طول ویدیو چند دقیقه طول می‌کشد",
               "info")
        for i in (2, 3):
            self.navs[i].setEnabled(False)
        self.analyze.reset()
        # نشانگر: اگر برنامه همین‌جا کرش کند، اجرای بعدی علتش را نشان می‌دهد
        diagnostics.mark_analysis(self.home.video_path, "extract")
        # انیمیشن پس‌زمینه را در طول تحلیل متوقف کن (کمتر شدن فشار GPU/CPU و
        # حذف یک منبع احتمالی ناپایداری OpenGL هنگام کار سنگین)
        try:
            self.bg.pause()
        except Exception:
            pass
        self._worker = AnalysisWorker(self.home.video_path, settings)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.stage.connect(self._on_stage)
        self._worker.progress.connect(self.analyze.on_progress)
        self._worker.log.connect(self.analyze.append_log)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(self._on_finished)
        # هر سه مسیر پایانی باید حلقه رویداد نخ را ببندند
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    _STAGE_KEYS = ("extract", "analyze", "analyze", "analyze", "analyze",
                   "render")

    def _on_stage(self, idx: int, text: str):
        self.analyze.on_stage(idx, text)
        if 0 <= idx < len(self._STAGE_KEYS):
            diagnostics.update_marker_stage(self._STAGE_KEYS[idx])

    # ------------------------------------------------------------------
    def show_previous_crash(self, data: dict):
        """پیام فارسی + فایل‌های گزارش، وقتی اجرای قبلی وسط تحلیل بسته شد."""
        from PySide6.QtWidgets import QMessageBox

        summary = diagnostics.crash_summary(data)
        notify(self, "اجرای قبلی وسط تحلیل بسته شد — جزئیات در fatal.log",
               "error", 8000)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("گزارش بسته‌شدن ناگهانی")
        box.setText(summary)
        detail = []
        if data.get("video"):
            detail.append("فایل ویدیو: %s" % data["video"])
        if data.get("started"):
            detail.append("زمان شروع: %s" % data["started"])
        detail.append("\n--- fatal.log ---\n%s" % (data.get("fatal") or "-"))
        detail.append("\n--- crash_log.txt ---\n%s"
                      % (data.get("crash_log") or "-"))
        detail.append("\n--- system_info.txt ---\n%s"
                      % diagnostics.system_info())
        box.setDetailedText("\n".join(detail)[:8000])
        open_btn = box.addButton("باز کردن پوشهٔ گزارش",
                                 QMessageBox.ActionRole)
        box.addButton("بستن", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() is open_btn:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(diagnostics.log_dir()))

    # ------------------------------------------------------------------
    def _retry(self):
        self._start(self.home.settings())

    def _cancel_analysis(self):
        """دکمه «توقف تحلیل»: پایپلاین بین فریم‌ها متوقف می‌شود."""
        if self._worker is not None:
            self._worker.stop()

    def _resume_background(self):
        try:
            self.bg.resume()
        except Exception:
            pass

    def _cleanup_thread(self):
        self._resume_background()
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    def _on_finished(self, results, out_video: str, out_json: str):
        diagnostics.clear_analysis_marker()
        self.results = results
        notify(self, "تحلیل کامل شد ✓ گزارش و نمودارها آماده است", "success", 3500)
        self.charts.set_results(results)
        self.report.set_results(results, out_video, out_json)
        self.analyze.on_finished(results, out_video, out_json)
        for i in (2, 3):
            self.navs[i].setEnabled(True)
        # archive the result in the athlete's longitudinal history
        try:
            target = None
            if self.session is not None and self.session.is_athlete:
                target = self.session.user_id
            elif self.pending_athlete_id:
                target = self.pending_athlete_id
            if target and out_json:
                self.history.record_from_files(target, out_json, out_video)
                notify(self, "نتیجه در پرونده شناگر بایگانی شد", "success",
                       2200)
        except Exception:
            pass
        finally:
            self.pending_athlete_id = None

    def _on_failed(self, msg: str):
        diagnostics.clear_analysis_marker()
        self.analyze.on_failed(msg)
        notify(self, "تحلیل با خطا متوقف شد", "error", 4000)

    def _on_cancelled(self):
        diagnostics.clear_analysis_marker()
        self.analyze.on_cancelled()
        notify(self, "تحلیل به‌درخواست شما متوقف شد", "warning")

    # ------------------------------------------------------------------
    # کشیدن و رها کردن فایل در کل پنجره
    # ------------------------------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(VIDEO_EXTS):
                self.set_page(0)
                self.home.set_video(path)
                break

    # ------------------------------------------------------------------
    # تغییر اندازه از لبه‌ها (پنجره فریم‌لس)
    # ------------------------------------------------------------------
    def _edge_at(self, pos: QPoint) -> str:
        r = self.rect()
        left = pos.x() <= _EDGE
        right = pos.x() >= r.width() - _EDGE
        top = pos.y() <= _EDGE
        bottom = pos.y() >= r.height() - _EDGE
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return ""

    def resizeEvent(self, e):
        super().resizeEvent(e)
        mgr = getattr(self, "_swim_toasts", None)
        if mgr is not None:
            mgr.reposition()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.isMaximized():
            edge = self._edge_at(e.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_geo = self.geometry()

    def mouseMoveEvent(self, e):
        if self._resize_edge and e.buttons() & Qt.LeftButton:
            self._do_resize(e.globalPosition().toPoint())
            return
        if not self.isMaximized():
            edge = self._edge_at(e.position().toPoint())
            self.setCursor({
                "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
                "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            }.get(edge, Qt.ArrowCursor))

    def mouseReleaseEvent(self, e):
        self._resize_edge = None
        self._resize_geo = None

    def _do_resize(self, gpos: QPoint):
        g = QRect(self._resize_geo)
        dx = gpos.x() - g.right()
        dy = gpos.y() - g.bottom()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        edge = self._resize_edge
        if "r" in edge:
            g.setWidth(max(min_w, g.width() + dx))
        if "b" in edge:
            g.setHeight(max(min_h, g.height() + dy))
        if "l" in edge:
            new_w = max(min_w, self._resize_geo.width() -
                        (gpos.x() - self._resize_geo.left()))
            g.setLeft(self._resize_geo.right() - new_w)
        if "t" in edge:
            new_h = max(min_h, self._resize_geo.height() -
                        (gpos.y() - self._resize_geo.top()))
            g.setTop(self._resize_geo.bottom() - new_h)
        self.setGeometry(g)

    # ------------------------------------------------------------------
    def closeEvent(self, e):
        try:
            self.analyze.shutdown()
        except Exception:
            pass
        if self._thread is not None and self._thread.isRunning():
            # اول لغو همکارانه، بعد بستن حلقه رویداد؛ در نهایت انتظار کوتاه.
            # بدون این ترتیب، QThread در حال اجرا نابود می‌شود و برنامه کرش می‌کند.
            if self._worker is not None:
                self._worker.stop()
            self._thread.quit()
            if not self._thread.wait(5000):
                self._thread.quit()
                self._thread.wait(5000)
        super().closeEvent(e)
