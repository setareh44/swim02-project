# -*- coding: utf-8 -*-
"""RBAC tests: master password, athlete PINs, CRUD, persistence (no Qt)."""
from __future__ import annotations

import json
import os

import pytest

from app.auth import (AuthError, AuthService, PasswordHasher, UserRole,
                      UserStore, data_dir)


@pytest.fixture()
def auth(tmp_path, monkeypatch):
    monkeypatch.setenv("SWIM_DATA_DIR", str(tmp_path))
    return AuthService()


# ---------------------------------------------------------------------------
def test_password_hasher_roundtrip_and_reject():
    rec = PasswordHasher.hash_secret("my-master-pw")
    assert rec["hash"] != "my-master-pw"
    assert PasswordHasher.verify("my-master-pw", rec)
    assert not PasswordHasher.verify("wrong", rec)
    assert not PasswordHasher.verify("", rec)
    assert not PasswordHasher.verify("my-master-pw", None)
    assert not PasswordHasher.verify("my-master-pw", {"hash": "zz"})
    # salts are random: same password -> different hashes
    assert (PasswordHasher.hash_secret("x")["salt"]
            != PasswordHasher.hash_secret("x")["salt"])


def test_admin_setup_verify_change(auth):
    assert not auth.is_admin_setup()
    with pytest.raises(AuthError):
        auth.setup_admin("short")          # < 8 chars
    auth.setup_admin("master-2026")
    assert auth.is_admin_setup()
    assert auth.verify_admin("master-2026")
    assert not auth.verify_admin("nope")
    with pytest.raises(AuthError):
        auth.setup_admin("another-one")    # already set
    with pytest.raises(AuthError):
        auth.change_admin_password("wrong-old", "new-master-1")
    auth.change_admin_password("master-2026", "new-master-1")
    assert auth.verify_admin("new-master-1")
    session = auth.login_admin("new-master-1")
    assert session.is_admin and session.user_id == "ADMIN"
    with pytest.raises(AuthError):
        auth.login_admin("bad")


def test_no_plaintext_secrets_on_disk(auth, tmp_path):
    auth.setup_admin("super-secret-1")
    auth.create_athlete("Ali", "1234")
    raw = open(os.path.join(str(tmp_path), "users.json"),
               encoding="utf-8").read()
    assert "super-secret-1" not in raw
    assert "1234" not in raw
    data = json.loads(raw)
    assert data["admin"]["hash"] and data["admin"]["salt"]


def test_athlete_lifecycle(auth):
    u = auth.create_athlete("Sara Ahmadi", "4321", age=16,
                            experience_years=3.5, skill_tier="intermediate")
    assert u.user_id.startswith("ATH-")
    assert u.role == UserRole.ATHLETE
    assert auth.verify_athlete(u.user_id, "4321") is not None
    assert auth.verify_athlete(u.user_id, "0000") is None
    assert auth.verify_athlete("ATH-9999", "4321") is None
    session = auth.login_athlete(u.user_id, "4321")
    assert session.is_athlete and session.display_name == "Sara Ahmadi"
    with pytest.raises(AuthError):
        auth.login_athlete(u.user_id, "bad-pin")
    # change + reset PIN
    auth.change_athlete_pin(u.user_id, "4321", "9999")
    assert auth.verify_athlete(u.user_id, "9999") is not None
    with pytest.raises(AuthError):
        auth.change_athlete_pin(u.user_id, "wrong", "1111")
    auth.admin_reset_pin(u.user_id, "2222")
    assert auth.verify_athlete(u.user_id, "2222") is not None
    # update + delete
    auth.update_athlete(u.user_id, age=17, skill_tier="advanced")
    assert auth.store.get(u.user_id).age == 17
    auth.remove_athlete(u.user_id)
    assert auth.store.get(u.user_id) is None
    with pytest.raises(AuthError):
        auth.remove_athlete(u.user_id)


def test_athlete_validation(auth):
    with pytest.raises(AuthError):
        auth.create_athlete("", "1234")
    with pytest.raises(AuthError):
        auth.create_athlete("X", "12")         # too short
    with pytest.raises(AuthError):
        auth.create_athlete("X", "abcd")       # not digits
    with pytest.raises(AuthError):
        auth.create_athlete("X", "1234", skill_tier="nope")
    auth.create_athlete("A", "1111", user_id="ATH-0042")
    with pytest.raises(AuthError):
        auth.create_athlete("B", "2222", user_id="ATH-0042")  # duplicate
    # inactive athletes cannot log in
    auth.update_athlete("ATH-0042", active=False)
    with pytest.raises(AuthError):
        auth.login_athlete("ATH-0042", "1111")
    assert auth.list_athletes(active_only=True) == []
    assert len(auth.list_athletes()) == 1


def test_persistence_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("SWIM_DATA_DIR", str(tmp_path))
    a1 = AuthService()
    a1.setup_admin("persist-master")
    a1.create_athlete("Tom", "5555", age=20)
    a2 = AuthService()          # fresh instance, same folder
    assert a2.is_admin_setup()
    assert a2.verify_admin("persist-master")
    assert a2.verify_athlete("ATH-0001", "5555") is not None
    assert data_dir() == str(tmp_path)
