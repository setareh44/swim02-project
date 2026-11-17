# -*- coding: utf-8 -*-
"""OpenGL bridge + crash-hook regression tests (no Qt / GPU required)."""
from __future__ import annotations

import pathlib
import sys

import pytest

from app import gl_render

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# GL constants: PySide6's QOpenGLFunctions exposes the methods but NOT the
# C enum constants, which used to raise AttributeError on every painted frame.
# ---------------------------------------------------------------------------
def test_gl_constants_match_the_standard_headers():
    assert gl_render.GL_COLOR_BUFFER_BIT == 0x4000
    assert gl_render.GL_FLOAT == 0x1406
    assert gl_render.GL_TRIANGLES == 0x0004


class _FakeFunctions:
    """Mimics QOpenGLFunctions: real methods, no GL_* attributes."""

    def __init__(self):
        self.calls = []

    def glViewport(self, x, y, w, h):
        self.calls.append(("viewport", x, y, w, h))

    def glClearColor(self, r, g, b, a):
        self.calls.append(("clearColor", r, g, b, a))

    def glClear(self, mask):
        self.calls.append(("clear", mask))

    def glDrawArrays(self, mode, first, count):
        self.calls.append(("draw", mode, first, count))


class _FakeProgram:
    def __init__(self):
        self.calls = []

    def bind(self):
        self.calls.append("bind")

    def enableAttributeArray(self, loc):
        self.calls.append(("enable", loc))

    def setAttributeBuffer(self, loc, type_, offset, count):
        self.calls.append(("attr", loc, type_, offset, count))

    def setUniformValue1f(self, loc, value):
        self.calls.append(("u1", loc, value))

    def setUniformValue2f(self, loc, x, y):
        self.calls.append(("u2", loc, x, y))

    def disableAttributeArray(self, loc):
        self.calls.append(("disable", loc))

    def release(self):
        self.calls.append("release")


class _FakeVbo:
    def __init__(self):
        self.calls = []

    def bind(self):
        self.calls.append("bind")

    def release(self):
        self.calls.append("release")


def test_paint_uses_numeric_constants_only():
    f, program, vbo = _FakeFunctions(), _FakeProgram(), _FakeVbo()
    gl_render.paint(f, program, vbo, 800, 600, 1.25, u_time=3, u_res=4)

    assert ("clear", 0x4000) in f.calls
    assert ("draw", 0x0004, 0, 3) in f.calls
    assert ("viewport", 0, 0, 800, 600) in f.calls
    assert ("attr", 0, 0x1406, 0, 2) in program.calls
    assert ("u1", 3, 1.25) in program.calls
    assert ("u2", 4, 800.0, 600.0) in program.calls
    # every resource is re-bound / released exactly once per frame
    assert program.calls.count("bind") == 1
    assert program.calls.count("release") == 1
    assert vbo.calls == ["bind", "release"]


def test_paint_propagates_driver_errors():
    class Broken(_FakeFunctions):
        def glClear(self, mask):
            raise RuntimeError("driver reset")

    with pytest.raises(RuntimeError):
        gl_render.paint(Broken(), _FakeProgram(), _FakeVbo(), 10, 10, 0.0)


def test_background_no_longer_reads_gl_constants_from_pyside():
    """رگرسیون: QOpenGLFunctions.GL_* در PySide6 وجود ندارد."""
    source = (ROOT / "app" / "gl_background.py").read_text(encoding="utf-8")
    assert "QOpenGLFunctions.GL_" not in source
    code = "\n".join(line for line in source.splitlines()
                     if not line.strip().startswith("#"))
    assert "QOpenGLFunctions" not in code


