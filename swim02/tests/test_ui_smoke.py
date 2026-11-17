# -*- coding: utf-8 -*-
"""تست دودی رابط کاربری (ساخته‌شدن پنجره‌ها، نوتیف و خروجی PDF).

اگر Qt در دسترس نباشد (مثلاً سرور بدون کتابخانه GL) این فایل رد می‌شود؛
روی کامپیوتر کاربر با `pytest tests/test_ui_smoke.py` واقعاً اجرا می‌شود و
همان‌جا مشخص می‌کند چیدمان نوار عنوان و گزارش PDF سالم است.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:                                   # Qt نیاز به کتابخانه‌های GL سیستم دارد
    from PySide6 import QtWidgets
    _QT_OK, _QT_ERR = True, ""
except Exception as exc:               # noqa: BLE001
    QtWidgets = None                   # type: ignore[assignment]
    _QT_OK, _QT_ERR = False, str(exc)

pytestmark = [
    pytest.mark.skipif(not _QT_OK, reason="Qt در دسترس نیست: %s" % _QT_ERR),
    pytest.mark.usefixtures("qapp"),
]


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_layout(qapp):
    from PySide6.QtCore import Qt

    from app.main_window import MainWindow

    win = MainWindow()
    win.resize(1320, 840)
    win.show()
    qapp.processEvents()

    # نام برنامه سمت چپ، دکمه‌های پنجره سمت راست
    brand = win.findChild(QtWidgets.QLabel, "brand")
    assert brand is not None
    brand_x = brand.mapTo(win, brand.rect().topLeft()).x()
    close_x = win.btn_close.mapTo(win, win.btn_close.rect().topLeft()).x()
    min_x = win.btn_min.mapTo(win, win.btn_min.rect().topLeft()).x()
    assert brand_x < win.width() / 2, "نام برنامه باید سمت چپ باشد"
    assert min_x > win.width() * 0.6, "دکمه کوچک‌کردن باید سمت راست باشد"
    assert close_x > min_x, "دکمه بستن باید راست‌ترین دکمه باشد"

    # متن آیتم‌های داشبورد راست‌چین است
    navs = win.navs
    assert len(navs) == 6
    names = [n.text() for n in navs]
    assert names[0] == "خانه و ویدیو" and names[1] == "اجرای تحلیل"
    assert names[4] == "پرونده شناگر" and names[5] == "پنل مربی"
    for n in navs:
        assert (n.text_lbl.alignment() & Qt.AlignRight) == Qt.AlignRight

    win.close()


def test_every_visible_label_is_right_aligned(qapp):
    """همهٔ متن‌های نرم‌افزار باید راست‌چین باشند (درخواست کاربر)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    from app.main_window import MainWindow

    win = MainWindow()
    win.show()
    qapp.processEvents()
    from app.bidi import strip_marks

    left = []
    for lab in win.findChildren(QLabel):
        text = strip_marks(lab.text()).strip()
        if not text or not lab.isVisible():
            continue
        if lab.property("keepAlign"):
            continue
        a = int(lab.alignment())
        if a & int(Qt.AlignHCenter):
            continue
        if (a & int(Qt.AlignRight)) and (a & int(Qt.AlignAbsolute)):
            continue
        left.append(text[:30])
    assert not left, "این متن‌ها چپ‌چین مانده‌اند: %s" % left
    win.close()


def test_toast_has_no_graphics_effect(qapp):
    """افکت گرافیکی روی پنجرهٔ دارای OpenGL می‌تواند باعث کرش شود."""
    from PySide6.QtWidgets import QWidget

    from app.toast import Toast

    host = QWidget()
    host.resize(400, 300)
    t = Toast(host, "سلام", "info")
    assert t.graphicsEffect() is None
    t.deleteLater()
    host.deleteLater()


def test_about_dialog_builds(qapp):
    from app.about_dialog import AboutDialog

    dlg = AboutDialog(None, first_run=True)
    assert dlg.chk_dont_show.text() == "دیگر نمایش نده"
    assert not dlg.chk_dont_show.isChecked()
    dlg.chk_dont_show.setChecked(True)
    assert dlg.dont_show_again()
    dlg.deleteLater()


def test_toast_manager(qapp):
    from PySide6.QtWidgets import QWidget

    from app.toast import notify

    host = QWidget()
    host.resize(800, 600)
    host.show()
    notify(host, "سلام", "success")
    mgr = getattr(host, "_swim_toasts", None)
    assert mgr is not None and len(mgr.items) == 1
    mgr.clear()
    host.close()


def test_pdf_export_writes_a_file(qapp, tmp_path):
    from app.pdf_report import export_pdf
    from app.swimmer import SwimmerProfile
    from tests.test_pdf_report import make_results

    out = tmp_path / "گزارش.pdf"
    export_pdf(str(out), make_results(),
               SwimmerProfile(name="ستایش محمدی"), color=True)
    assert out.is_file()
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 4000
