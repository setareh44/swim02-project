# -*- coding: utf-8 -*-
"""Engine-level regression tests for swim_ai.py (no MediaPipe / GUI needed)."""
from __future__ import annotations

import json
import os
import re

import numpy as np
import pytest

import swim_ai as S
from synthetic import TRUE_MPP, make_pose, run_pipeline


# ---------------------------------------------------------------------------
# end-to-end pipeline
# ---------------------------------------------------------------------------
def test_pipeline_end_to_end():
    r = run_pipeline(make_pose())

    assert r.style_final == "CRAWL"
    assert S.VIEW_HUD[r.track.dominant] == "SIDE"
    assert 0.0 <= r.style_full.conf <= 1.0
    # the fixture swims one full stroke cycle every 1.30 s
    assert r.strokes.spm_avg == pytest.approx(2 * 60 / 1.30, rel=0.10)
    assert r.perf.mean_speed == pytest.approx(1.50, rel=0.10)
    assert r.perf.distance == pytest.approx(1.50 * r.pose.n / r.pose.fps, rel=0.10)
    # every status code must be a valid GREEN/YELLOW/RED/unknown value
    for arr in r.evalr.status.values():
        assert set(np.unique(arr)) <= {0, 1, 2, 3}
    assert 0.0 <= r.sym.global_pct <= 100.0


def test_calibration_is_close_to_ground_truth():
    r = run_pipeline(make_pose())
    assert r.perf.mpp_median == pytest.approx(TRUE_MPP, rel=0.06)


# ---------------------------------------------------------------------------
# speed: vertical bobbing must not be counted as forward motion
# ---------------------------------------------------------------------------
def test_bobbing_does_not_change_speed():
    flat = run_pipeline(make_pose(bob_m=0.0))
    bobbing = run_pipeline(make_pose(bob_m=0.12))
    assert bobbing.perf.mean_speed == pytest.approx(flat.perf.mean_speed, abs=0.06)


def test_stationary_swimmer_has_almost_no_speed():
    r = run_pipeline(make_pose(speed_mps=0.0, bob_m=0.12))
    assert r.perf.mean_speed < 0.15
    assert r.perf.distance < 0.4


# ---------------------------------------------------------------------------
# stroke rate when only one cycle fits in the clip
# ---------------------------------------------------------------------------
def test_single_cycle_stroke_rate():
    """Only one stroke peak inside the clip: the old code divided by the clip
    duration (60.0 SPM instead of 92.3); the periodicity estimate fixes that."""
    pose = make_pose(n=120)
    r = run_pipeline(pose)
    assert r.strokes.cycles == 1
    assert r.strokes.spm_avg == pytest.approx(2 * 60 / 1.30, rel=0.10)


# ---------------------------------------------------------------------------
# view confidence must never be reported as 0 %
# ---------------------------------------------------------------------------
def test_view_confidence_filled_for_missing_frames():
    pose = make_pose(n=180)
    pose.img[40:75, :, 2] = np.nan          # blot out a third of a second
    pose.img[40:75, :, :2] = np.nan
    pose.img[120, :, 2] = 0.0
    r = run_pipeline(pose)
    assert np.all(np.isfinite(r.track.conf))
    assert np.all(r.track.conf > 0.0)
    assert set(np.unique(r.track.codes)) <= {0, 1, 2, 3}


# ---------------------------------------------------------------------------
# cancellation
# ---------------------------------------------------------------------------
def test_pipeline_honours_cancel():
    pose = make_pose(n=60)
    cfg = S.Config(render=False, cancel=lambda: True)
    with pytest.raises(S.AnalysisCancelled):
        S.SwimAnalysisPipeline(cfg).analyze("synthetic.mp4", pose_raw=pose)


def test_broken_cancel_predicate_is_ignored():
    def boom():
        raise RuntimeError("nope")

    pose = make_pose(n=60)
    r = S.SwimAnalysisPipeline(S.Config(render=False, cancel=boom)).analyze(
        "synthetic.mp4", pose_raw=pose)
    assert r.style_final in {"CRAWL", "BACK", "FLY", "BREAST"}


