# -*- coding: utf-8 -*-
"""صفحه نخست: معرفی، انتخاب ویدیو با کشیدن‌ورها کردن، و تنظیمات تحلیل."""
from __future__ import annotations

import os

import cv2
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from swim_ai import open_video_reader

from .. import icons
from ..theme import C
from ..toast import notify
from ..widgets import SectionHeader, card

VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".wmv")


class DropZone(QLabel):
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(230)
        self.setAlignment(Qt.AlignCenter)
        self.setProperty("active", False)
        self._render_idle()

    def _render_idle(self):
        self.setText("")
        # محتوای چند‌خطی با یک ویجت داخلی
        if self.layout() is None:
            lay = QVBoxLayout(self)
            lay.setAlignment(Qt.AlignCenter)
            lay.setSpacing(10)
            ic = QLabel()
            ic.setAlignment(Qt.AlignCenter)
            ic.setPixmap(icons.pixmap("folder", C.CYAN, 46))
            t1 = QLabel("ویدیوی شنا را اینجا رها کنید")
            t1.setAlignment(Qt.AlignCenter)
            t1.setStyleSheet("font-size:16px; font-weight:700; color:%s;" % C.TEXT)
            t2 = QLabel("یا از دکمه زیر انتخاب کنید  ·  MP4 / MOV / AVI / MKV")
            t2.setAlignment(Qt.AlignCenter)
            t2.setObjectName("faint")
            lay.addWidget(ic)
            lay.addWidget(t1)
            lay.addWidget(t2)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setProperty("active", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, e):
        self.setProperty("active", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, e):
        self.setProperty("active", False)
        self.style().unpolish(self)
        self.style().polish(self)
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(VIDEO_EXTS):
                self.file_dropped.emit(path)
                break


