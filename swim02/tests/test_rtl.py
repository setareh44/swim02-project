# -*- coding: utf-8 -*-
"""تست قواعد راست‌چین‌سازی.

بخش محاسبهٔ تراز بدون Qt تست می‌شود؛ اگر Qt در دسترس باشد، اصل کار روی
ویجت‌های واقعی هم بررسی می‌شود.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:                                   # این ماژول ذاتاً Qt لازم دارد
    from PySide6 import QtCore, QtWidgets

    from app import rtl as rtl_mod
    _QT_OK = True
except Exception as _exc:              # noqa: BLE001 - سرور بدون GL/EGL
    rtl_mod = None                     # type: ignore[assignment]
    _QT_OK = False
    _QT_ERR = str(_exc)

pytestmark = pytest.mark.skipif(not _QT_OK,
                                reason="Qt در دسترس نیست")


class TestWithQt:
    @pytest.fixture(autouse=True)
    def app(self):
        yield QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_default_left_alignment_becomes_right(self):
        a = rtl_mod.aligned_right(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        assert int(a) & int(QtCore.Qt.AlignRight)
        assert not (int(a) & int(QtCore.Qt.AlignLeft))

    def test_centered_labels_stay_centered(self):
        a = rtl_mod.aligned_right(QtCore.Qt.AlignHCenter
                                  | QtCore.Qt.AlignVCenter)
        assert int(a) & int(QtCore.Qt.AlignHCenter)

    def test_right_alignment_is_absolute(self):
        """رگرسیون کرش «چپ‌چین»: AlignRight بدون AlignAbsolute در ویجت RTL
        به لبهٔ انتهایی (یعنی چپ) ترجمه می‌شود."""
        a = rtl_mod.aligned_right(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        assert int(a) & int(QtCore.Qt.AlignRight)
        assert int(a) & int(QtCore.Qt.AlignAbsolute)

    def test_label_gets_absolute_right_alignment(self):
        lab = QtWidgets.QLabel("خانه و ویدیو")
        lab.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        changed = rtl_mod.fix_widget(lab)
        assert changed
        assert int(lab.alignment()) & int(QtCore.Qt.AlignRight)
        assert int(lab.alignment()) & int(QtCore.Qt.AlignAbsolute)

    def test_layout_direction_is_left_alone(self):
        """جهت چیدمان فقط از QApplication می‌آید (یک منبع حقیقت)."""
        lab = QtWidgets.QLabel("گزارش")
        lab.setLayoutDirection(QtCore.Qt.LeftToRight)
        rtl_mod.fix_widget(lab)
        assert lab.layoutDirection() == QtCore.Qt.LeftToRight

    def test_latin_first_text_gets_rlm(self):
        lab = QtWidgets.QLabel("SWIM-AI برای شناگران")
        rtl_mod.fix_widget(lab)
        assert lab.text().startswith("\u200f")

    def test_latin_only_text_is_not_touched(self):
        lab = QtWidgets.QLabel("SPM 39.7")
        rtl_mod.fix_widget(lab)
        assert lab.text() == "SPM 39.7"

    def test_keep_align_property_is_respected(self):
        lab = QtWidgets.QLabel("SWIM-AI")
        lab.setProperty(rtl_mod.KEEP_ALIGN, True)
        lab.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        rtl_mod.fix_widget(lab)
        assert int(lab.alignment()) & int(QtCore.Qt.AlignLeft)

    def test_keep_direction_property_is_respected(self):
        w = QtWidgets.QWidget()
        w.setLayoutDirection(QtCore.Qt.LeftToRight)
        w.setProperty(rtl_mod.KEEP_DIRECTION, True)
        rtl_mod.fix_widget(w)
        assert w.layoutDirection() == QtCore.Qt.LeftToRight

    def test_tree_walk_sets_every_label(self):
        top = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(top)
        labels = []
        for text in ("خانه", "ویدیو", "گزارش"):
            lab = QtWidgets.QLabel(text)
            lab.setAlignment(QtCore.Qt.AlignLeft)
            labels.append(lab)
            lay.addWidget(lab)
        count = rtl_mod.apply_rtl_tree(top)
        assert count >= 3
        for lab in labels:
            assert int(lab.alignment()) & int(QtCore.Qt.AlignRight)
