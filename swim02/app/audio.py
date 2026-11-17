# -*- coding: utf-8 -*-
"""Interactive audio feedback for Setargan-Darya (Qt-optional).

* Every button / nav click plays a short synthesized beep (no audio assets
  needed - the WAV files are generated with the standard library on first
  use and cached under <data_dir>/sounds).
* ``AudioService.speak()`` reads a text aloud with the OS speech engine when
  one is available (Windows SAPI via PowerShell, macOS ``say``, Linux
  ``espeak-ng`` / ``espeak`` / ``spd-say``). Always best-effort, threaded and
  non-blocking; failures are silent.

Qt integration: :class:`ClickSoundFilter` is a global event filter -
installed once on the QApplication - that plays the click sound for every
``QAbstractButton`` release (plus the custom sidebar ``NavItem`` frames).

The module imports without Qt so tests and CLI tools can use the WAV
synthesis and the service logic headlessly.
"""
from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import threading
import wave

from . import branding
from .auth import data_dir

SOUNDS_DIR = "sounds"
_SAMPLE_RATE = 22050

CLICK_PREF_KEY = "ui/click_sound"


# ---------------------------------------------------------------------------
# WAV synthesis (stdlib only)
# ---------------------------------------------------------------------------
def _tone_samples(freq_hz: float, ms: int, volume: float,
                  sample_rate: int = _SAMPLE_RATE,
                  freq_end: float | None = None) -> bytes:
    n = max(1, int(sample_rate * ms / 1000))
    out = bytearray()
    fade = max(1, n // 12)   # short fade-in/out kills the click transient
    for i in range(n):
        f = freq_hz if freq_end is None else (
            freq_hz + (freq_end - freq_hz) * i / max(n - 1, 1))
        env = min(i / fade, 1.0, (n - 1 - i) / fade, 1.0)
        v = math.sin(2.0 * math.pi * f * i / sample_rate)
        out += struct.pack("<h", int(32767 * volume * env * v))
    return bytes(out)


def ensure_beep(name: str, freq_hz: float = 880.0, ms: int = 55,
                volume: float = 0.45,
                freq_end: float | None = None) -> str:
    """Generate (once) and return the path of a cached beep WAV file."""
    folder = os.path.join(data_dir(), SOUNDS_DIR)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".wav")
    if os.path.isfile(path) and os.path.getsize(path) > 100:
        return path
    tmp = path + ".tmp"
    try:
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_SAMPLE_RATE)
            w.writeframes(_tone_samples(freq_hz, ms, volume,
                                        freq_end=freq_end))
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return ""
    return path


def _ascii_fold(text: str) -> str:
    return str(text or "").encode("ascii", "replace").decode("ascii")


