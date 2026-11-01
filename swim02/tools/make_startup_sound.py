# -*- coding: utf-8 -*-
"""ساخت موزیک کوتاه شروع برنامه (تم آب / استخر / شنا).

    python tools/make_startup_sound.py

خروجی: app/assets/startup.wav  (mono, 22050 Hz, 16-bit, ~۲.۵ ثانیه ≈ ۱۱۰ کیلوبایت)

صدا با NumPy ساخته می‌شود (هیچ فایل صوتی بیرونی لازم نیست):
  ۱) حباب‌های آب: سینوس با فرکانس فزاینده و پوش سریع
  ۲) پاشیدن آب: نویز کم‌گذر با پوش کوتاه
  ۳) پد آرام زیر آب: دو نُت با ترمولوی کند
  ۴) سه نُت زنگ (C-E-G) به‌عنوان «شروع»
  ۵) ریورب ساده با کانولوشن FFT
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path

import numpy as np

SR = 22050
DURATION = 2.6
OUT = Path(__file__).resolve().parents[1] / "app" / "assets" / "startup.wav"


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    """پوش حمله/افتادن نمایی."""
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0.0, 1.0)
    d = np.exp(-np.maximum(t - attack, 0.0) / max(decay, 1e-4))
    return a * d


def _bubble(freq0: float, freq1: float, dur: float, amp: float) -> np.ndarray:
    n = int(dur * SR)
    f = np.linspace(freq0, freq1, n)                 # حباب در حال بالا آمدن
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) + 0.35 * np.sin(2 * phase)
    return amp * body * _env(n, 0.004, dur * 0.45)


def _splash(amp: float = 0.16) -> np.ndarray:
    n = int(0.55 * SR)
    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, 1.0, n)
    # کم‌گذر ساده و متغیر: میانگین متحرک
    kernel = np.ones(48) / 48.0
    smooth = np.convolve(noise, kernel, mode="same")
    t = np.arange(n) / SR
    env = np.exp(-t / 0.14) * np.clip(t / 0.01, 0, 1)
    return amp * smooth * env * 6.0


def _note(freq: float, dur: float, amp: float, start: float,
          total: int) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = (np.sin(2 * np.pi * freq * t)
            + 0.30 * np.sin(2 * np.pi * 2 * freq * t)
            + 0.12 * np.sin(2 * np.pi * 3 * freq * t))
    tone = amp * body * _env(n, 0.012, dur * 0.42)
    out = np.zeros(total)
    i = int(start * SR)
    j = min(total, i + n)
    out[i:j] = tone[:j - i]
    return out


def _pad(total: int) -> np.ndarray:
    t = np.arange(total) / SR
    trem = 0.5 + 0.5 * np.sin(2 * np.pi * 0.9 * t)          # موج آرام آب
    body = (np.sin(2 * np.pi * 196.00 * t)                  # G3
            + 0.7 * np.sin(2 * np.pi * 293.66 * t)          # D4
            + 0.25 * np.sin(2 * np.pi * 392.00 * t))        # G4
    env = np.clip(t / 0.45, 0, 1) * np.clip((DURATION - t) / 1.1, 0, 1)
    return 0.055 * body * env * (0.75 + 0.25 * trem)


def _reverb(x: np.ndarray, mix: float = 0.28) -> np.ndarray:
    rng = np.random.default_rng(11)
    ir_len = int(0.55 * SR)
    t = np.arange(ir_len) / SR
    ir = rng.normal(0, 1, ir_len) * np.exp(-t / 0.16)
    ir[0] = 1.0
    ir /= np.max(np.abs(ir))
    n = len(x) + ir_len - 1
    size = 1 << (n - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    wet /= max(np.max(np.abs(wet)), 1e-9)
    return (1 - mix) * x + mix * wet * np.max(np.abs(x))


def build() -> np.ndarray:
    total = int(DURATION * SR)
    out = np.zeros(total)

    out += _pad(total)

    # پاشیدن آب در ابتدا
    sp = _splash()
    out[:len(sp)] += sp

    # حباب‌ها
    rng = np.random.default_rng(3)
    for _ in range(11):
        start = rng.uniform(0.10, 2.05)
        dur = rng.uniform(0.05, 0.13)
        f0 = rng.uniform(520, 780)
        f1 = f0 * rng.uniform(1.5, 2.3)
        b = _bubble(f0, f1, dur, rng.uniform(0.05, 0.10))
        i = int(start * SR)
        j = min(total, i + len(b))
        out[i:j] += b[:j - i]

    # سه نُت «شروع» (C5 - E5 - G5)
    out += _note(523.25, 0.95, 0.20, 0.50, total)
    out += _note(659.25, 0.95, 0.17, 0.68, total)
    out += _note(783.99, 1.20, 0.15, 0.86, total)

    out = _reverb(out)

    # حذف کلیک ابتدا/انتها و نرمال‌سازی
    fade = int(0.02 * SR)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    peak = float(np.max(np.abs(out)))
    if peak > 0:
        out = out / peak * 0.82
    return out


def save(samples: np.ndarray, path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(samples, -1.0, 1.0)
    data = (pcm * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(data)
    return path


if __name__ == "__main__":
    p = save(build())
    n = len(build())
    print("wrote %s  (%.2f s, %d samples, %.0f KB)"
          % (p, n / SR, n, p.stat().st_size / 1024))
    # چند عدد برای اطمینان از سالم بودن صدا
    x = build()
    print("peak %.3f  rms %.3f" % (float(np.max(np.abs(x))),
                                   float(np.sqrt(np.mean(x ** 2)))))
    del struct
