# -*- coding: utf-8 -*-
"""تست فایل صوتی شروع برنامه و انتخاب مسیر پخش."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from app import sound

ASSET = Path(__file__).resolve().parents[1] / "app" / "assets" / "startup.wav"


def test_asset_exists_and_is_valid_wav():
    assert ASSET.is_file(), "app/assets/startup.wav is missing"
    with wave.open(str(ASSET), "rb") as f:
        assert f.getnchannels() == 1
        assert f.getsampwidth() == 2
        rate = f.getframerate()
        frames = f.getnframes()
    assert rate in (16000, 22050, 32000, 44100)
    duration = frames / rate
    assert 1.0 <= duration <= 5.0, duration                     # کوتاه
    assert ASSET.stat().st_size < 400_000, "صدا نباید حجم نصب را زیاد کند"


def test_audio_content_is_sane():
    with wave.open(str(ASSET), "rb") as f:
        rate = f.getframerate()
        data = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2")
    x = data.astype(np.float32) / 32768.0
    assert np.max(np.abs(x)) <= 1.0
    assert np.max(np.abs(x)) > 0.5, "صدا بسیار ضعیف است"
    rms = float(np.sqrt(np.mean(x ** 2)))
    assert 0.02 < rms < 0.6, rms
    # ابتدا و انتها نباید کلیک داشته باشند
    assert abs(x[0]) < 0.05 and abs(x[-1]) < 0.05
    # انرژی در میانه هم وجود دارد (سکوت نیم‌ثانیه‌ای در وسط نباشد)
    mid = x[len(x) // 2 - 1000: len(x) // 2 + 1000]
    assert float(np.max(np.abs(mid))) > 0.05
    assert rate > 0


def test_asset_path_finds_bundled_file():
    path = sound.asset_path("startup.wav")
    assert path and Path(path).is_file()
    assert sound.startup_sound_available()
    assert sound.asset_path("does-not-exist.wav") == ""
