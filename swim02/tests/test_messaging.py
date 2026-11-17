# -*- coding: utf-8 -*-
"""Admin inbox / compliance notification tests (no Qt)."""
from __future__ import annotations

from app.messaging import ComplianceNotifier, MessageStore


def test_send_and_inbox_order(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    store = MessageStore()
    assert store.unread_count() == 0
    m1 = store.send("ATH-0001", "Sara", "t1", "t1fn", "b1", "b1fn")
    m2 = store.send("ATH-0002", "Ali", "t2", "t2fn")
    assert store.unread_count() == 2
    inbox = store.inbox()
    assert [m.msg_id for m in inbox] == [m2.msg_id, m1.msg_id]  # newest first
    assert store.mark_read(m2.msg_id)
    assert store.unread_count() == 1
    inbox = store.inbox()
    assert inbox[0].msg_id == m1.msg_id     # unread still first
    assert not store.mark_read("MSG-nope")
    assert store.mark_all_read() == 1
    assert store.unread_count() == 0
    assert store.mark_all_read() == 0


def test_inbox_survives_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    MessageStore().send("ATH-0001", "Sara", "سلام", "salam")
    assert MessageStore().unread_count() == 1


def test_compliance_notifier_builds_all_four_cases(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    noti = ComplianceNotifier()
    both = noti.notify("ATH-0001", "Sara", "2026-11-17", True, True)
    assert "هم رژیم و هم تمرین" in both.title_fa
    assert "diet AND workout" in both.title_fn
    diet = noti.notify("ATH-0001", "Sara", "2026-11-17", True, False,
                       note="no pool today")
    assert "رژیمش را با موفقیت رعایت کرد" in diet.title_fa
    assert ("Student [Sara] followed their diet successfully today"
            in diet.title_fn)
    diet.title_fn.encode("ascii")
    assert "no pool today" in diet.body_fn
    work = noti.notify("ATH-0002", "Ali", "2026-11-17", False, True)
    assert "تمرینش را کامل انجام داد" in work.title_fa
    assert "completed their workout" in work.title_fn
    none = noti.notify("ATH-0003", "Tom", "2026-11-17", False, False)
    assert "انجام نداد" in none.title_fa
    assert "missed both diet and workout" in none.title_fn
    for msg in (both, diet, work, none):
        assert msg.kind == "compliance"
        msg.title_fn.encode("ascii")
        msg.body_fn.encode("ascii")


def test_notifier_appends_exactly_one_message(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    noti = ComplianceNotifier()
    assert len(noti.store.inbox()) == 0
    noti.notify("ATH-0001", "Sara", "2026-11-17", True, True)
    assert len(noti.store.inbox()) == 1
