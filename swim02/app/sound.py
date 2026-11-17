# -*- coding: utf-8 -*-
"""پخش موزیک کوتاه شروع برنامه (تم آب و استخر).

فایل صوتی `app/assets/startup.wav` همراه برنامه نصب می‌شود؛ پخش آن هیچ
کتابخانه‌ای لازم ندارد:
  * ویندوز: `winsound` (داخل خود پایتون)
  * مک: `afplay`
  * لینوکس: `aplay` / `paplay` / `ffplay` اگر موجود باشند
اگر هیچ‌کدام نبود، برنامه بی‌صدا و بدون خطا ادامه می‌دهد.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def asset_path(name: str) -> str:
    """مسیر فایل همراه برنامه (در بیلد PyInstaller داخل پوشه موقت است)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / "app" / "assets" / name
        if p.is_file():
            return str(p)
    here = Path(__file__).resolve().parent / "assets" / name
    if here.is_file():
        return str(here)
    exe_dir = Path(getattr(sys, "executable", ""))
    if getattr(sys, "frozen", False):
        p = exe_dir.parent / "app" / "assets" / name
        if p.is_file():
            return str(p)
    return ""


def startup_sound_available() -> bool:
    return bool(asset_path("startup.wav"))


def play_startup_sound(volume_pct: int = 70) -> bool:
    """پخش غیرمسدودکننده؛ True اگر پخش آغاز شد."""
    from . import prefs

    if not prefs.get_bool(prefs.KEY_SOUND, True):
        return False
    path = asset_path("startup.wav")
    if not path:
        return False
    try:
        if sys.platform.startswith("win"):
            import winsound
            # SND_NODEFAULT: در نبود دستگاه صدا خطای سیستمی ندهد
            winsound.PlaySound(
                path, winsound.SND_FILENAME | winsound.SND_ASYNC
                | winsound.SND_NODEFAULT)
            return True
        if sys.platform == "darwin":
            if shutil.which("afplay"):
                subprocess.Popen(["afplay", path],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL)
                return True
            return False
        for player, args in (("paplay", []), ("aplay", ["-q"]),
                             ("ffplay", ["-nodisp", "-autoexit", "-loglevel",
                                         "quiet"])):
            exe = shutil.which(player)
            if exe:
                subprocess.Popen([exe] + args + [path],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL)
                return True
    except Exception:
        return False
    return False


def stop_music() -> None:
    """توقف پخش (اگر پخش‌کننده سیستمی در حال کار باشد)."""
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


def _debug_env() -> str:
    from . import branding
    return branding.env_first("SETARGAN_NO_SOUND", "SWIM_NO_SOUND")
