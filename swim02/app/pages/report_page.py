# -*- coding: utf-8 -*-
"""صفحه گزارش کامل: شاخص‌ها، توزیع وضعیت تکنیک، خطاها و پیشنهادهای هوشمند."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .. import icons, prefs
from ..rtl import apply_rtl_tree
from ..insights import build_insights
from ..jalali import jalali_str
from ..labels import (CRITICAL_KEYS, STATUS_NAME, STYLE_DESC, STYLE_FA,
                      TECH_KEYS, VIEW_FA)
from ..pdf_report import default_filename, export_pdf
from ..swimmer import EVENTS, GENDERS, LEVELS, SwimmerProfile
from ..theme import C
from ..toast import notify
from ..widgets import KpiTile, Pill, QualityBar, SectionHeader, card, fmt_num

_LEVEL = {"red": (C.RED, "warning"), "yellow": (C.YELLOW, "warning"),
          "green": (C.GREEN, "check"), "info": (C.BLUE, "info")}


class _QualityRow(QWidget):
    def __init__(self, key: str, counts: list, total: int):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        name, desc = TECH_KEYS[key]
        box = QVBoxLayout()
        box.setSpacing(1)
        t = QLabel(name)
        t.setStyleSheet("font-weight:700;")
        d = QLabel(desc)
        d.setObjectName("faint")
        d.setStyleSheet("font-size:11px;")
        box.addWidget(t)
        box.addWidget(d)
        lay.addLayout(box, 2)

        self.bar = QualityBar(name, desc, counts)
        lay.addWidget(self.bar, 5)

        pct = [round(100 * c / max(1, total)) for c in counts]
        for value, color in zip(pct[1:], (C.GREEN, C.YELLOW, C.RED)):
            lab = QLabel("%d٪" % value)
            lab.setFixedWidth(46)
            lab.setAlignment(Qt.AlignCenter)
            lab.setStyleSheet("color:%s; font-weight:700;" % color)
            lay.addWidget(lab)


#: اندازهٔ یکسان دکمه‌های PDF/ذخیره (ارتفاع ثابت، حداقل عرض)
_BTN_H = 46
_BTN_W = 210


class ReportPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths = ("", "")
        self._results = None
        self.profile = SwimmerProfile.from_dict(
            prefs.get_json(prefs.KEY_PROFILE, None))
        if not self.profile.date:
            self.profile.date = jalali_str()

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self.scroll)
        self.content = QWidget()
        self.scroll.setWidget(self.content)
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # پروندهٔ شناگر همیشه بالای گزارش است (حتی پیش از تحلیل)
        outer.addWidget(self._build_profile_card())

        # بخش پویا: بعد از هر تحلیل دوباره ساخته می‌شود
        self.dyn = QWidget()
        self.lay = QVBoxLayout(self.dyn)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(16)
        outer.addWidget(self.dyn)
        outer.addStretch(1)

        ph = QLabel("پس از تکمیل تحلیل، گزارش کامل اینجا نمایش داده می‌شود.")
        ph.setObjectName("faint")
        ph.setAlignment(Qt.AlignCenter)
        self.lay.addWidget(ph)

    # ------------------------------------------------------------------
    # پروندهٔ شناگر + خروجی PDF
    # ------------------------------------------------------------------
    def _build_profile_card(self) -> QFrame:
        c, lay = card()
        head = QHBoxLayout()
        head.addWidget(SectionHeader("پروندهٔ شناگر (سرصفحهٔ گزارش)", "body"))
        head.addStretch(1)
        note = QLabel("این اطلاعات در PDF چاپی و گزارش ذخیره می‌شود")
        note.setObjectName("faint")
        head.addWidget(note)
        lay.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.ed_name = QLineEdit(self.profile.name)
        self.ed_name.setPlaceholderText("مثلاً: ستایش محمدی")
        self.ed_date = QLineEdit(self.profile.date or jalali_str())
        self.ed_date.setPlaceholderText("۱۴۰۵/۰۸/۰۷")
        self.ed_birth = QLineEdit(self.profile.birth_year)
        self.ed_birth.setPlaceholderText("۱۳۸۷")
        self.ed_age = QLineEdit(self.profile.age)
        self.ed_age.setPlaceholderText("۱۸")
        self.cmb_gender = _combo(GENDERS, self.profile.gender,
                                 placeholder="انتخاب کنید")
        self.ed_club = QLineEdit(self.profile.club)
        self.ed_club.setPlaceholderText("باشگاه / تیم")
        self.ed_coach = QLineEdit(self.profile.coach)
        self.ed_coach.setPlaceholderText("نام مربی")
        self.cmb_event = _combo(EVENTS, self.profile.event, editable=True,
                                placeholder="رویداد")
        self.cmb_level = _combo(LEVELS, self.profile.level,
                                placeholder="انتخاب کنید")
        self.ed_session = QLineEdit(self.profile.session_no)
        self.ed_pool = QLineEdit(self.profile.pool_length)
        self.ed_height = QLineEdit(self.profile.height)
        self.ed_notes = QLineEdit(self.profile.notes)
        self.ed_notes.setPlaceholderText("هدف جلسه، مصدومیت، نکتهٔ مربی…")

        fields = [
            ("نام و نام خانوادگی", self.ed_name),
            ("تاریخ", self.ed_date),
            ("سال تولد", self.ed_birth),
            ("سن", self.ed_age),
            ("جنسیت", self.cmb_gender),
            ("باشگاه / تیم", self.ed_club),
            ("مربی", self.ed_coach),
            ("رویداد", self.cmb_event),
            ("سطح", self.cmb_level),
            ("شماره جلسه", self.ed_session),
            ("طول استخر (متر)", self.ed_pool),
            ("قد (متر)", self.ed_height),
        ]
        row = col = 0
        for label, widget in fields:
            grid.addWidget(_flabel(label), row, col)
            grid.addWidget(widget, row, col + 1)
            col += 2
            if col >= 6:
                row += 1
                col = 0
        # یادداشت: یک ردیف کامل
        grid.addWidget(_flabel("یادداشت"), row, 0)
        grid.addWidget(self.ed_notes, row, 1, 1, 5)
        for col_idx in (1, 3, 5):
            grid.setColumnStretch(col_idx, 1)
        lay.addLayout(grid)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.btn_pdf_color = QPushButton("  گزارش PDF رنگی (چاپ)")
        self.btn_pdf_color.setObjectName("primary")
        self.btn_pdf_color.setIcon(icons.icon("printer", "#04202c", 18))
        self.btn_pdf_color.setEnabled(False)
        self.btn_pdf_color.clicked.connect(lambda: self._export_pdf(True))

        self.btn_pdf_bw = QPushButton("  گزارش PDF سیاه‌وسفید")
        self.btn_pdf_bw.setIcon(icons.icon("printer", C.TEXT, 18))
        self.btn_pdf_bw.setEnabled(False)
        self.btn_pdf_bw.clicked.connect(lambda: self._export_pdf(False))

        self.btn_save_profile = QPushButton("  ذخیرهٔ پرونده")
        self.btn_save_profile.setObjectName("ghost")
        self.btn_save_profile.setIcon(icons.icon("check", C.TEAL, 18))
        self.btn_save_profile.clicked.connect(self._save_profile_clicked)

        # هر سه دکمه دقیقاً یک اندازه باشند (درخواست کاربر): ارتفاع ثابت و
        # عرض یکسان با ضریب کشش برابر، مستقل از طول متنِ هر دکمه.
        # ظاهری است؛ هر خطایی نباید ساخت صفحه را متوقف کند.
        btns = QHBoxLayout()
        btns.setSpacing(10)
        for btn in (self.btn_pdf_color, self.btn_pdf_bw,
                    self.btn_save_profile):
            try:
                btn.setProperty("rp", "pdf")
                btn.setFixedHeight(_BTN_H)
                btn.setMinimumWidth(_BTN_W)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                btn.setCursor(Qt.PointingHandCursor)
            except Exception:                   # noqa: BLE001
                pass
            btns.addWidget(btn, 1)
        row2.addLayout(btns, 3)
        row2.addSpacing(4)

        hint = QLabel("PDF در اندازهٔ A4 ساخته می‌شود و آمادهٔ چاپ است.")
        hint.setObjectName("faint")
        hint.setWordWrap(True)
        row2.addWidget(hint, 2)
        lay.addLayout(row2)
        return c

    def _collect_profile(self) -> SwimmerProfile:
        self.profile = SwimmerProfile(
            name=self.ed_name.text().strip(),
            date=self.ed_date.text().strip() or jalali_str(),
            birth_year=self.ed_birth.text().strip(),
            age=self.ed_age.text().strip(),
            gender=self.cmb_gender.currentText().strip(),
            club=self.ed_club.text().strip(),
            coach=self.ed_coach.text().strip(),
            event=self.cmb_event.currentText().strip(),
            level=self.cmb_level.currentText().strip(),
            session_no=self.ed_session.text().strip(),
            pool_length=self.ed_pool.text().strip(),
            height=self.ed_height.text().strip(),
            notes=self.ed_notes.text().strip(),
        )
        return self.profile

    def _save_profile_clicked(self):
        self.save_profile()
        notify(self, "پروندهٔ شناگر ذخیره شد و در گزارش‌های بعدی می‌ماند",
               "success")

    def save_profile(self) -> SwimmerProfile:
        prof = self._collect_profile()
        try:
            prefs.set_json(prefs.KEY_PROFILE, prof.to_dict())
        except Exception:
            pass
        return prof

    def _open_file(self, path: str, label: str) -> None:
        if not path or not os.path.exists(path):
            notify(self, "%s پیدا نشد" % label, "warning")
            return
        _open(path)
        notify(self, "%s باز شد" % label, "info", 1800)

    def _export_pdf(self, color: bool):
        if self._results is None:
            notify(self, "اول یک تحلیل را کامل کنید، بعد PDF بگیرید", "warning")
            return
        prof = self.save_profile()
        folder = os.path.dirname(str(self._paths[1] or "")) or os.path.expanduser("~")
        suggested = os.path.join(folder, default_filename(prof, color))
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیرهٔ گزارش PDF", suggested, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            export_pdf(path, self._results, prof, color=color)
        except Exception as exc:            # noqa: BLE001
            notify(self, "ساخت PDF انجام نشد: %s" % exc, "error", 5000)
            return
        notify(self, "گزارش PDF %s ذخیره شد: %s"
               % ("رنگی" if color else "سیاه‌وسفید", os.path.basename(path)),
               "success", 4200)
        _open(path)

    # ------------------------------------------------------------------
    def set_results(self, r, out_video: str, out_json: str):
        self._paths = (out_video, out_json)
        self._results = r
        self.btn_pdf_color.setEnabled(True)
        self.btn_pdf_bw.setEnabled(True)
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        self._header(r)
        self._kpis(r)
        self._quality(r)
        self._critical(r)
        self._insights(r)
        self._exports(out_video, out_json)
        self.lay.addStretch(1)
        # محتوای پویا همین حالا ساخته شد؛ بدون انتظار برای رویداد نمایش،
        # همهٔ متن‌هایش را راست‌چین و راست‌به‌چپ کن.
        try:
            apply_rtl_tree(self.dyn)
        except Exception:                       # noqa: BLE001 - ظاهری است
            pass

    # ------------------------------------------------------------------
    def _header(self, r):
        c, lay = card()
        top = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(6)
        prof = self._collect_profile()
        who = prof.name.strip()
        title = QLabel("گزارش تحلیل: %s" % (who or os.path.basename(r.video_path)))
        title.setObjectName("h2")
        title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        col.addWidget(title)
        meta = QLabel(
            "%s  ·  %s  ·  مدت %.1f ثانیه  ·  %d فریم  ·  دقت تشخیص %.0f٪"
            % (STYLE_DESC.get(r.style_final, r.style_final),
               VIEW_FA.get(_view_name(r), _view_name(r)),
               r.pose.n / r.pose.fps, r.pose.n,
               100 * r.pose_raw.detect_ratio))
        meta.setObjectName("muted")
        col.addWidget(meta)
        top.addLayout(col, 1)
        top.addWidget(Pill("سبک: %s" % STYLE_FA.get(r.style_final, r.style_final),
                           C.CYAN))
        top.addWidget(Pill("اطمینان: %.0f٪" % (100 * r.style_full.conf), C.TEAL))
        if prof.date:
            top.addWidget(Pill("تاریخ: %s" % prof.date, C.BLUE))
        lay.addLayout(top)
        self.lay.addWidget(c)

    def _kpis(self, r):
        c, lay = card()
        lay.addWidget(SectionHeader("شاخص‌های کلیدی عملکرد", "gauge"))
        grid = QGridLayout()
        grid.setSpacing(10)
        crit = sum(r.evalr.events.values())
        tiles = [
            KpiTile("تعداد کل ضربه‌ها", str(r.strokes.total_strokes),
                    icon_name="wave", accent=C.CYAN),
            KpiTile("نرخ ضربه میانگین", fmt_num(r.strokes.spm_avg, "%.1f"), "SPM",
                    icon_name="gauge", accent=C.BLUE),
            KpiTile("سرعت میانگین", fmt_num(r.perf.mean_speed, "%.2f"), "m/s",
                    icon_name="speed", accent=C.TEAL),
            KpiTile("بیشینه سرعت", fmt_num(r.perf.max_speed, "%.2f"), "m/s",
                    icon_name="speed", accent=C.GREEN),
            KpiTile("مسافت تخمینی", fmt_num(r.perf.distance, "%.1f"), "متر",
                    icon_name="wave", accent=C.VIOLET),
            KpiTile("طول ضربه", fmt_num(r.perf.sl_mean, "%.2f"), "متر/ضربه",
                    icon_name="body", accent=C.INDIGO),
            KpiTile("شاخص کارایی", fmt_num(r.perf.eff_mean, "%.2f"),
                    icon_name="chart", accent=C.TEAL),
            KpiTile("SWOLF تخمینی", fmt_num(r.perf.swolf_est, "%.1f"),
                    icon_name="chart", accent=C.ORANGE),
            KpiTile("تقارن دو دست", fmt_num(r.sym.global_pct, "%.0f"), "٪",
                    icon_name="body", accent=C.GREEN),
            KpiTile("رویداد بحرانی", str(crit),
                    icon_name="warning",
                    accent=C.RED if crit else C.GREEN),
        ]
        for i, t in enumerate(tiles):
            grid.addWidget(t, i // 5, i % 5)
        lay.addLayout(grid)
        self.lay.addWidget(c)

    def _quality(self, r):
        c, lay = card()
        head = QHBoxLayout()
        head.addWidget(SectionHeader("وضعیت شاخص‌های تکنیکی در طول ویدیو", "body"))
        head.addStretch(1)
        for name, color in ((STATUS_NAME[1], C.GREEN), (STATUS_NAME[2], C.YELLOW),
                            (STATUS_NAME[3], C.RED)):
            lab = QLabel("● " + name)
            lab.setStyleSheet("color:%s; font-weight:700;" % color)
            head.addWidget(lab)
        lay.addLayout(head)

        for key in TECH_KEYS:
            arr = r.evalr.status[key]
            counts = [int(np.sum(arr == k)) for k in range(4)]
            lay.addWidget(_QualityRow(key, counts, len(arr)))
        self.lay.addWidget(c)

    def _critical(self, r):
        c, lay = card()
        lay.addWidget(SectionHeader("رخدادهای بحرانی", "warning"))
        grid = QGridLayout()
        for i, key in enumerate(CRITICAL_KEYS):
            name = TECH_KEYS[key][0]
            cnt = r.evalr.events.get(key, 0)
            frames = r.evalr.red_frames.get(key, 0)
            color = C.RED if cnt else C.GREEN
            box = QFrame()
            box.setObjectName("kpi")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(12, 10, 12, 10)
            v = QLabel(str(cnt))
            v.setStyleSheet("font-size:26px; font-weight:800; color:%s;" % color)
            t = QLabel(name)
            t.setObjectName("muted")
            t.setWordWrap(True)
            f = QLabel("%d فریم قرمز" % frames)
            f.setObjectName("faint")
            f.setStyleSheet("font-size:11px;")
            bl.addWidget(v)
            bl.addWidget(t)
            bl.addWidget(f)
            grid.addWidget(box, 0, i)
        lay.addLayout(grid)
        self.lay.addWidget(c)

    def _insights(self, r):
        c, lay = card()
        lay.addWidget(SectionHeader("پیشنهادهای هوشمند اصلاح تکنیک", "info"))
        for item in build_insights(r):
            color, icn = _LEVEL[item["level"]]
            box = QFrame()
            box.setStyleSheet(
                "QFrame{background:rgba(255,255,255,0.03);"
                "border-right:4px solid %s; border-radius:12px;}" % color)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(14, 12, 14, 12)
            bl.setSpacing(6)
            head = QHBoxLayout()
            ic = QLabel()
            ic.setPixmap(icons.pixmap(icn, color, 20))
            head.addWidget(ic)
            t = QLabel(item["title"])
            t.setStyleSheet("font-weight:800; font-size:14px; color:%s;" % color)
            head.addWidget(t)
            head.addStretch(1)
            bl.addLayout(head)
            txt = QLabel(item["text"])
            txt.setObjectName("muted")
            txt.setWordWrap(True)
            bl.addWidget(txt)
            if item.get("drill"):
                d = QLabel("تمرین پیشنهادی: " + item["drill"])
                d.setWordWrap(True)
                d.setStyleSheet("color:%s; font-weight:600;" % C.TEAL)
                bl.addWidget(d)
            lay.addWidget(box)
        self.lay.addWidget(c)

    def _exports(self, out_video, out_json):
        c, lay = card()
        lay.addWidget(SectionHeader("خروجی‌ها", "export"))
        row = QHBoxLayout()
        b1 = QPushButton("  باز کردن فایل JSON")
        b1.setIcon(icons.icon("report", C.CYAN, 18))
        b1.clicked.connect(lambda: self._open_file(out_json, "فایل JSON"))
        row.addWidget(b1)
        if out_video:
            b2 = QPushButton("  باز کردن ویدیوی تحلیل‌شده")
            b2.setIcon(icons.icon("video", C.CYAN, 18))
            b2.clicked.connect(lambda: self._open_file(out_video,
                                                       "ویدیوی تحلیل‌شده"))
            row.addWidget(b2)
            b3 = QPushButton("  پوشه خروجی")
            b3.setObjectName("ghost")
            b3.setIcon(icons.icon("folder", C.MUTED, 18))
            b3.clicked.connect(lambda: self._open_file(
                os.path.dirname(out_video), "پوشهٔ خروجی"))
            row.addWidget(b3)
        row.addStretch(1)
        lay.addLayout(row)
        self.lay.addWidget(c)


def _view_name(r) -> str:
    from swim_ai import VIEW_HUD
    return VIEW_HUD[r.track.dominant]


def _open(path: str):
    if path and os.path.exists(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def _flabel(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return lab


def _combo(items, current: str = "", editable: bool = False,
           placeholder: str = "") -> QComboBox:
    """کمبوی فارسی؛ گزینهٔ خالی با placeholder نشان داده می‌شود."""
    box = QComboBox()
    box.setEditable(editable)
    box.addItems([i for i in items if i])
    if placeholder and not editable:
        box.setPlaceholderText(placeholder)
        box.setCurrentIndex(-1)
    if current:
        idx = box.findText(current)
        if idx >= 0:
            box.setCurrentIndex(idx)
        elif editable:
            box.setCurrentText(current)
    return box
