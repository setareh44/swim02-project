#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless user management for SWIM-AI (coaches / IT admins).

All output is plain ASCII Finglish so Windows CMD never shows "???".

Usage (run from the project folder):
    python tools/manage_users.py setup-admin
    python tools/manage_users.py add-athlete --name "Ali Rezaei" --pin 1234 --age 16 --exp 3 --skill intermediate
    python tools/manage_users.py list
    python tools/manage_users.py reset-pin --id ATH-0001 --pin 5678
    python tools/manage_users.py delete --id ATH-0001
    python tools/manage_users.py change-admin

The database lives in %LOCALAPPDATA%\\SWIM-AI (Windows) or ~/.swim-ai,
or wherever SWIM_DATA_DIR points.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import AuthError, AuthService, SKILL_FINGLISH, SKILL_TIERS, alog


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


def cmd_add_athlete(auth: AuthService, args) -> int:
    pin = args.pin
    if not pin:
        pin = getpass.getpass("PIN (4-12 digits): ")
    try:
        user = auth.create_athlete(args.name, pin, age=args.age,
                                   experience_years=args.exp,
                                   skill_tier=args.skill)
    except AuthError as exc:
        alog("Khata: %s" % exc)
        return 1
    alog("OK: shenagar sakhte shod: %s (%s)" % (user.user_id, user.name))
    return 0


def cmd_list(auth: AuthService, _args) -> int:
    users = auth.list_athletes()
    alog("Tedad-e shenagaran: %d" % len(users))
    alog("%-10s | %-24s | age | exp  | skill" % ("ID", "name"))
    alog("-" * 64)
    for u in users:
        alog("%-10s | %-24s | %3d | %4.1f | %s%s" % (
            u.user_id, u.name[:24], u.age, u.experience_years,
            SKILL_FINGLISH.get(u.skill_tier, u.skill_tier),
            "" if u.active else " (inactive)"))
    alog("Admin setup: %s" % ("yes" if auth.is_admin_setup() else "no"))
    return 0


def cmd_reset_pin(auth: AuthService, args) -> int:
    pin = args.pin
    if not pin:
        pin = getpass.getpass("New PIN (4-12 digits): ")
    try:
        auth.admin_reset_pin(args.id, pin)
    except AuthError as exc:
        alog("Khata: %s" % exc)
        return 1
    alog("OK: PIN reset shod: %s" % args.id)
    return 0


def cmd_delete(auth: AuthService, args) -> int:
    try:
        auth.remove_athlete(args.id)
    except AuthError as exc:
        alog("Khata: %s" % exc)
        return 1
    alog("OK: shenagar hazf shod: %s" % args.id)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="SWIM-AI user management (Finglish)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup-admin").set_defaults(func=cmd_setup_admin)
    sub.add_parser("change-admin").set_defaults(func=cmd_change_admin)
    pa = sub.add_parser("add-athlete")
    pa.add_argument("--name", required=True)
    pa.add_argument("--pin", default="")
    pa.add_argument("--age", type=int, default=0)
    pa.add_argument("--exp", type=float, default=0.0)
    pa.add_argument("--skill", choices=SKILL_TIERS, default="beginner")
    pa.set_defaults(func=cmd_add_athlete)
    sub.add_parser("list").set_defaults(func=cmd_list)
    pr = sub.add_parser("reset-pin")
    pr.add_argument("--id", required=True)
    pr.add_argument("--pin", default="")
    pr.set_defaults(func=cmd_reset_pin)
    pd = sub.add_parser("delete")
    pd.add_argument("--id", required=True)
    pd.set_defaults(func=cmd_delete)
    args = p.parse_args()
    return args.func(AuthService(), args)


if __name__ == "__main__":
    sys.exit(main())
