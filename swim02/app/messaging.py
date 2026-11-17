# -*- coding: utf-8 -*-
"""Internal messaging / notification queue (Qt-free).

The coach (Setareh) has one inbox; students append to it::

    <data_dir>/messages.json   {"messages": [...]}

The main producer is the daily compliance tracker: every student submit
creates exactly one message for the admin dashboard, e.g.
"Student [Sara] followed their diet successfully today". Each message is
stored in Persian (UI) and ASCII Finglish (terminal / speech).
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from typing import List, Optional

from .auth import alog, data_dir, utcnow_iso

MESSAGES_FILE = "messages.json"
MAX_MESSAGES = 500


@dataclass
class Message:
    msg_id: str
    created_at: str
    from_id: str
    from_name: str
    kind: str = "compliance"       # compliance | note | system
    title_fa: str = ""
    title_fn: str = ""
    body_fa: str = ""
    body_fn: str = ""
    read: bool = False
    read_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in (data or {}).items() if k in known}
        obj = cls(msg_id=str(clean.get("msg_id", "")),
                  created_at=str(clean.get("created_at", "")),
                  from_id=str(clean.get("from_id", "")),
                  from_name=str(clean.get("from_name", "")))
        for key, val in clean.items():
            if key in ("msg_id", "created_at", "from_id", "from_name"):
                continue
            try:
                if key == "read":
                    setattr(obj, key, bool(val))
                else:
                    setattr(obj, key, str(val or ""))
            except (TypeError, ValueError):
                continue
        return obj


class MessageStore:
    """Append / read the admin inbox with atomic writes."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(data_dir(), MESSAGES_FILE)

    # -- persistence ------------------------------------------------------
    def _read_all(self) -> List[Message]:
        if not os.path.isfile(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        items = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [Message.from_dict(d) for d in items if isinstance(d, dict)]

    def _write_all(self, messages: List[Message]) -> None:
        folder = os.path.dirname(self.path) or "."
        os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"messages": [m.to_dict() for m in messages]}, f,
                          ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError as exc:
            alog("Hoshdar: zakhire payam namovafagh bood: %s" % exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    # -- API --------------------------------------------------------------
    def send(self, from_id: str, from_name: str, title_fa: str,
             title_fn: str, body_fa: str = "", body_fn: str = "",
             kind: str = "compliance") -> Message:
        stamp = utcnow_iso().replace(":", "").replace("+", "z")
        token = secrets.token_hex(3).upper()
        msg = Message(msg_id="MSG-%s-%s" % (stamp, token),
                      created_at=utcnow_iso(),
                      from_id=from_id, from_name=from_name, kind=kind,
                      title_fa=title_fa, title_fn=title_fn,
                      body_fa=body_fa, body_fn=body_fn)
        messages = self._read_all()
        messages.append(msg)
        messages = messages[-MAX_MESSAGES:]
        self._write_all(messages)
        return msg

    def inbox(self, unread_first: bool = True) -> List[Message]:
        # newest first; the insertion index breaks same-second ties
        keyed = sorted(enumerate(self._read_all()),
                       key=lambda p: (p[1].created_at, p[0]), reverse=True)
        messages = [m for _, m in keyed]
        if not unread_first:
            return messages
        # unread first (newest first), then read (newest first)
        return ([m for m in messages if not m.read]
                + [m for m in messages if m.read])

    def unread_count(self) -> int:
        return sum(1 for m in self._read_all() if not m.read)

    def mark_read(self, msg_id: str) -> bool:
        messages = self._read_all()
        changed = False
        for m in messages:
            if m.msg_id == msg_id and not m.read:
                m.read = True
                m.read_at = utcnow_iso()
                changed = True
        if changed:
            self._write_all(messages)
        return changed

    def mark_all_read(self) -> int:
        messages = self._read_all()
        count = 0
        for m in messages:
            if not m.read:
                m.read = True
                m.read_at = utcnow_iso()
                count += 1
        if count:
            self._write_all(messages)
        return count


class ComplianceNotifier:
    """Builds the admin message for one daily compliance submit."""

    def __init__(self, store: Optional[MessageStore] = None):
        self.store = store or MessageStore()

    def notify(self, athlete_id: str, athlete_name: str, day: str,
               diet_done: bool, workout_done: bool,
               note: str = "") -> Message:
        name = (athlete_name or athlete_id).strip()
        if diet_done and workout_done:
            title_fa = ("شاگرد [%s] امروز هم رژیم و هم تمرینش را کامل انجام داد"
                        % name)
            title_fn = ("Student [%s] followed diet AND workout fully today"
                        % name)
        elif diet_done:
            title_fa = "شاگرد [%s] امروز رژیمش را با موفقیت رعایت کرد" % name
            title_fn = ("Student [%s] followed their diet successfully today"
                        % name)
        elif workout_done:
            title_fa = "شاگرد [%s] امروز تمرینش را کامل انجام داد" % name
            title_fn = ("Student [%s] completed their workout fully today"
                        % name)
        else:
            title_fa = "شاگرد [%s] امروز رژیم و تمرینش را انجام نداد" % name
            title_fn = ("Student [%s] missed both diet and workout today"
                        % name)
        body_fa = "تاریخ: %s | رژیم: %s | تمرین: %s" % (
            day, "بله ✓" if diet_done else "خیر ✗",
            "بله ✓" if workout_done else "خیر ✗")
        body_fn = "date=%s diet=%s workout=%s" % (
            day, "YES" if diet_done else "NO",
            "YES" if workout_done else "NO")
        if note.strip():
            body_fa += "\nیادداشت شاگرد: %s" % note.strip()
            body_fn += " | note=%s" % note.strip().encode(
                "ascii", "replace").decode("ascii")
        msg = self.store.send(athlete_id, name, title_fa, title_fn,
                              body_fa, body_fn, kind="compliance")
        alog("Payam-e compliance ersal shod: %s" % msg.msg_id)
        return msg
