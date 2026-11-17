# -*- coding: utf-8 -*-
"""Phase recognition + confidence engine tests (no MediaPipe / GUI)."""
from __future__ import annotations

import json

import numpy as np
import pytest

import swim_ai as S
from synthetic import make_pose, run_pipeline


def test_phases_cover_full_cycle():
    r = run_pipeline(make_pose())
    for arm in "LR":
        codes = r.phases.codes[arm]
        assert codes.shape == (r.pose.n,)
        assert codes.dtype == np.int8
        assert set(np.unique(codes)) <= {0, 1, 2, 3, 4, 5}
        # a 4 s crawl clip must show every phase of the cycle
        assert set(np.unique(codes)) >= {1, 2, 3, 4, 5}
    total = sum(r.phases.dist.values())
    assert total == pytest.approx(1.0, abs=0.02)
    assert set(r.phases.dist) == {"ENTRY", "CATCH", "PULL", "PUSH", "RECOVERY"}


def test_phases_unknown_without_cycles():
    r = run_pipeline(make_pose(n=30))     # too short for a full cycle
    for arm in "LR":
        assert set(np.unique(r.phases.codes[arm])) <= {0, 1, 2, 3, 4, 5}


def test_confidence_high_on_clean_clip():
    r = run_pipeline(make_pose())
    c = r.confr
    assert c.conf.shape == (r.pose.n,)
    assert np.all(c.conf >= 0.0) and np.all(c.conf <= 1.0)
    assert c.mean_conf > 0.8
    assert c.low_ratio == pytest.approx(0.0, abs=0.05)
    assert c.high_ratio > 0.8
    assert np.all(c.meas_err_deg >= 2.0) and np.all(c.meas_err_deg <= 30.0)


def test_confidence_drops_on_missed_frames():
    pose = make_pose(n=120)
    pose.img[10:20, :, :] = np.nan        # simulate splash / occlusion burst
    pose.wld[10:20, :, :] = np.nan
    r = run_pipeline(pose)
    assert r.confr.conf[10:20].mean() < r.confr.conf[40:60].mean()
    assert r.confr.meas_err_deg[15] > r.confr.meas_err_deg[50]


def test_json_and_report_include_phases_confidence(tmp_path, capsys):
    r = run_pipeline(make_pose(n=120))
    out = tmp_path / "ph.json"
    S.JsonExporter().export(r, str(out))
    data = json.loads(out.read_text(encoding="ascii"))
    frame0 = data["frames"][0]
    assert frame0["stroke_phase"]["left"] in S.PHASE_HUD.values()
    assert 0.0 <= frame0["confidence"] <= 1.0
    assert frame0["meas_error_deg"] >= 2.0
    assert data["summary"]["confidence"]["mean"] > 0.0
    assert "ENTRY" in data["summary"]["phases"]["distribution"]
    S.ReportPrinter().print(r, None, str(out))
    text = capsys.readouterr().out
    assert "Stroke Phases" in text and "Confidence" in text
    text.encode("ascii")                  # Finglish terminal compatibility
