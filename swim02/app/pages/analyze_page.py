# -*- coding: utf-8 -*-
"""صفحه تحلیل: پیشرفت شش‌مرحله‌ای، لاگ زنده، پخش نتیجه و شاخص‌های کلیدی."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import icons
from ..labels import STAGES, STYLE_FA
from ..theme import C
from ..video_player import VideoPlayer
from ..widgets import KpiTile, SectionHeader, StageCard, card, fmt_num


class AnalyzePage(QWidget):
    goto_charts = Signal()
    goto_report = Signal()
    retry = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        # ---------------- مراحل ----------------
        scard, sl = card()
        sl.addWidget(SectionHeader("مراحل پردازش", "settings"))
        self.stages = []
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, title in enumerate(STAGES):
            w = StageCard(i, title)
            self.stages.append(w)
            grid.addWidget(w, i // 2, i % 2)
        sl.addLayout(grid)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        sl.addWidget(self.progress)

        row = QHBoxLayout()
        self.lbl_progress = QLabel("آماده برای تحلیل")
        self.lbl_progress.setObjectName("faint")
        self.lbl_progress.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.lbl_progress, 1)
        self.btn_cancel = QPushButton("  توقف تحلیل")
        self.btn_cancel.setObjectName("ghost")
        self.btn_cancel.setIcon(icons.styled_icon("media_stop", C.RED, 16))
        self.btn_cancel.clicked.connect(self._ask_cancel)
        self.btn_cancel.setEnabled(False)
        row.addWidget(self.btn_cancel)
        sl.addLayout(row)
        lay.addWidget(scard)

        # ---------------- لاگ ----------------
        lcard, ll = card()
        ll.addWidget(SectionHeader("گزارش اجرای پایپلاین", "report"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(170)
        self.log.setMaximumBlockCount(2000)
        # خطوط لاگ انگلیسی/عددی هستند؛ باید چپ‌به‌راست بمانند.
        # توجه: QPlainTextEdit اصلاً setAlignment ندارد (فقط QLabel/QTextEdit
        # دارند)؛ برای همین فقط جهت چیدمان کافی است.
        # این تنظیم فقط ظاهری است: اگر روزی خطا داد، نباید پنجره باز نشود.
        try:
            self.log.setLayoutDirection(Qt.LeftToRight)
            self.log.setProperty("keepAlign", True)
            self.log.setProperty("keepDirection", True)
        except Exception:                       # noqa: BLE001
            pass
        ll.addWidget(self.log)
        lay.addWidget(lcard)

        # ---------------- خطا ----------------
        self.err_card, el = card()
        self.err_card.setStyleSheet(
            "QFrame#card { border:1px solid rgba(248,113,113,0.5); }")
        er = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("warning", C.RED, 30))
        er.addWidget(ic)
        self.err_text = QLabel()
        self.err_text.setWordWrap(True)
        self.err_text.setStyleSheet("color:%s; font-weight:700;" % C.RED)
        er.addWidget(self.err_text, 1)
        self.btn_retry = QPushButton("  تلاش دوباره")
        self.btn_retry.setIcon(icons.icon("refresh", C.CYAN, 18))
        self.btn_retry.clicked.connect(self.retry.emit)
        er.addWidget(self.btn_retry)
        el.addLayout(er)
        self.err_card.hide()
        lay.addWidget(self.err_card)

        # ---------------- نتیجه ----------------
        self.res_card, rl = card()
        rl.addWidget(SectionHeader("نتیجه تحلیل و پخش ویدیو", "video"))
        self.player = VideoPlayer()
        rl.addWidget(self.player)

        self.kpi_row = QHBoxLayout()
        self.kpi_row.setSpacing(10)
        rl.addLayout(self.kpi_row)

        nav = QHBoxLayout()
        nav.addStretch(1)
        self.btn_charts = QPushButton("  مشاهده نمودارها")
        self.btn_charts.setIcon(icons.icon("chart", C.CYAN, 18))
        self.btn_charts.clicked.connect(self.goto_charts.emit)
        self.btn_report = QPushButton("  گزارش و پیشنهادها")
        self.btn_report.setObjectName("primary")
        self.btn_report.setIcon(icons.icon("report", "#04202c", 18))
        self.btn_report.clicked.connect(self.goto_report.emit)
        nav.addWidget(self.btn_charts)
        nav.addWidget(self.btn_report)
        rl.addLayout(nav)
        self.res_card.hide()
        lay.addWidget(self.res_card)
        lay.addStretch(1)

    # ------------------------------------------------------------------
    def _ask_cancel(self):
        """دکمه توقف: درخواست لغو و قفل دکمه تا پایان کار."""
        self.btn_cancel.setEnabled(False)
        self.lbl_progress.setText("در حال توقف… (پایان فریم جاری)")
        self.cancel_requested.emit()

    def reset(self):
        self.err_card.hide()
        self.res_card.hide()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.lbl_progress.setText("در حال آغاز پردازش…")
        self.btn_cancel.setEnabled(True)
        self.log.clear()
        for s in self.stages:
            s.set_state("wait")

    def on_stage(self, i: int, text: str):
        if 0 <= i < len(self.stages):
            for j in range(i):
                self.stages[j].set_state("done", "تکمیل شد")
            self.stages[i].set_state("run", text)
            if i == 5:
                self.progress.setRange(0, 0)  # حالت نامعین رندر
                self.lbl_progress.setText("در حال تولید خروجی…")

    def on_progress(self, cur: int, total: int):
        if total <= 0:
            return
        pct = int(100 * cur / total)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self.progress.setValue(pct)
        self.lbl_progress.setText("استخراج اسکلت  ·  %d٪  (%d / %d فریم)"
                                  % (pct, cur, total))

    def append_log(self, line: str):
        self.log.appendPlainText(line)

    def on_failed(self, msg: str):
        for s in self.stages:
            if s.objectName() == "stageRun":
                s.set_state("err", msg[:60])
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.btn_cancel.setEnabled(False)
        self.err_text.setText(msg)
        self.err_card.show()
        self.lbl_progress.setText("تحلیل با خطا متوقف شد.")

    def on_cancelled(self):
        """تحلیل توسط کاربر متوقف شد."""
        for s in self.stages:
            if s.objectName() == "stageRun":
                s.set_state("wait", "متوقف شد")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.btn_cancel.setEnabled(False)
        self.lbl_progress.setText("تحلیل به‌درخواست شما متوقف شد.")

    def on_finished(self, results, out_video: str, out_json: str):
        for s in self.stages:
            s.set_state("done", "تکمیل شد")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.btn_cancel.setEnabled(False)
        self.lbl_progress.setText("تحلیل با موفقیت کامل شد ✓")
        self._build_kpis(results)
        self.player.set_results(results)
        self.player.set_media(results.video_path, out_video)
        self.res_card.show()

    def _build_kpis(self, r):
        while self.kpi_row.count():
            it = self.kpi_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        tiles = [
            KpiTile("سبک شنا", STYLE_FA.get(r.style_final, r.style_final),
                    icon_name="wave", accent=C.CYAN),
            KpiTile("نرخ ضربه", fmt_num(r.strokes.spm_avg, "%.1f"), "SPM",
                    icon_name="gauge", accent=C.BLUE),
            KpiTile("سرعت میانگین", fmt_num(r.perf.mean_speed, "%.2f"), "m/s",
                    icon_name="speed", accent=C.TEAL),
            KpiTile("SWOLF", fmt_num(r.perf.swolf_est, "%.1f"),
                    icon_name="chart", accent=C.VIOLET),
            KpiTile("تقارن", fmt_num(r.sym.global_pct, "%.0f"), "٪",
                    icon_name="body", accent=C.GREEN),
        ]
        for t in tiles:
            self.kpi_row.addWidget(t)

    def shutdown(self):
        self.player.shutdown()
