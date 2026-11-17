# -*- coding: utf-8 -*-
"""Motivational engine: deterministic selection + personalisation (no Qt)."""
from __future__ import annotations

from app.history import AnalysisSummary
from app.motivation import QUOTE_BANK, MotivationEngine


def _summaries(swolfs):
    return [AnalysisSummary(
        analysis_id="A-%d" % i, athlete_id="ATH-1",
        date_iso="2026-11-%02dT10:00:00" % (i + 1), video_name="s.mp4",
        style="CRAWL", spm=60.0, swolf=sw, mean_speed=1.2,
        symmetry=80.0, confidence=0.9) for i, sw in enumerate(swolfs)]


def test_bank_covers_all_verdicts_and_ascii_finglish():
    assert len(QUOTE_BANK) >= 12
    tags = {t for q in QUOTE_BANK for t in q.tags}
    for need in ("welcome", "improving", "declining", "stable", "general"):
        assert need in tags
    for q in QUOTE_BANK:
        assert q.fa.strip()
        q.finglish.encode("ascii")          # terminal / TTS safe


def test_selection_is_deterministic_per_day():
    eng = MotivationEngine()
    assert eng.select("improving", "ATH-1") == eng.select("improving", "ATH-1")
    # every verdict resolves to a quote carrying that tag (or general)
    for verdict in ("improving", "declining", "stable", "welcome"):
        q = eng.select(verdict, "ATH-1")
        assert verdict in q.tags or "general" in q.tags


def test_personalise_welcome_without_history():
    eng = MotivationEngine()
    quote, fa, fn, verdict = eng.personalise([], athlete_name="Sara",
                                             user_id="ATH-1")
    assert verdict == "welcome"
    assert "welcome" in quote.tags
    assert "Sara" in fa and "Sara" in fn
    fn.encode("ascii")


def test_personalise_uses_real_numbers():
    eng = MotivationEngine()
    q1, fa1, fn1, v1 = eng.personalise(_summaries([45.0, 40.0, 35.0]),
                                       athlete_name="Ali", user_id="A")
    assert v1 == "improving"
    assert "SWOLF" in fa1 and "SWOLF" in fn1     # references the metric
    fn1.encode("ascii")

    q2, fa2, fn2, v2 = eng.personalise(_summaries([35.0, 40.0, 45.0]),
                                       user_id="A")
    assert v2 == "declining"
    fn2.encode("ascii")

    q3, fa3, fn3, v3 = eng.personalise(_summaries([40.0, 40.0, 40.0]),
                                       user_id="A")
    assert v3 == "stable"
    fn3.encode("ascii")
