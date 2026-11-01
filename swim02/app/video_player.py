# -*- coding: utf-8 -*-
"""پخش‌کننده ویدیو با OpenCV + کنترل‌های کامل و قابلیت ترسیم اسکلت تحلیل‌شده."""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QSlider,
                               QVBoxLayout)

from swim_ai import (BONES, L_EL, L_HIP, L_KN, L_SH, L_WR, NOSE,
                     R_EL, R_HIP, R_KN, R_SH, R_WR, open_video_reader)

from . import icons
from .overlay import draw_skeleton
from .theme import C

_BGR = {1: (0, 200, 120), 2: (0, 190, 255), 3: (60, 70, 250), 0: (220, 200, 40)}

#: اندازهٔ دکمه‌های پخش و توقف (قطر گویِ آماده، پیکسل)
_PLAY_SIZE = 56
_STOP_SIZE = 44


def _qimage(frame_bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class VideoPlayer(QFrame):
    frame_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._cap = None
        self._cap_cleanup = lambda: None
        self._frame = None          # آخرین فریم خوانده‌شده (برای تغییر اندازه)
        self._frame_idx_shown = -1
        self._seeking = False
        self._path = ""
        self._total = 0
        self._fps = 30.0
        self._idx = 0
        self._speed = 1.0
        self._results = None
        self._show_skeleton = False
        self._skeleton_broken = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self.screen = QLabel()
        self.screen.setAlignment(Qt.AlignCenter)
        self.screen.setMinimumHeight(380)
        self.screen.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.screen.setStyleSheet(
            "background:#02080f; border:1px solid %s; border-radius:12px;" % C.BORDER)
        self._placeholder()
        lay.addWidget(self.screen, 1)

        # ---------- ردیف کنترل ----------
        bar = QHBoxLayout()
        bar.setSpacing(10)
        # کنترل‌های پخش، مثل پخش‌کننده‌های استاندارد: دکمهٔ اصلیِ روشن و گِرد
        # با نماد تیره (بیشترین کنتراست) و کنارش یک دکمهٔ فرعیِ آرام.
        # گویِ براقِ آماده (رینگ فلزی + شیشهٔ بنفش) — تصویر، نه استایل سادهٔ Qt
        self.btn_play = QPushButton()
        self.btn_play.setObjectName("playBtn")
        self.btn_play.setFixedSize(_PLAY_SIZE, _PLAY_SIZE)
        self.btn_play.setIconSize(QSize(_PLAY_SIZE, _PLAY_SIZE))
        self._set_play_icon("play")
        self.btn_play.setToolTip("پخش / توقف (Space)")
        self.btn_play.setCursor(Qt.PointingHandCursor)
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.toggle)
        bar.addWidget(self.btn_play, 0, Qt.AlignVCenter)

        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setFixedSize(_STOP_SIZE, _STOP_SIZE)
        self.btn_stop.setIconSize(QSize(_STOP_SIZE, _STOP_SIZE))
        self.btn_stop.setIcon(icons.media_icon("stop"))
        self.btn_stop.setToolTip("توقف و بازگشت به ابتدای ویدیو")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        bar.addWidget(self.btn_stop, 0, Qt.AlignVCenter)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        # valueChanged (نه sliderMoved) تا کلیک روی شیار و کلیدهای جهت هم Seek کنند
        self.slider.valueChanged.connect(self._slider_moved)
        bar.addWidget(self.slider, 1)

        self.lbl_time = QLabel("۰۰:۰۰ / ۰۰:۰۰")
        self.lbl_time.setObjectName("muted")
        self.lbl_time.setMinimumWidth(112)
        self.lbl_time.setAlignment(Qt.AlignCenter)
        self.lbl_time.setStyleSheet(
            "font-family:'Consolas','DejaVu Sans Mono',monospace;"
            "font-size:12px; letter-spacing:0.5px;")
        bar.addWidget(self.lbl_time)

        self.cmb_speed = QComboBox()
        self.cmb_speed.addItems(["۰.۵×", "۱×", "۱.۵×", "۲×"])
        self.cmb_speed.setCurrentIndex(1)
        self.cmb_speed.currentIndexChanged.connect(self._speed_changed)
        bar.addWidget(self.cmb_speed)

        self.chk_skel = QCheckBox("اسکلت")
        self.chk_skel.setEnabled(False)
        self.chk_skel.toggled.connect(self._skeleton_toggled)
        bar.addWidget(self.chk_skel)

        self.cmb_source = QComboBox()
        self.cmb_source.addItem("ویدیوی اصلی", "orig")
        self.cmb_source.addItem("ویدیوی تحلیل‌شده (HUD)", "hud")
        self.cmb_source.model().item(1).setEnabled(False)
        self.cmb_source.currentIndexChanged.connect(self._source_changed)
        bar.addWidget(self.cmb_source)
        lay.addLayout(bar)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._hud_path = ""

    # ------------------------------------------------------------------
    def _placeholder(self):
        pm = icons.pixmap("video", C.FAINT, 64)
        self.screen.setPixmap(pm)

    def _set_play_icon(self, name: str) -> None:
        """گویِ پخش یا مکث را بگذار (هر سه حالت: عادی/هوور/غیرفعال)."""
        self.btn_play.setIcon(icons.media_icon(name))

    def set_media(self, path: str, hud_path: str = "") -> None:
        self._path = path
        self._hud_path = hud_path
        self.cmb_source.model().item(1).setEnabled(bool(hud_path))
        self.cmb_source.setCurrentIndex(0)
        self._open(path)

    def set_results(self, results) -> None:
        self._results = results
        self.chk_skel.setEnabled(results is not None)

    def _release(self) -> None:
        self._timer.stop()
        if self._cap is not None:
            try:
                self._cap_cleanup()
            finally:
                self._cap = None
                self._cap_cleanup = lambda: None
        self._frame = None
        self._frame_idx_shown = -1

    def _open(self, path: str, start: int = 0) -> None:
        self._release()
        try:
            cap, cleanup = open_video_reader(path)
        except IOError:
            self._cap = None
            self._frame = None
            self.btn_play.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.slider.setEnabled(False)
            return
        self._cap, self._cap_cleanup = cap, cleanup
        self._total = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._fps = fps if fps and fps > 0 else 30.0
        self._idx = 0
        self.slider.blockSignals(True)      # جلوگیری از Seek خودکار در میانه بازکردن
        self.slider.setRange(0, self._total - 1)
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.slider.setEnabled(True)
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self._set_play_icon("play")
        self._show_frame(0 if start <= 0 else start)

    # ------------------------------------------------------------------
    def toggle(self):
        if self._cap is None:
            return
        if self._timer.isActive():
            self.pause()
        else:
            self.play()

    def play(self):
        if self._cap is None:
            return
        if self._idx >= self._total - 1:
            self._seek(0)
        self._timer.start(max(8, int(1000 / (self._fps * self._speed))))
        self._set_play_icon("pause")

    def pause(self):
        self._timer.stop()
        self._set_play_icon("play")

    def stop(self):
        self.pause()
        self._seek(0)

    def _seek(self, frame: int):
        if self._cap is None:
            return
        self._idx = max(0, min(frame, self._total - 1))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._idx)
        self._show_frame(self._idx)

    def _speed_changed(self, i: int):
        self._speed = (0.5, 1.0, 1.5, 2.0)[i]
        if self._timer.isActive():
            self._timer.setInterval(
                max(8, int(1000 / (self._fps * self._speed))))

    def _skeleton_toggled(self, on: bool):
        if on and self._skeleton_broken:
            self._skeleton_broken = False       # کاربر دوباره امتحان می‌کند
        self._show_skeleton = on
        # فقط بازترسیم فریم فعلی؛ خواندن دوباره باعث پرش یک‌فریمی می‌شد
        self._render_current()

    def _source_changed(self, _i: int):
        data = self.cmb_source.currentData()
        hud = data == "hud" and bool(self._hud_path)
        path = self._hud_path if hud else self._path
        # روی ویدیوی HUD اسکلت از قبل رندر شده؛ ترسیم دوباره لازم نیست
        self.chk_skel.setEnabled((not hud) and self._results is not None)
        if self._cap is None:
            return
        self.pause()
        self._open(path)
        self.play()

    def _slider_moved(self, value: int):
        """کلیک/درگ روی نوار زمان -> Seek به همان فریم."""
        if self._seeking or self._cap is None:
            return
        self.pause()
        self._seek(value)

    # ------------------------------------------------------------------
    def _tick(self):
        if self._cap is None:
            return
        self._idx += 1
        if self._idx >= self._total:
            self.pause()
            self._idx = self._total - 1
            return
        self._show_frame(self._idx)

    def _show_frame(self, i: int):
        """خواندن فریم i از ویدیو و نمایش آن."""
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok:
            self.pause()
            return
        self._frame = frame
        self._frame_idx_shown = i
        self._render_current()
        self.frame_changed.emit(i)

    def _render_current(self):
        """نمایش فریم کش‌شده در اندازه فعلی صفحه (بدون خواندن دوباره ویدیو)."""
        if self._frame is None:
            return
        frame = self._frame
        hud_source = self.cmb_source.currentData() == "hud"
        if self._show_skeleton and self._results is not None and not hud_source:
            try:
                frame = self._draw_skeleton(frame.copy(), self._frame_idx_shown)
            except Exception as exc:  # noqa: BLE001
                # رسم اسکلت هرگز نباید پخش ویدیو را متوقف کند؛ یک بار خاموش می‌شود
                self._skeleton_broken = True
                self._show_skeleton = False
                self.chk_skel.blockSignals(True)
                self.chk_skel.setChecked(False)
                self.chk_skel.blockSignals(False)
                print("[SWIM-AI] skeleton overlay disabled: %r" % (exc,))
                frame = self._frame
        pm = QPixmap.fromImage(_qimage(frame))
        size = self.screen.size()
        if size.width() > 10 and size.height() > 10:
            pm = pm.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.screen.setPixmap(pm)
        self._seeking = True
        self.slider.blockSignals(True)
        self.slider.setValue(self._frame_idx_shown)
        self.slider.blockSignals(False)
        self._seeking = False
        self.lbl_time.setText(self._fmt(self._frame_idx_shown) + " / "
                              + self._fmt(max(0, self._total - 1)))

    def _draw_skeleton(self, frame: np.ndarray, i: int) -> np.ndarray:
        """ترسیم اسکلت؛ هندسه و اعتبارسنجی NaN در ``app.overlay`` انجام می‌شود."""
        r = self._results
        if r is None or i < 0 or i >= r.pose.n:
            return frame
        pts = r.pose.img[i]                      # (NJ, 3) x, y, visibility
        st = r.evalr.status

        def code(key: str) -> int:
            arr = st.get(key)
            if arr is None or i >= len(arr):
                return 0
            return int(arr[i])

        status = {
            L_EL: code("elbow_L"), R_EL: code("elbow_R"),
            L_KN: code("knee_L"), R_KN: code("knee_R"),
            L_HIP: code("torso"), R_HIP: code("torso"),
            L_WR: code("sym"), R_WR: code("sym"),
        }
        return draw_skeleton(frame, pts, BONES, status, colors=_BGR,
                             highlights=(NOSE, L_SH, R_SH))

    def _fmt(self, frame: int) -> str:
        sec = frame / max(self._fps, 1e-6)
        return "%02d:%02d" % (sec // 60, sec % 60)

    def resizeEvent(self, e):
        # تغییر اندازه نباید ویدیو را جلو ببرد: فقط فریم کش‌شده بازترسیم می‌شود
        self._render_current()
        super().resizeEvent(e)

    def shutdown(self):
        self._release()
