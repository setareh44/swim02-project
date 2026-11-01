# -*- coding: utf-8 -*-
"""تست ثبت کرش و نشانگر تحلیل + قواعد راست‌چین‌سازی.

این ماژول‌ها بدون Qt هم باید کار کنند، چون دقیقاً پیش از ساخته‌شدن QApplication
اجرا می‌شوند (وقتی برنامه در حال کرش‌کردن است).
"""
from __future__ import annotations

import os

import pytest

from app import diagnostics


@pytest.fixture(autouse=True)
def temp_log_dir(tmp_path, monkeypatch):
    """هر تست در پوشهٔ لاگ خودش کار کند (به فایل‌های واقعی دست نزنیم)."""
    monkeypatch.setenv("SWIM_LOG_DIR", str(tmp_path))
    yield tmp_path
    diagnostics.clear_analysis_marker()


# --------------------------------------------------------------- مسیرها
def test_all_logs_live_in_the_log_dir(temp_log_dir):
    for path in (diagnostics.crash_log_path(), diagnostics.fatal_log_path(),
                 diagnostics.console_log_path(), diagnostics.marker_path(),
                 diagnostics.info_path()):
        assert os.path.dirname(path) == str(temp_log_dir)


def test_log_dir_is_created_if_missing(tmp_path, monkeypatch):
    target = tmp_path / "deep" / "folder"
    monkeypatch.setenv("SWIM_LOG_DIR", str(target))
    assert diagnostics.log_dir() == str(target)
    assert target.is_dir()


# ------------------------------------------------------- نشانگر تحلیل
def test_marker_is_written_and_read(temp_log_dir):
    assert diagnostics.previous_analysis_crash() is None
    diagnostics.mark_analysis("C:/videos/شنا.mp4", "extract")
    data = diagnostics.previous_analysis_crash()
    assert data is not None
    assert data["video"].endswith("شنا.mp4")
    assert data["stage"] == "extract"
    assert data["started"]


def test_marker_stage_updates(temp_log_dir):
    diagnostics.mark_analysis("v.mp4", "extract")
    diagnostics.update_marker_stage("render")
    data = diagnostics.previous_analysis_crash()
    assert data["stage"] == "render"
    assert data["video"] == "v.mp4"


def test_marker_clears(temp_log_dir):
    diagnostics.mark_analysis("v.mp4", "analyze")
    diagnostics.clear_analysis_marker()
    assert diagnostics.previous_analysis_crash() is None
    # پاک‌کردن دوباره نباید خطا بدهد
    diagnostics.clear_analysis_marker()


def test_marker_update_without_marker_is_harmless(temp_log_dir):
    diagnostics.update_marker_stage("render")     # نباید استثنا بدهد
    assert diagnostics.previous_analysis_crash() is None


# ------------------------------------------------------------- faulthandler
def test_faulthandler_creates_fatal_log(temp_log_dir):
    path = diagnostics.install_faulthandler()
    assert path == diagnostics.fatal_log_path()
    assert os.path.isfile(path)
    text = open(path, encoding="utf-8").read()
    assert "SWIM-AI" in text
    # پس از این تست، faulthandler فعال می‌ماند ولی روی فایل پوشهٔ موقت است


def test_thread_excepthook_writes_to_crash_log(temp_log_dir):
    written = []
    diagnostics.install_thread_excepthook(written.append)
    import threading

    def boom():
        raise ValueError("sentinel-error")

    t = threading.Thread(target=boom, name="tester")
    t.start()
    t.join()
    assert written, "hook must report the traceback"
    assert "sentinel-error" in written[0]
    assert "tester" in written[0]
    assert "sentinel-error" in open(diagnostics.crash_log_path(),
                                    encoding="utf-8").read()


# --------------------------------------------------------------- کد خروج
@pytest.mark.parametrize("code,needle", [
    (0, "عادی"),
    (3221225477, "حافظه"),        # 0xC0000005 access violation
    (3221225725, "پشته"),         # 0xC00000FD stack overflow
    (-11, "SIGSEGV"),
    (-6, "SIGABRT"),
    (1, "کد خروج 1"),
])
def test_exit_code_text_explains_crashes(code, needle):
    assert needle in diagnostics.exit_code_text(code)


def test_crash_summary_is_persian_and_actionable(temp_log_dir):
    diagnostics.mark_analysis("v.mp4", "extract")
    data = diagnostics.previous_analysis_crash()
    text = diagnostics.crash_summary(data)
    assert "بسته شد" in text
    assert "استخراج اسکلت" in text          # نام فارسی مرحله
    assert "fatal.log" in text


def test_system_info_reports_versions(temp_log_dir):
    text = diagnostics.system_info()
    assert "python" in text and "platform" in text
    assert "opencv" in text
    assert "numpy" in text


def test_system_info_file_is_written(temp_log_dir):
    path = diagnostics.write_system_info()
    assert os.path.isfile(path)
    assert "executable" in open(path, encoding="utf-8").read()


def test_tail_handles_missing_and_big_files(temp_log_dir):
    assert diagnostics.tail(str(temp_log_dir / "nope.txt")) == ""
    big = temp_log_dir / "big.txt"
    big.write_text("\n".join("line %d" % i for i in range(5000)),
                   encoding="utf-8")
    out = diagnostics.tail(str(big), 5)
    assert out.splitlines()[-1] == "line 4999"
    assert len(out.splitlines()) == 5
