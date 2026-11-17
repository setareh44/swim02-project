# -*- coding: utf-8 -*-
"""Daily diet/workout compliance tracker tests (no Qt)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.compliance import ComplianceStore, today_iso


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    return ComplianceStore()


def test_submit_and_get_today(store):
    assert store.get_day("ATH-0001") is None
    entry = store.submit("ATH-0001", True, False, note="cheat meal at noon")
    assert entry.day == today_iso()
    assert entry.diet_done and not entry.workout_done
    assert entry.note == "cheat meal at noon"
    again = store.get_day("ATH-0001")
    assert again is not None and again.submitted_at == entry.submitted_at


def test_resubmit_same_day_replaces(store):
    store.submit("ATH-0001", True, False)
    store.submit("ATH-0001", True, True, note="evening run done")
    assert len(store.history("ATH-0001", 30)) == 1
    assert store.get_day("ATH-0001").workout_done


def test_bad_day_is_rejected(store):
    with pytest.raises(ValueError):
        store.submit("ATH-0001", True, True, day="not-a-day")


def test_streak_counts_consecutive_full_days(store):
    today = date.today()
    for back in range(3):
        store.submit("ATH-0001", True, True,
                     day=(today - timedelta(days=back)).isoformat())
    assert store.streak("ATH-0001") == 3
    assert store.streak("ATH-0001", kind="diet") == 3
    # a diet-only day breaks the full streak but keeps the diet streak
    store.submit("ATH-0001", True, False,
                 day=(today - timedelta(days=3)).isoformat())
    assert store.streak("ATH-0001") == 3
    assert store.streak("ATH-0001", kind="diet") == 4


def test_streak_tolerates_unsubmitted_today(store):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    store.submit("ATH-0001", True, True, day=yesterday)
    assert store.get_day("ATH-0001") is None      # today still open
    assert store.streak("ATH-0001") == 1


def test_week_rate_and_summaries(store):
    today = date.today()
    store.submit("ATH-0001", True, True,
                 day=(today - timedelta(days=1)).isoformat())
    store.submit("ATH-0001", True, False,
                 day=(today - timedelta(days=2)).isoformat())
    rate = store.week_rate("ATH-0001")
    assert rate["submitted"] == 2
    assert rate["diet"] == pytest.approx(100.0 * 2 / 7)
    assert rate["workout"] == pytest.approx(100.0 * 1 / 7)
    assert "رکورد" in store.summary_fa("ATH-0001")
    fn = store.summary_finglish("ATH-0001")
    fn.encode("ascii")
    assert "streak=" in fn


def test_persistence_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    ComplianceStore().submit("ATH-0007", False, True)
    assert ComplianceStore().get_day("ATH-0007").workout_done


def test_students_are_isolated(store):
    store.submit("ATH-0001", True, True)
    assert store.get_day("ATH-0002") is None
    assert store.streak("ATH-0002") == 0
