# -*- coding: utf-8 -*-
"""Coaching-insight engine tests (pure numpy, no Qt needed)."""
from __future__ import annotations

import numpy as np

from app.insights import build_insights
from synthetic import make_pose, run_pipeline


def test_insights_on_normal_clip():
    r = run_pipeline(make_pose(n=180))
    items = build_insights(r)
    assert items, "at least one coaching card is expected"
    for item in items:
        assert set(item) >= {"level", "icon", "title", "text"}
        assert item["level"] in {"red", "yellow", "info", "green"}


def test_insights_survive_all_nan_knees():
    """Regression: max() on an empty sequence used to crash the report page."""
    r = run_pipeline(make_pose(n=120))
    for arm in "LR":
        r.bio.knee[arm][:] = np.nan
    r.perf.swolf_est = float("nan")
    r.perf.sl_mean = float("nan")
    r.strokes.spm_avg = float("nan")
    r.sym.global_pct = float("nan")
    items = build_insights(r)
    assert isinstance(items, list)


def test_insights_report_missing_symmetry():
    r = run_pipeline(make_pose(n=120))
    r.sym.global_pct = float("nan")
    titles = [i["title"] for i in build_insights(r)]
    assert not any("تقارن" in t for t in titles)
