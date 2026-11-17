# -*- coding: utf-8 -*-
"""تنظیمات پایدار برنامه (QSettings).

ذخیره‌سازی در رجیستری ویندوز (`HKCU\\Software\\Setargan-Darya`) یا فایل تنظیمات
لینوکس/مک انجام می‌شود؛ بنابراین در نسخه نصب‌شده در Program Files هم کار دارد.
تنظیمات نسخه قدیمی (SWIM-AI) در اولین اجرا خودکار منتقل می‌شود.
"""
from __future__ import annotations

import json
from typing import Any

from .branding import LEGACY_ORG, ORG_NAME

_ORG = ORG_NAME
_APP = ORG_NAME

KEY_ABOUT_SEEN = "ui/about_seen"
KEY_SOUND = "ui/startup_sound"
KEY_PROFILE = "report/swimmer_profile"

_DEFAULTS = {
    KEY_ABOUT_SEEN: False,
    KEY_SOUND: True,
}


def _settings():
    try:
        from PySide6.QtCore import QSettings
    except Exception:                       # pragma: no cover - بدون Qt
        return None
    try:
        return QSettings(_ORG, _APP)
    except Exception:                       # pragma: no cover
        return None


def migrate_legacy_settings() -> bool:
    """Copy SWIM-AI settings forward once (sound toggle, about seen, ...).

    Returns True when anything was migrated. Never raises; without Qt it is
    a no-op (there is nothing to migrate to on a headless box anyway).
    """
    try:
        from PySide6.QtCore import QSettings
    except Exception:                       # pragma: no cover - بدون Qt
        return False
    try:
        new = QSettings(_ORG, _APP)
        if new.allKeys():
            return False                    # already in use: nothing to do
        old = QSettings(LEGACY_ORG, LEGACY_ORG)
        keys = old.allKeys()
        if not keys:
            return False
        for key in keys:
            new.setValue(key, old.value(key))
        new.sync()
        return True
    except Exception:                       # pragma: no cover
        return False


def get_bool(key: str, default: bool | None = None) -> bool:
    if default is None:
        default = bool(_DEFAULTS.get(key, False))
    s = _settings()
    if s is None:
        return default
    try:
        raw = s.value(key, default)
    except Exception:
        return default
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(raw)


def set_bool(key: str, value: bool) -> None:
    s = _settings()
    if s is None:
        return
    try:
        s.setValue(key, bool(value))
        s.sync()
    except Exception:
        pass


def get_str(key: str, default: str = "") -> str:
    s = _settings()
    if s is None:
        return default
    try:
        return str(s.value(key, default) or default)
    except Exception:
        return default


def set_str(key: str, value: str) -> None:
    s = _settings()
    if s is None:
        return
    try:
        s.setValue(key, value)
        s.sync()
    except Exception:
        pass


def get_json(key: str, default: Any = None):
    raw = get_str(key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def set_json(key: str, value: Any) -> None:
    try:
        set_str(key, json.dumps(value, ensure_ascii=False))
    except Exception:
        pass