class _SpinRow(QWidget):
    def __init__(self, label: str, spin: QWidget, suffix: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        t = QLabel(label)
        t.setObjectName("muted")
        t.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(t)
        lay.addStretch(1)
        if suffix:
            sp = QLabel(suffix)
            sp.setObjectName("faint")
            lay.addWidget(sp)
        lay.addWidget(spin)


class HomePage(QWidget):
    video_selected = Signal(str)
    start_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path = ""
        self._thumb_pix = None
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(18)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        blay = QVBoxLayout(body)
        blay.setContentsMargins(0, 0, 0, 0)
        blay.setSpacing(18)

        # ---------------- هیرو ----------------
        hero = QWidget()
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        title = QLabel("تحلیل هوشمند بیومکانیک شنا")
        title.setObjectName("h1")
        title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sub = QLabel("از یک ویدیوی ساده گوشی تا گزارش سطح آزمایشگاهی — تشخیص سبک، "
                     "خطای تکنیک، سرعت، SWOLF و نمودارهای تعاملی")
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hl.addWidget(title)
        hl.addWidget(sub)
        badges = QHBoxLayout()
        badges.setSpacing(8)
        for txt in ("MediaPipe Pose", "نمای چندزاویه‌ای", "۴ سبک شنا",
                    "OpenGL + نمودار تعاملی"):
            b = QLabel(txt)
            b.setObjectName("badge")
            badges.addWidget(b)
        badges.addStretch(1)
        hl.addLayout(badges)
        blay.addWidget(hero)

        grid = QGridLayout()
        grid.setSpacing(18)

        # ---------------- کارت انتخاب ویدیو ----------------
        vcard, vl = card()
        vl.addWidget(SectionHeader("انتخاب ویدیو", "video"))
        self.zone = DropZone()
        self.zone.file_dropped.connect(self.set_video)
        vl.addWidget(self.zone)

        row = QHBoxLayout()
        self.btn_pick = QPushButton("  انتخاب فایل ویدیو")
        self.btn_pick.setIcon(icons.icon("folder", C.CYAN, 18))
        self.btn_pick.clicked.connect(self._pick)
        row.addWidget(self.btn_pick)
        row.addStretch(1)
        vl.addLayout(row)

        self.thumb = QLabel()
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedHeight(150)
        self.thumb.setStyleSheet(
            "background:#02080f; border:1px solid %s; border-radius:12px;" % C.BORDER)
        self.thumb.hide()
        vl.addWidget(self.thumb)

        self.lbl_file = QLabel("هنوز ویدیویی انتخاب نشده است.")
        self.lbl_file.setObjectName("muted")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        vl.addWidget(self.lbl_file)
        self.lbl_meta = QLabel("")
        self.lbl_meta.setObjectName("faint")
        self.lbl_meta.setWordWrap(True)
        self.lbl_meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        vl.addWidget(self.lbl_meta)
        grid.addWidget(vcard, 0, 1)

        # ---------------- کارت تنظیمات ----------------
        scard, sl = card()
        sl.addWidget(SectionHeader("تنظیمات تحلیل", "settings"))

        self.sp_height = QDoubleSpinBox()
        self.sp_height.setRange(1.0, 2.3)
        self.sp_height.setSingleStep(0.01)
        self.sp_height.setValue(1.75)
        self.sp_height.setDecimals(2)
        sl.addWidget(_SpinRow("قد شناگر (کالیبراسیون)", self.sp_height, "متر"))

        self.sp_pool = QDoubleSpinBox()
        self.sp_pool.setRange(5.0, 200.0)
        self.sp_pool.setValue(25.0)
        sl.addWidget(_SpinRow("طول استخر", self.sp_pool, "متر"))

        self.cmb_view = QComboBox()
        self.cmb_view.addItems(["auto", "side", "front", "overhead", "oblique"])
        sl.addWidget(_SpinRow("زاویه دوربین", self.cmb_view))

        self.sp_fov = QDoubleSpinBox()
        self.sp_fov.setRange(30.0, 120.0)
        self.sp_fov.setValue(65.0)
        sl.addWidget(_SpinRow("زاویه دید دوربین", self.sp_fov, "درجه"))

        self.cmb_model = QComboBox()
        self.cmb_model.addItems(["0 — سبک (سریع)", "1 — کامل (پیش‌فرض)",
                                 "2 — سنگین (دقیق)"])
        self.cmb_model.setCurrentIndex(1)
        sl.addWidget(_SpinRow("پیچیدگی مدل Pose", self.cmb_model))

        self.chk_render = QCheckBox("ساخت ویدیوی خروجی با داشبورد HUD")
        self.chk_render.setChecked(True)
        sl.addWidget(self.chk_render)

        tip = QLabel("توصیه: دوربین ثابت، در ارتفاع لگن و از نمای پهلو، با نور "
                     "یکنواخت بهترین نتیجه را می‌دهد.")
        tip.setObjectName("faint")
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.addWidget(tip)
        sl.addStretch(1)
        grid.addWidget(scard, 0, 0)
        blay.addLayout(grid)

        # ---------------- دکمه شروع ----------------
        cta = QHBoxLayout()
        cta.addStretch(1)
        self.btn_start = QPushButton("  شروع تحلیل هوشمند")
        self.btn_start.setObjectName("primary")
        self.btn_start.setIcon(icons.icon("wave", "#04202c", 22))
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._start)
        cta.addWidget(self.btn_start)
        cta.addStretch(1)
        blay.addLayout(cta)
        blay.addStretch(1)

    # ------------------------------------------------------------------
    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب ویدیوی شنا", os.path.expanduser("~"),
            "ویدیوها (%s)" % " ".join("*" + e for e in VIDEO_EXTS))
        if path:
            self.set_video(path)

    def set_video(self, path: str):
        if not os.path.isfile(path):
            return
        self.video_path = path
        self.video_selected.emit(path)
        self.lbl_file.setText("فایل انتخاب‌شده: " + os.path.basename(path))
        notify(self, "ویدیو انتخاب شد: %s" % os.path.basename(path), "success")
        self.btn_start.setEnabled(True)
        self._thumb_pix = None
        try:
            cap, cleanup = open_video_reader(path)
        except IOError:
            self.lbl_meta.setText("این فایل به‌عنوان ویدیو قابل خواندن نیست.")
            return
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            ok, frame = cap.read()
        finally:
            cleanup()
        if ok and frame is not None:
            from PySide6.QtGui import QImage
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h2, w2 = rgb.shape[:2]
            img = QImage(rgb.data, w2, h2, 3 * w2, QImage.Format_RGB888).copy()
            self._thumb_pix = QPixmap.fromImage(img)
            self._show_thumb()
        else:
            self.thumb.hide()
        dur = n / fps if fps else 0
        self.lbl_meta.setText(
            "مدت: %02d:%02d  ·  %d فریم  ·  %d×%d  ·  %.0f FPS"
            % (dur // 60, dur % 60, n, w, h, fps))

    def _show_thumb(self):
        """نمایش بندانگشتی با اندازه فعلی ویجت (پیش از چیده‌شدن، عرض صفر است)."""
        if self._thumb_pix is None or self._thumb_pix.isNull():
            return
        width = self.thumb.width()
        if width < 120:                      # هنوز چیده نشده: عرض تقریبی کارت
            width = 520
        self.thumb.setPixmap(self._thumb_pix.scaled(
            width, max(120, self.thumb.height()), Qt.KeepAspectRatio,
            Qt.SmoothTransformation))
        self.thumb.show()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._show_thumb()

    def _start(self):
        if not self.video_path:
            return
        self.start_requested.emit(self.settings())

    def settings(self) -> dict:
        return {
            "height": self.sp_height.value(),
            "pool_length": self.sp_pool.value(),
            "view": self.cmb_view.currentText(),
            "fov": self.sp_fov.value(),
            "model_complexity": self.cmb_model.currentIndex(),
            "render": self.chk_render.isChecked(),
        }
