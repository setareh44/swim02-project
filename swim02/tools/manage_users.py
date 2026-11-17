#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless user management for Setargan-Darya (coaches / IT admins).

All output is plain ASCII Finglish so Windows CMD never shows "???".

Usage (run from the project folder):
    python tools/manage_users.py setup-admin
    python tools/manage_users.py add-student --name "Sara Ahmadi" --username sara.a --secret 1234 --age 16 --exp 3 --skill intermediate
    python tools/manage_users.py list
    python tools/manage_users.py login --user sara.a --secret 1234
    python tools/manage_users.py reset-secret --id ATH-0001 --secret 5678
    python tools/manage_users.py delete --id ATH-0001
    python tools/manage_users.py change-admin
    python tools/manage_users.py inbox
    python tools/manage_users.py inbox-read --id MSG-...

Secrets: 4-12 digits = PIN, anything else (min 6 ASCII chars) = password.
Capacity: up to 50 students. Legacy command names (add-athlete, reset-pin)
still work.

The database lives in %LOCALAPPDATA%\\Setargan-Darya (Windows) or
~/.setargan-darya, or wherever SETARGAN_DATA_DIR points (a previous
SWIM-AI folder is migrated forward automatically).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import (MAX_ATHLETES, AuthError, AuthService, SKILL_FINGLISH,
                      SKILL_TIERS, alog)
from app.messaging import MessageStore


def cmd_setup_admin(auth: AuthService, _args) -> int:
    if auth.is_admin_setup():
        alog("Khata: ramz-e modir ghablan tanzim shode ast.")
        return 1
    pw1 = getpass.getpass("New master password (min 8 ASCII chars): ")
    pw2 = getpass.getpass("Repeat master password: ")
    if pw1 != pw2:
        alog("Khata: tekrar-e ramz yeki nist.")
        return 1
    try:
        auth.setup_admin(pw1)
    except AuthError as exc:
        alog("Khata: %s" % exc)
        return 1
    alog("OK: ramz-e modir tanzim shod.")
    return 0


def cmd_change_admin(auth: AuthService, _args) -> int:
    old = getpass.getpass("Old master password: ")
    new1 = getpass.getpass("New master password: ")
    new2 = getpass.getpass("Repeat new master password: ")
    if new1 != new2:
        alog("Khata: tekrar-e ramz yeki nist.")
        return 1
    try:
        auth.change_admin_password(old, new1)
    except AuthError as exc:
        alog("Khata: %s" % exc)
        return 1
    alog("OK: ramz-e modir taghyir kard.")
    return 0


def cmd_add_student(auth: AuthService, args) -> int:
    secret = args.secret or args.pin
    if not secret:
        secret = getpass.getpass("Secret (PIN 4-12 digits or password 6+): ")
    try:
        user = auth.create_athlete(args.name, secret, age=args.age,
                                   experience_years=args.exp,
                                   skill_tier=args.skill,
                                   username=args.username or None)
    except AuthError as exc:
        alog("Khata: %s" % exc)
        return 1
    alog("OK: shagerd sakhte shod: %s (@%s)" % (user.user_id, user.username))
    return 0


def cmd_list(auth: AuthService, _args) -> int:
    users = auth.list_athletes()
    alog("Tedad-e shagerdan: %d / %d" % (len(users), MAX_ATHLETES))
    alog("%-10s | %-16s | %-20s | age | exp  | skill" % ("ID", "username",
                                                          "name"))
    alog("-" * 78)
    for u in users:
        alog("%-10s | %-16s | %-20s | %3d | %4.1f | %s%s" % (
            u.user_id, ("@" + u.username)[:16], u.name[:20], u.age,
            u.experience_years, SKILL_FINGLISH.get(u.skill_tier, u.skill_tier),
            "" if u.active else " (inactive)"))
    alog("Admin setup: %s" % ("yes" if auth.is_admin_setup() else "no"))
    return 0


def cmd_login(auth: AuthService, args) -> int:
    secret = args.secret
    if not secret:
        secret = getpass.getpass("Secret: ")
    try:
        session = auth.login_athlete(args.user, secret)
    except AuthError as exc:
        alog("FAIL: %s" % exc)
        return 1
    alog("OK: login movafagh: %s (%s)" % (session.display_name,
                                          session.user_id))
    return 0


def cmd_reset_secret(auth: AuthService, args) -> int:
    secret = args.secret or args.pin
    if not secret:
        secret = getpass.getpass("New secret: ")
    try:
        auth.admin_reset_secret(args.id, secret)
    except AuthError as exc:
        alog("Khata: %s" % exc)
        return 1
    alog("OK: ramz reset shod: %s" % args.id)
    return 0


def cmd_delete(auth: AuthService, args) -> int:
    try:
        auth.remove_athlete(args.id)
    except AuthError as exc:
        alog("Khata: %s" % exc)
        return 1
    alog("OK: shagerd hazf shod: %s" % args.id)
    return 0


def cmd_inbox(_auth: AuthService, _args) -> int:
    store = MessageStore()
    messages = store.inbox()
    alog("Payam-haye nakhande: %d / %d" % (store.unread_count(),
                                           len(messages)))
    for m in messages[:30]:
        alog("[%s] %s | %s | %s" % ("NEW" if not m.read else "   ",
                                    m.created_at[:16], m.from_name,
                                    m.title_fn or m.title_fa.encode(
                                        "ascii", "replace").decode("ascii")))
    return 0


def cmd_inbox_read(_auth: AuthService, args) -> int:
    if MessageStore().mark_read(args.id):
        alog("OK: payam khande shod: %s" % args.id)
        return 0
    alog("Khata: payam peyda nashod: %s" % args.id)
    return 1


def main() -> int:
    p = argparse.ArgumentParser(
        description="Setargan-Darya user management (Finglish)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup-admin").set_defaults(func=cmd_setup_admin)
    sub.add_parser("change-admin").set_defaults(func=cmd_change_admin)

    def _add_student_parser(name: str):
        pa = sub.add_parser(name)
        pa.add_argument("--name", required=True)
        pa.add_argument("--username", default="")
        pa.add_argument("--secret", default="")
        pa.add_argument("--pin", default="")      # legacy alias
        pa.add_argument("--age", type=int, default=0)
        pa.add_argument("--exp", type=float, default=0.0)
        pa.add_argument("--skill", choices=SKILL_TIERS, default="beginner")
        pa.set_defaults(func=cmd_add_student)
        return pa

    _add_student_parser("add-student")
    _add_student_parser("add-athlete")            # legacy alias
    sub.add_parser("list").set_defaults(func=cmd_list)
    pl = sub.add_parser("login")
    pl.add_argument("--user", required=True)
    pl.add_argument("--secret", default="")
    pl.set_defaults(func=cmd_login)

    def _reset_parser(name: str):
        pr = sub.add_parser(name)
        pr.add_argument("--id", required=True)
        pr.add_argument("--secret", default="")
        pr.add_argument("--pin", default="")      # legacy alias
        pr.set_defaults(func=cmd_reset_secret)
        return pr

    _reset_parser("reset-secret")
    _reset_parser("reset-pin")                    # legacy alias
    pd = sub.add_parser("delete")
    pd.add_argument("--id", required=True)
    pd.set_defaults(func=cmd_delete)
    sub.add_parser("inbox").set_defaults(func=cmd_inbox)
    pr = sub.add_parser("inbox-read")
    pr.add_argument("--id", required=True)
    pr.set_defaults(func=cmd_inbox_read)
    args = p.parse_args()
    return args.func(AuthService(), args)


if __name__ == "__main__":
    sys.exit(main())
