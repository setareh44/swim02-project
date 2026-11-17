# -*- coding: utf-8 -*-
"""Audio service tests: WAV synthesis + safe no-op behaviour (no Qt)."""
from __future__ import annotations

import os
import wave

from app.audio import AudioService, ClickSoundFilter, ensure_beep


def test_beep_wav_is_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    path = ensure_beep("click", 880.0, 45, 0.4)
    assert os.path.isfile(path)
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 22050
        assert w.getnframes() > 100
    # second call reuses the cache
    assert ensure_beep("click", 880.0, 45, 0.4) == path


def test_service_is_silent_safe_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SETARGAN_NO_SOUND", "1")
    svc = AudioService()
    assert svc.play_click() is False
    assert svc.play_success() is False
    assert svc.play_error() is False
    assert svc.speak("hello", block=True) is False
    assert svc.speak("") is False


def test_speak_never_raises_without_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("SETARGAN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SETARGAN_NO_SOUND", raising=False)
    svc = AudioService()
    # must not raise even when no player / TTS engine exists
    assert svc.speak("salam", block=True) in (True, False)


def test_click_filter_without_qt_returns_false():
    import sys
    # ClickSoundFilter must degrade gracefully when PySide6 is missing
    if "PySide6" in sys.modules:
        import pytest
        pytest.skip("Qt present; filter would install for real")
    assert ClickSoundFilter().install(object()) is False