# ---------------------------------------------------------------------------
# playback backends (all non-blocking, never raise)
# ---------------------------------------------------------------------------
def _play_file(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.PlaySound(
                path, winsound.SND_FILENAME | winsound.SND_ASYNC
                | winsound.SND_NODEFAULT)
            return True
        if sys.platform == "darwin":
            if shutil.which("afplay"):
                subprocess.Popen(
                    ["afplay", path], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                return True
            return False
        for player, args in (("paplay", []), ("aplay", ["-q"]),
                             ("ffplay", ["-nodisp", "-autoexit", "-loglevel",
                                         "quiet"])):
            exe = shutil.which(player)
            if exe:
                subprocess.Popen(
                    [exe] + args + [path], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                return True
    except Exception:
        return False
    return False


def _speak_sync(text: str) -> bool:
    text = str(text or "").strip()
    if not text:
        return False
    try:
        if sys.platform.startswith("win"):
            ps = shutil.which("powershell") or shutil.which("powershell.exe")
            if not ps:
                return False
            safe = text.replace("'", "''")
            cmd = ("Add-Type -AssemblyName System.Speech; "
                   "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                   ".Speak('%s')" % safe)
            subprocess.run([ps, "-NoProfile", "-NonInteractive",
                            "-Command", cmd],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, timeout=60)
            return True
        if sys.platform == "darwin" and shutil.which("say"):
            subprocess.run(["say", text], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, timeout=60)
            return True
        for exe in ("espeak-ng", "espeak", "spd-say"):
            if shutil.which(exe):
                subprocess.run([exe, _ascii_fold(text)],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL, timeout=60)
                return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
class AudioService:
    """Singleton-ish facade for clicks, jingles and speech."""

    _instance: "AudioService | None" = None

    def __new__(cls) -> "AudioService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._click_path = ""
            cls._instance._ok_path = ""
            cls._instance._err_path = ""
        return cls._instance

    # -- preferences ------------------------------------------------------
    @staticmethod
    def _prefs_enabled() -> tuple[bool, bool]:
        """(master_sound, click_sound). Qt-free safe defaults when needed."""
        if branding.sound_disabled():
            return False, False
        master, click = True, True
        try:
            from . import prefs
            master = prefs.get_bool(prefs.KEY_SOUND, True)
            click = prefs.get_bool(CLICK_PREF_KEY, True)
        except Exception:
            pass
        return master, click

    # -- beeps ------------------------------------------------------------
    def _paths(self) -> tuple[str, str, str]:
        if not self._click_path:
            self._click_path = ensure_beep("click", 880.0, 45, 0.40)
            self._ok_path = ensure_beep("success", 660.0, 140, 0.45,
                                        freq_end=990.0)
            self._err_path = ensure_beep("error", 220.0, 160, 0.45,
                                         freq_end=185.0)
        return self._click_path, self._ok_path, self._err_path

    def play_click(self) -> bool:
        master, click = self._prefs_enabled()
        if not (master and click):
            return False
        return _play_file(self._paths()[0])

    def play_success(self) -> bool:
        master, _ = self._prefs_enabled()
        if not master:
            return False
        return _play_file(self._paths()[1])

    def play_error(self) -> bool:
        master, _ = self._prefs_enabled()
        if not master:
            return False
        return _play_file(self._paths()[2])

    # -- speech -----------------------------------------------------------
    def speak(self, text: str, block: bool = False) -> bool:
        """Read ``text`` aloud (best-effort, threaded unless block=True)."""
        master, _ = self._prefs_enabled()
        if not master or not str(text or "").strip():
            return False
        if block:
            return _speak_sync(text)
        thread = threading.Thread(target=_speak_sync, args=(text,),
                                  name="swim-speak", daemon=True)
        thread.start()
        return True


def click() -> bool:
    """Convenience shortcut used by UI code: play the click beep."""
    return AudioService().play_click()


# ---------------------------------------------------------------------------
# Qt: global click-sound event filter
# ---------------------------------------------------------------------------
class ClickSoundFilter:
    """Event filter that beeps on every button/NavItem click.

    Implemented without importing Qt at module level: ``install(app)``
    creates the real QObject filter only when PySide6 is available.
    """

    def __init__(self):
        self._filter = None

    def install(self, app) -> bool:
        try:
            from PySide6.QtCore import QEvent, QObject
            from PySide6.QtWidgets import QAbstractButton, QFrame
        except Exception:
            return False

        service = AudioService()

        class _Filter(QObject):
            def eventFilter(self, obj, event):  # noqa: N802
                try:
                    if (event.type() == QEvent.MouseButtonRelease
                            and event.button() == 1):   # Qt.LeftButton
                        # walk up: clicks may land on child labels inside
                        # a button / NavItem frame rather than the frame itself
                        w = obj
                        for _ in range(8):
                            if w is None:
                                break
                            if isinstance(w, QAbstractButton):
                                if w.isEnabled():
                                    service.play_click()
                                break
                            if (isinstance(w, QFrame)
                                    and w.objectName() == "navItem"
                                    and w.isEnabled()):
                                service.play_click()
                                break
                            w = w.parent()
                except Exception:
                    pass
                return False

        self._filter = _Filter(app)
        app.installEventFilter(self._filter)
        return True
