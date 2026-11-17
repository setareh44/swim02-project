# -*- coding: utf-8 -*-
"""History archive, progress trends and plan assignment (no Qt)."""
from __future__ import annotations

import pytest

from app.history import AnalysisSummary, HistoryStore, ProgressTracker
from app.plans import (MEAL_TEMPLATES, WORKOUT_TEMPLATES, MealPlan, PlanStore,
                       WorkoutPlan)


def _engine_json(spm=60.0, swolf=40.0, speed=1.2, sym=80.0, conf=0.9):
    return {"summary": {
        "video": "session.mp4", "style_final": "CRAWL",
        "strokes": {"spm_avg": spm},
        "performance": {"swolf_estimated": swolf},
        "speed": {"mean_mps": speed},
        "symmetry": {"global_pct": sym},
        "confidence": {"mean": conf}}}


def _summaries(swolfs, spms=None):
    out = []
    for i, sw in enumerate(swolfs):
        out.append(AnalysisSummary(
            analysis_id="A-%d" % i, athlete_id="ATH-0001",
            date_iso="2026-11-%02dT10:00:00" % (i + 1),
            video_name="s%d.mp4" % i, style="CRAWL",
            spm=(spms[i] if spms else 60.0), swolf=sw,
            mean_speed=1.2 + 0.05 * i, symmetry=80.0, confidence=0.9))
    return out


# ---------------------------------------------------------------------------
def test_history_record_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("SWIM_DATA_DIR", str(tmp_path))
    store = HistoryStore()
    assert store.list("ATH-0001") == []
    s = store.record("ATH-0001", _engine_json(spm=62.0, swolf=38.5),
                     "s1.mp4", json_file="/tmp/s1.json")
    assert s.athlete_id == "ATH-0001" and s.spm == 62.0
    assert s.swolf == 38.5 and s.mean_speed == 1.2
    items = store.list("ATH-0001")
    assert len(items) == 1 and items[0].analysis_id == s.analysis_id
    full = store.load_full("ATH-0001", s.analysis_id)
    assert full["summary"]["strokes"]["spm_avg"] == 62.0
    assert store.load_full("ATH-0001", "nope") is None
    assert store.list("ATH-9999") == []
    assert "ATH-0001" in store.athlete_ids()


def test_progress_trends_and_forecast():
    improving = ProgressTracker(_summaries([45.0, 42.0, 39.0, 36.0]))
    assert improving.trend("swolf") == ProgressTracker.IMPROVING
    assert improving.delta_pct("swolf") == pytest.approx(-20.0)
    nxt = improving.predict_next("swolf")
    assert nxt == pytest.approx(33.0, abs=1.0)
    assert improving.overall() == ProgressTracker.IMPROVING

    declining = ProgressTracker(_summaries([36.0, 39.0, 42.0, 45.0]))
    assert declining.trend("swolf") == ProgressTracker.DECLINING
    assert declining.overall() == ProgressTracker.DECLINING

    stable = ProgressTracker(_summaries([40.0, 40.1, 39.9, 40.0]))
    assert stable.trend("swolf") == ProgressTracker.STABLE

    single = ProgressTracker(_summaries([40.0]))
    assert single.trend("swolf") == ProgressTracker.STABLE
    assert single.delta_pct("swolf") is None
    assert single.predict_next("swolf") is None

    lines = improving.report_lines_finglish()
    assert any(line.startswith("Overall:") for line in lines)
    for line in lines:                       # terminal-safe ASCII only
        line.encode("ascii")
    assert "SWOLF" in improving.report_text_fa()


def test_plan_store_workouts_and_meals(tmp_path, monkeypatch):
    monkeypatch.setenv("SWIM_DATA_DIR", str(tmp_path))
    store = PlanStore()
    w = store.assign_workout("ATH-0001", "High elbow",
                             [{"title": "Sculling", "detail": "6x50m"}],
                             style_focus="CRAWL", sessions_per_week=3)
    assert isinstance(w, WorkoutPlan) and not w.done
    assert len(store.workouts("ATH-0001")) == 1
    assert store.set_workout_done("ATH-0001", w.plan_id, True)
    assert store.workouts("ATH-0001")[0].done
    assert store.remove_workout("ATH-0001", w.plan_id)
    assert store.workouts("ATH-0001") == []
    assert not store.remove_workout("ATH-0001", "missing")

    m = store.assign_meal("ATH-0001", "Base diet",
                          {"breakfast": "oats"}, goal="general",
                          hydration_note="2L water")
    assert isinstance(m, MealPlan)
    assert store.meals("ATH-0001")[0].meals["breakfast"] == "oats"
    assert store.set_meal_done("ATH-0001", m.plan_id)
    assert store.remove_meal("ATH-0001", m.plan_id)
    assert store.meals("ATH-9999") == []


def test_plan_templates_are_complete():
    assert len(WORKOUT_TEMPLATES) >= 5
    for key, tpl in WORKOUT_TEMPLATES.items():
        assert tpl["title"] and tpl["finglish"] and len(tpl["items"]) >= 2
        tpl["finglish"].encode("ascii")
        for item in tpl["items"]:
            assert item["title"] and item["detail"]
    assert len(MEAL_TEMPLATES) >= 2
    for key, tpl in MEAL_TEMPLATES.items():
        assert tpl["title"] and len(tpl["meals"]) >= 3
