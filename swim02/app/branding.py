# -*- coding: utf-8 -*-
"""Single source of application identity: Setargan-Darya (ستارگان دریا).

Everything user-visible (window titles, about box, settings, data folders,
log tag) reads the constants below, so a future rebrand touches one file.

Backward compatibility with the previous SWIM-AI identity is kept in three
places on purpose:
  * environment variables: SETARGAN_* names are honoured first, the legacy
    SWIM_* names still work as a fallback;
  * data / log folders: the first run on a machine that already has a
    SWIM-AI folder copies it forward (migration, never deletion);
  * technical artifact names (``_swimai`` output suffixes, ``swim_ai``
    module/file names) are intentionally UNCHANGED so old result files,
    scripts and muscle memory keep working.

Qt-free: usable from CLI tools, tests and the engine alike.
"""
from __future__ import annotations

import os
import shutil
import sys

APP_NAME_EN = "Setargan-Darya"
APP_NAME_FA = "ستارگان دریا"
APP_SLUG = "setargan-darya"          # file- and folder-safe ASCII slug
APP_TAG = "Setargan-Darya"           # console / log prefix, e.g. [Setargan-Darya]
ADMIN_NAME = "Setareh"               # project director / master coach
ORG_NAME = "Setargan-Darya"          # QSettings organisation + application

# previous identity (migration source only - do not use for new paths)
LEGACY_NAME_EN = "SWIM-AI"
LEGACY_SLUG = "swim-ai"
LEGACY_TAG = "SWIM-AI"
LEGACY_ORG = "SWIM-AI"


# ---------------------------------------------------------------------------
def env_first(*names: str, default: str = "") -> str:
    """First set-and-non-empty environment variable, else ``default``."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def migrate_dir(new_dir: str, legacy_dir: str) -> None:
    """One-time best-effort copy of a legacy folder to its new location."""
    try:
        if os.path.abspath(new_dir) == os.path.abspath(legacy_dir):
            return
        if not os.path.isdir(legacy_dir):
            return
        new_exists = os.path.isdir(new_dir) and bool(os.listdir(new_dir))
        if new_exists:
            return                      # already migrated (or already in use)
        shutil.copytree(legacy_dir, new_dir, dirs_exist_ok=True)
        print("[%s] Migrated previous data folder: %s -> %s"
              % (APP_TAG, legacy_dir, new_dir))
    except Exception:
        pass                            # migration must never break startup


def _resolve(new_env: str, legacy_env: str) -> str:
    override = env_first(new_env, legacy_env)
    if override:
        path = os.path.abspath(override)
        os.makedirs(path, exist_ok=True)
        return path
    if sys.platform.startswith("win") and os.environ.get("LOCALAPPDATA"):
        new_dir = os.path.join(os.environ["LOCALAPPDATA"], ORG_NAME)
        legacy_dir = os.path.join(os.environ["LOCALAPPDATA"], LEGACY_ORG)
    else:
        new_dir = os.path.join(os.path.expanduser("~"), "." + APP_SLUG)
        legacy_dir = os.path.join(os.path.expanduser("~"), "." + LEGACY_SLUG)
    migrate_dir(new_dir, legacy_dir)
    os.makedirs(new_dir, exist_ok=True)
    return new_dir


def user_data_dir() -> str:
    """Writable folder for users/plans/history/messages (migrates legacy)."""
    return _resolve("SETARGAN_DATA_DIR", "SWIM_DATA_DIR")


def log_dir() -> str:
    """Writable folder for logs and crash reports (migrates legacy)."""
    return _resolve("SETARGAN_LOG_DIR", "SWIM_LOG_DIR")


def sound_disabled() -> bool:
    return env_first("SETARGAN_NO_SOUND", "SWIM_NO_SOUND") == "1"


def auth_disabled() -> bool:
    return env_first("SETARGAN_NO_AUTH", "SWIM_NO_AUTH") == "1"


def pose_model_path() -> str:
    return env_first("SETARGAN_POSE_MODEL", "SWIM_POSE_MODEL")


def gl_disabled() -> bool:
    return env_first("SETARGAN_NO_GL", "SWIM_NO_GL").strip() in (
        "1", "true", "TRUE")


def pause_disabled() -> bool:
    return env_first("SETARGAN_NO_PAUSE", "SWIM_NO_PAUSE") == "1"