# ---------------------------------------------------------------------------
# crash hook: repeated per-frame failures must not flood the log / dialogs
# ---------------------------------------------------------------------------
def test_excepthook_dedupes_repeated_errors(tmp_path, monkeypatch, capsys):
    from app import main as app_main

    log = tmp_path / "crash_log.txt"
    monkeypatch.setattr(app_main, "CRASH_LOG", str(log))
    monkeypatch.setattr(app_main, "_last_signature", None)
    monkeypatch.setattr(app_main, "_repeat_count", 0)
    monkeypatch.setattr(app_main, "_last_error_at", 0.0)
    monkeypatch.setattr(app_main, "_last_box_at", 0.0)

    def boom():
        raise AttributeError("no attribute 'GL_COLOR_BUFFER_BIT'")

    for _ in range(50):
        try:
            boom()
        except AttributeError:
            app_main._excepthook(*sys.exc_info())

    text = log.read_text(encoding="utf-8")
    assert text.count("Setargan-Darya unhandled error") == 1        # only the first one
    out = capsys.readouterr()
    assert "same error repeated" in (out.out + out.err)
    # 49 repeats -> a single "repeated 49 time(s)" summary line, not 49 blocks
    assert "AttributeError" in text


def test_crash_log_is_rolled_over(tmp_path, monkeypatch):
    from app import main as app_main

    log = tmp_path / "crash_log.txt"
    log.write_text("x" * 10, encoding="utf-8")
    monkeypatch.setattr(app_main, "CRASH_LOG", str(log))
    monkeypatch.setattr(app_main, "CRASH_LOG_MAX_BYTES", 5)
    app_main._rotate_crash_log()
    assert (tmp_path / "crash_log.txt.1").exists()
    assert not log.exists() or log.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# skeleton overlay: NaN keypoints must never kill video playback
# ---------------------------------------------------------------------------
def _frame_and_points():
    import numpy as np

    import swim_ai as S
    frame = np.zeros((240, 320, 3), np.uint8)
    pts = np.full((S.NJ, 3), np.nan)
    # a fully valid joint
    pts[S.L_SH] = (100.0, 80.0, 0.95)
    # x valid, y NaN  -> the exact case that raised ValueError in cv2.circle
    pts[S.L_EL] = (130.0, np.nan, 0.95)
    # y valid, x NaN
    pts[S.R_EL] = (np.nan, 120.0, 0.95)
    # both valid but low visibility -> must be skipped
    pts[S.L_WR] = (150.0, 100.0, 0.10)
    # valid but outside the frame -> must be clipped, not crash
    pts[S.R_WR] = (900.0, -50.0, 0.9)
    return frame, pts


def test_overlay_tolerates_nan_coordinates():
    from app import overlay
    import swim_ai as S

    frame, pts = _frame_and_points()
    out = overlay.draw_skeleton(frame, pts, S.BONES, {})
    assert out.shape == frame.shape          # no exception, same frame


def test_overlay_point_validation():
    from app import overlay
    import swim_ai as S

    _, pts = _frame_and_points()
    mask = overlay.valid_mask(pts)
    assert mask[S.L_SH] and mask[S.R_WR]
    assert not mask[S.L_EL] and not mask[S.R_EL]   # one coordinate is NaN
    assert not mask[S.L_WR]                        # visibility too low

    pix = overlay.points(pts, 320, 240)
    assert pix[S.L_EL] is None
    assert pix[S.R_WR] == (319, 0)                 # clipped into the frame


def test_overlay_handles_empty_and_missing_results():
    from app import overlay

    frame, pts = _frame_and_points()
    assert overlay.draw_skeleton(frame, pts[:0], [(0, 1)]) is frame
    # bone indices outside the point array are ignored
    overlay.draw_skeleton(frame, pts, [(0, 99)])


def test_player_guards_drawing_failures(monkeypatch):
    """رگرسیون: خطای رسم باید فقط overlay را خاموش کند، نه پخش را."""
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "video_player.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    handler_ok = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            if "_draw_skeleton" in body:
                handler = ast.dump(ast.Module(body=node.handlers,
                                              type_ignores=[]))
                handler_ok = "_skeleton_broken" in handler
    assert handler_ok, "drawing is not wrapped in a safe try/except"