# ---------------------------------------------------------------------------
# export / report
# ---------------------------------------------------------------------------
def test_json_export(tmp_path):
    r = run_pipeline(make_pose(n=120), pool_length_m=50.0)
    out = tmp_path / "out.json"
    S.JsonExporter().export(r, str(out))
    data = json.loads(out.read_text(encoding="ascii"))

    assert data["summary"]["frames"] == r.pose.n
    assert data["summary"]["style_final"] == r.style_final
    assert data["summary"]["performance"]["pool_length_m"] == 50.0
    assert len(data["frames"]) == r.pose.n
    frame = data["frames"][0]
    for key in ("view", "elbow_angle_deg", "speed_mps", "status_codes",
                "critical_warning"):
        assert key in frame
    # NaN must be encoded as null, never as a bare NaN token
    assert "NaN" not in out.read_text(encoding="ascii")


def test_report_prints_configured_pool_length(capsys):
    r = run_pipeline(make_pose(n=120), pool_length_m=33.0)
    S.ReportPrinter().print(r, None, None)
    out = capsys.readouterr().out
    assert "SWOLF (Takhmini, 33 m)" in out
    # no raw NaN leaking into the terminal report ("etminan" is a word, not a NaN)
    assert not re.search(r"\bnan\b", out.lower())


# ---------------------------------------------------------------------------
# renderer
# ---------------------------------------------------------------------------
def _write_video(path, n=100, size=(320, 240), fps=30.0):
    import cv2
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, size)
    assert writer.isOpened(), "mp4v encoder unavailable"
    for i in range(n):
        frame = np.zeros((size[1], size[0], 3), np.uint8)
        frame[:, :, 1] = int(255 * i / max(n - 1, 1))
        writer.write(frame)
    writer.release()


def test_render_writes_video(tmp_path):
    import cv2
    src = tmp_path / "clip.mp4"
    _write_video(src, n=100)
    pose = make_pose(n=100, fps=30.0)
    r = run_pipeline(pose)
    out = tmp_path / "hud.mp4"
    S.VideoRenderer(S.Config(render=True), r).render(str(src), str(out))

    assert out.exists() and out.stat().st_size > 1000
    cap = cv2.VideoCapture(str(out))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 100
    assert int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 320   # decoded size wins
    cap.release()


def test_render_accepts_unicode_output_path(tmp_path):
    src = tmp_path / "clip.mp4"
    _write_video(src, n=40)
    r = run_pipeline(make_pose(n=40, fps=30.0))
    out = tmp_path / "ویدیوی تحلیل.mp4"
    S.VideoRenderer(S.Config(render=True), r).render(str(src), str(out))
    assert out.exists() and out.stat().st_size > 1000
    assert not list(tmp_path.glob("swim_ai_out_*"))


def test_writer_removes_partial_file_on_failure(tmp_path):
    out = tmp_path / "partial.mp4"
    with pytest.raises(RuntimeError), S.open_writer(str(out), 30.0, (64, 64)) as w:
        w.write(np.zeros((64, 64, 3), np.uint8))
        raise RuntimeError("cancelled")
    assert not out.exists()


def test_writer_unicode_path_moves_result(tmp_path):
    out = tmp_path / "خروجی.mp4"
    with S.open_writer(str(out), 30.0, (64, 64)) as w:
        w.write(np.zeros((64, 64, 3), np.uint8))
    assert out.exists()
    assert not [p for p in os.listdir(tmp_path) if p.startswith("swim_ai_out_")]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def test_smooth_keeps_endpoints_linear():
    x = np.arange(100, dtype=float)
    y = S.SignalTools.smooth(x, 15)
    # edge padding: a linear ramp must stay linear (no pull towards zero)
    assert y[0] == pytest.approx(x[0], abs=1e-6)
    assert y[-1] == pytest.approx(x[-1], abs=1e-6)
    assert np.allclose(y, x)


def test_weighted_quantile_ignores_nan_and_short_segments():
    vals = np.array([[10.0, 5.0], [20.0, np.nan], [30.0, 7.0]])
    weights = np.array([[8.0, 1.0], [1.0, 0.0], [1.0, 9.0]])
    out = S.SpeedEstimator._weighted_quantile(vals, weights, 0.30)
    assert out[0] == pytest.approx(10.0)     # the heavily weighted value wins
    assert out[1] == pytest.approx(7.0)      # NaN entry is ignored
