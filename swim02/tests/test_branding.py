# -*- coding: utf-8 -*-
"""Application identity + legacy SWIM-AI fallback tests (no Qt)."""
from __future__ import annotations

import os

from app import branding


def test_identity_constants():
    assert branding.APP_NAME_EN == "Setargan-Darya"
    assert branding.APP_NAME_FA == "ستارگان دریا"
    assert branding.APP_TAG == "Setargan-Darya"
    assert branding.ADMIN_NAME == "Setareh"
    assert branding.ORG_NAME == "Setargan-Darya"
    branding.APP_SLUG.encode("ascii")
    branding.APP_TAG.encode("ascii")


def test_env_first_prefers_new_names(monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", "/new")
    monkeypatch.setenv("SWIM_DATA_DIR", "/old")
    assert branding.env_first("SETARGAN_DATA_DIR", "SWIM_DATA_DIR") == "/new"
    monkeypatch.delenv("SETARGAN_DATA_DIR")
    assert branding.env_first("SETARGAN_DATA_DIR", "SWIM_DATA_DIR") == "/old"
    monkeypatch.delenv("SWIM_DATA_DIR")
    assert branding.env_first("SETARGAN_DATA_DIR", "SWIM_DATA_DIR") == ""
    assert branding.env_first("SETARGAN_DATA_DIR", "SWIM_DATA_DIR",
                              default="d") == "d"


def test_toggle_helpers_honour_both_names(monkeypatch):
    for new, old, fn in (
            ("SETARGAN_NO_SOUND", "SWIM_NO_SOUND", branding.sound_disabled),
            ("SETARGAN_NO_AUTH", "SWIM_NO_AUTH", branding.auth_disabled),
            ("SETARGAN_NO_GL", "SWIM_NO_GL", branding.gl_disabled),
            ("SETARGAN_NO_PAUSE", "SWIM_NO_PAUSE", branding.pause_disabled)):
        monkeypatch.delenv(new, raising=False)
        monkeypatch.delenv(old, raising=False)
        assert fn() is False
        monkeypatch.setenv(old, "1")
        assert fn() is True
        monkeypatch.delenv(old)
        monkeypatch.setenv(new, "1")
        assert fn() is True
        monkeypatch.delenv(new)


def test_legacy_data_dir_still_works(tmp_path, monkeypatch):
    monkeypatch.delenv("SETARGAN_DATA_DIR", raising=False)
    monkeypatch.setenv("SWIM_DATA_DIR", str(tmp_path))
    from app.auth import AuthService
    auth = AuthService()
    auth.setup_admin("legacy-master")
    assert auth.verify_admin("legacy-master")
    assert os.path.isfile(os.path.join(str(tmp_path), "users.json"))


def test_legacy_log_dir_still_works(tmp_path, monkeypatch):
    monkeypatch.delenv("SETARGAN_LOG_DIR", raising=False)
    monkeypatch.setenv("SWIM_LOG_DIR", str(tmp_path))
    from app import diagnostics
    assert diagnostics.log_dir() == str(tmp_path)


def test_migrate_dir_copies_but_never_deletes(tmp_path):
    legacy = tmp_path / "old"
    legacy.mkdir()
    (legacy / "users.json").write_text("{}", encoding="utf-8")
    new = tmp_path / "new"
    branding.migrate_dir(str(new), str(legacy))
    assert (new / "users.json").is_file()
    assert (legacy / "users.json").is_file()      # source is kept
    # a non-empty target is never overwritten
    (new / "users.json").write_text('{"v": 2}', encoding="utf-8")
    branding.migrate_dir(str(new), str(legacy))
    assert (new / "users.json").read_text(encoding="utf-8") == '{"v": 2}'
