#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setargan-Darya (ستارگان دریا) - swimming analytics engine
=========================================================
Automated swimming style classification, multi-view pose adaptation and
biomechanical performance analysis (OpenCV + MediaPipe Pose + NumPy).

INSTALL (Windows CMD / Linux / macOS)
    pip install -r requirements.txt

    Python 3.10 - 3.14 is supported through a dual pose backend:
      * mediapipe >= 1.0  -> modern PoseLandmarker Tasks API (Python 3.10-3.14),
        model bundles are read from ./models/*.task (auto-downloaded if missing)
      * mediapipe 0.10.x  -> legacy mp.solutions.pose API (Python 3.10-3.12)
    The backend is selected automatically from the installed mediapipe version.

RUN
    python swim_ai.py video.mp4
    python swim_ai.py video.mp4 -o out.mp4 --json out.json --height 1.80 --pool-length 25
    python swim_ai.py video.mp4 --view side --show

PIPELINE
    1. Pose extraction (CLAHE/gamma lighting normalisation, rotation fallback for
       horizontal swimmers, image + metric 3D world landmarks)
    2. Noise cleaning (visibility gating, bone-length gate, Hampel filter,
       gap interpolation, smoothing) -> robust to ripples / bubbles / glare
    3. Camera-view classification per frame (SIDE / FRONT-BACK / OVERHEAD / OBLIQUE)
    4. View adaptation: planar image coordinates for SIDE view, metric 3D world
       coordinates + body-aligned canonical frame for all other views
    5. Biomechanics (elbow, knee, roll, pitch, hip undulation, arm signals)
    6. Style classification (first N frames + whole video)
    7. Stroke counting, SPM, speed (auto-calibration), SWOLF, efficiency, symmetry
    8. Technique evaluation (GREEN / YELLOW / RED) + HUD video + JSON + CMD report

All terminal output is plain ASCII "Finglish" (no Persian Unicode) so that Windows
consoles never show "???".
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import shutil
import sys
import tempfile
import urllib.request
import warnings
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# ---------------------------------------------------------------------------
# Peak detection (SciPy-compatible subset, implemented with NumPy only)
# ---------------------------------------------------------------------------
# The whole project needs exactly one function from SciPy: find_peaks.  SciPy
# weighs ~140 MB in a virtual environment and ~50 MB in a packaged build, so it
# is not a dependency any more.  The implementation below matches
# ``scipy.signal.find_peaks`` for the two call styles used here (no arguments,
# and ``distance`` + ``prominence``), which keeps the analysis results stable
# and the distribution small.  tests/test_peaks.py cross-checks it against
# SciPy whenever SciPy happens to be installed.
def _peak_prominences(x: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Prominence of every peak in ``idx`` (same definition as SciPy)."""
    n = len(x)
    out = np.zeros(len(idx), dtype=np.float64)
    for k, i in enumerate(idx):
        # walk left until a strictly higher sample, tracking the minimum
        left_min = x[i]
        j = i - 1
        while j >= 0 and x[j] <= x[i]:
            left_min = min(left_min, x[j])
            j -= 1
        if j < 0:
            left_min = min(x[:i + 1])
        # walk right the same way
        right_min = x[i]
        j = i + 1
        while j < n and x[j] <= x[i]:
            right_min = min(right_min, x[j])
            j += 1
        if j >= n:
            right_min = min(x[i:])
        out[k] = x[i] - max(left_min, right_min)
    return out


def find_peaks(x, distance=None, prominence=None, **_ignored):
    """برگرداندن نمایه قله‌های محلی، سازگار با ``scipy.signal.find_peaks``.

    فقط امکاناتی پیاده شده است که در این پروژه استفاده می‌شود (بدون پارامتر،
    و با ``distance`` / ``prominence``). خروجی همان تاپل ``(peaks, {})`` است.
    """
    arr = np.asarray(x, dtype=np.float64).ravel()
    n = arr.size
    if n < 3:
        return np.array([], dtype=np.int64), {}

    # local maxima; a flat top (plateau) counts as one peak reported at its
    # middle sample, exactly like SciPy
    found = []
    i = 1
    while i < n - 1:
        if arr[i] > arr[i - 1]:
            j = i
            while j < n - 1 and arr[j + 1] == arr[j]:
                j += 1
            if j < n - 1 and arr[j] > arr[j + 1]:
                found.append((i + j) // 2)
            i = j + 1
        else:
            i += 1
    idx = np.asarray(found, dtype=np.int64)
    idx = idx[np.isfinite(arr[idx])]
    if idx.size == 0:
        return np.array([], dtype=np.int64), {}

    if prominence is not None:
        prom = _peak_prominences(arr, idx)
        idx = idx[prom >= float(prominence)]
        if idx.size == 0:
            return np.array([], dtype=np.int64), {}

    if distance is not None and int(distance) > 1:
        keep = []
        # tallest first; ties resolved by the earlier sample (as SciPy does)
        for i in sorted(idx, key=lambda j: (-arr[j], j)):
            if all(abs(i - j) >= int(distance) for j in keep):
                keep.append(i)
        idx = np.array(sorted(keep), dtype=np.int64)
    return idx.astype(np.int64), {}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Local joint indices (13 key joints) and their MediaPipe indices
(NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR,
 L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN) = range(13)
MP_INDEX = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
NJ = 13

# BGR colours
GREEN = (0, 255, 0)
YELLOW = (0, 255, 255)
RED = (0, 0, 255)
WHITE = (235, 235, 235)
CYAN = (255, 255, 0)
STATUS_COLORS = {0: WHITE, 1: GREEN, 2: YELLOW, 3: RED}

# Camera views
VIEW_SIDE, VIEW_FRONT, VIEW_OVERHEAD, VIEW_OBLIQUE = 0, 1, 2, 3
VIEW_HUD = {0: "SIDE", 1: "FRONT/BACK", 2: "OVERHEAD", 3: "OBLIQUE"}
VIEW_FINGLISH = {0: "Pahlu (Side)", 1: "Robero/Posh (Front/Back)",
                 2: "Az Bala (Overhead)", 3: "Morib (Oblique)"}
VIEW_ARG = {"side": 0, "front": 1, "overhead": 2, "oblique": 3}

# Styles
STYLE_HUD = {"CRAWL": "FRONT CRAWL", "BACK": "BACKSTROKE",
             "FLY": "BUTTERFLY", "BREAST": "BREASTSTROKE"}
STYLE_FINGLISH = {"CRAWL": "Koral Sine (Front Crawl)", "BACK": "Koral Posht (Backstroke)",
                  "FLY": "Parvaneh (Butterfly)", "BREAST": "Ghorbaghe (Breaststroke)"}
ALTERNATING = {"CRAWL": True, "BACK": True, "FLY": False, "BREAST": False}

# Stroke-cycle phases (per arm, per frame)
PH_UNKNOWN, PH_ENTRY, PH_CATCH, PH_PULL, PH_PUSH, PH_RECOVERY = range(6)
PHASE_HUD = {0: "--", 1: "ENTRY", 2: "CATCH", 3: "PULL", 4: "PUSH", 5: "RECOVERY"}
PHASE_FINGLISH = {0: "namoshakhas", 1: "Vorood (Entry)", 2: "Gereftan (Catch)",
                  3: "Keshesh (Pull)", 4: "Hel Dadan (Push)", 5: "Bazgasht (Recovery)"}

# Anthropometry: segment length as a fraction of body height (Winter, 2009)
ANTHRO = {"torso": 0.288, "upper_arm": 0.186, "forearm": 0.146,
          "thigh": 0.245, "shank": 0.246, "shoulder_width": 0.259}
ANTHRO_SPAN = ANTHRO["torso"] + ANTHRO["thigh"] + ANTHRO["shank"]   # shoulder -> ankle

BONES = [(L_SH, L_EL), (L_EL, L_WR), (R_SH, R_EL), (R_EL, R_WR),
         (L_HIP, L_KN), (L_KN, L_AN), (R_HIP, R_KN), (R_KN, R_AN)]

FONT = cv2.FONT_HERSHEY_SIMPLEX


# ---------------------------------------------------------------------------
# Console (ASCII / Finglish only) and helpers
# ---------------------------------------------------------------------------
class AnalysisCancelled(RuntimeError):
    """Raised when the caller asks the pipeline to stop (GUI cancel button)."""


class Console:
    """Prints strictly ASCII text so Windows CMD never shows question marks."""

    @staticmethod
    def say(msg: str = "") -> None:
        print(str(msg).encode("ascii", "replace").decode("ascii"))
        sys.stdout.flush()

    @staticmethod
    def rule(char: str = "=", width: int = 64) -> None:
        Console.say(char * width)


@contextlib.contextmanager
def quiet():
    """Silence numpy warnings (all-NaN slices, division by zero) inside a block."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with np.errstate(all="ignore"):
            yield


# ---------------------------------------------------------------------------
# Video I/O helpers
# ---------------------------------------------------------------------------
# OpenCV builds for Windows cannot open paths containing non-ASCII characters
# (Persian file names are the norm for this project).  These helpers fall back
# to an ASCII-only temporary copy so that the analysis still runs.
def _is_ascii_path(path: str) -> bool:
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def open_video_reader(path: str):
    """Open ``path`` for reading, even when the path has non-ASCII characters.

    Returns ``(capture, cleanup)``; ``cleanup()`` must be called when the reader
    is no longer needed (it also removes the temporary copy, if one was made).
    Raises ``IOError`` when the file cannot be opened at all.
    """
    cap = cv2.VideoCapture(path)
    if cap.isOpened():
        return cap, (lambda: None)

    if _is_ascii_path(path):
        cap.release()
        raise IOError("Video baz nashod: " + path)

    cap.release()
    tmp_dir = tempfile.mkdtemp(prefix="swim_ai_in_")
    tmp = os.path.join(tmp_dir, "input" + os.path.splitext(path)[1])
    try:
        shutil.copyfile(path, tmp)
    except OSError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise IOError("Video baz nashod: %s (%s)" % (path, exc)) from exc
    Console.say("[i] Non-ASCII path detected: using a temporary copy.")
    cap = cv2.VideoCapture(tmp)
    if not cap.isOpened():
        cap.release()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise IOError("Video baz nashod: " + path)

    def _cleanup() -> None:
        cap.release()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return cap, _cleanup


@contextlib.contextmanager
def open_capture(path: str):
    """Yield an opened ``cv2.VideoCapture`` (handles non-ASCII paths)."""
    cap, cleanup = open_video_reader(path)
    try:
        yield cap
    finally:
        cleanup()


@contextlib.contextmanager
def open_writer(path: str, fps: float, size: Tuple[int, int]):
    """Yield an opened ``cv2.VideoWriter`` and move the result into place.

    The writer itself is created on an ASCII path (Windows limitation) and the
    finished file is moved to ``path`` afterwards, so Persian output names work.
    """
    tmp_dir = None
    target = path
    if not _is_ascii_path(path):
        tmp_dir = tempfile.mkdtemp(prefix="swim_ai_out_")
        target = os.path.join(tmp_dir, "output.mp4")
    writer = cv2.VideoWriter(target, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not writer.isOpened():
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise IOError("Sakht-e video-ye khoroji ghabel-e anjam nist: " + path)
    ok = False
    try:
        yield writer
        ok = True
    finally:
        writer.release()
        if tmp_dir:
            if ok and os.path.isfile(target):
                try:
                    shutil.move(target, path)
                except OSError:
                    shutil.copyfile(target, path)
            shutil.rmtree(tmp_dir, ignore_errors=True)
        elif not ok:
            # keep no half-written video behind (cancelled / failed render)
            with contextlib.suppress(OSError):
                if os.path.isfile(path):
                    os.remove(path)


@dataclass
class Config:
    # --- pose extraction ---
    model_complexity: int = 1
    rotation_fallback: bool = True
    flip_depth: bool = False
    # --- cleaning ---
    min_vis: float = 0.45
    hampel_sec: float = 0.35
    hampel_sigma: float = 3.5
    bone_tol: float = 0.35
    max_gap_sec: float = 0.5
    smooth_sec: float = 0.14
    # --- style classification ---
    classify_frames: int = 45
    # --- calibration / performance ---
    swimmer_height_m: float = 1.75
    fov_deg: float = 65.0
    meters_per_pixel: Optional[float] = None
    pool_length_m: float = 25.0
    # --- technique thresholds ---
    view_override: Optional[int] = None
    pull_enter: float = 0.15
    elbow_margin: float = 0.05
    straight_warn: float = 150.0
    straight_crit: float = 165.0
    straight_depth: float = 0.35
    pitch_warn: float = 8.0
    pitch_crit: float = 15.0
    hipdev_warn: float = 0.12
    hipdev_crit: float = 0.22
    sym_warn: float = 80.0
    sym_crit: float = 65.0
    min_event_sec: float = 0.20
    flash_period_sec: float = 0.30
    # --- misc ---
    render: bool = True
    show: bool = False
    # Optional predicate polled between frames/stages; returning True aborts the
    # run with AnalysisCancelled (used by the GUI cancel button).
    cancel: Optional[Callable[[], bool]] = None

    def cancelled(self) -> bool:
        if self.cancel is None:
            return False
        try:
            return bool(self.cancel())
        except Exception:  # noqa: BLE001 - a broken predicate must not abort analysis
            return False

    def checkpoint(self) -> None:
        """Raise AnalysisCancelled if the caller requested a stop."""
        if self.cancelled():
            raise AnalysisCancelled("Tahlil tavasot-e karbar motevaghaf shod.")


# ---------------------------------------------------------------------------
# Signal and geometry tools
# ---------------------------------------------------------------------------
class SignalTools:
    @staticmethod
    def odd(n: float) -> int:
        n = max(3, int(round(n)))
        return n if n % 2 == 1 else n + 1

    @staticmethod
    def fill_gaps(x: np.ndarray, max_gap: int) -> np.ndarray:
        """Linear interpolation of NaN gaps no longer than max_gap frames."""
        x = np.asarray(x, dtype=np.float64).copy()
        valid = np.flatnonzero(~np.isnan(x))
        if valid.size < 2:
            return x
        filled = np.interp(np.arange(len(x)), valid, x[valid])
        for g in np.flatnonzero(np.diff(valid) > 1):
            i, j = valid[g], valid[g + 1]
            if j - i - 1 > max_gap:
                filled[i + 1:j] = np.nan
        filled[:valid[0]] = np.nan
        filled[valid[-1] + 1:] = np.nan
        return filled

    @staticmethod
    def smooth(x: np.ndarray, win: int) -> np.ndarray:
        """NaN-aware moving average (NaN positions stay NaN).

        Uses edge padding: with zero padding the first/last half window is pulled
        towards zero, which shortens the travelled trajectory and under-estimates
        speed at the beginning and the end of the clip.
        """
        x = np.asarray(x, dtype=np.float64)
        win = min(win, len(x))
        if win % 2 == 0:
            win -= 1
        if win < 3:
            return x.copy()
        nanm = np.isnan(x)
        k = np.ones(win)
        pad = min(win // 2, max(0, len(x) - 1))
        xv = np.where(nanm, 0.0, x)
        valid = np.flatnonzero(~nanm)
        # Pad by *linear extrapolation* of the edge trend.  Padding with zeros
        # (or repeating the edge value) bends the first/last half window towards
        # a constant, which shortens the travelled trajectory of a clip and
        # under-estimates its speed.
        if valid.size >= 3 and pad:
            q = max(2, min(pad, valid.size // 4 + 1))
            slope_l = float(np.median(np.diff(x[valid[:q]])))
            slope_r = float(np.median(np.diff(x[valid[-q:]])))
            left = x[valid[0]] - slope_l * np.arange(pad, 0, -1)
            right = x[valid[-1]] + slope_r * np.arange(1, pad + 1)
        elif valid.size:
            left = np.full(pad, x[valid[0]])
            right = np.full(pad, x[valid[-1]])
        else:
            left = right = np.zeros(pad)
        xp = np.concatenate([left, xv, right])
        mp = np.concatenate([np.ones(pad), (~nanm).astype(float), np.ones(pad)])
        num = np.convolve(xp, k, mode="valid")
        den = np.convolve(mp, k, mode="valid")
        out = num / np.maximum(den, 1e-9)
        out[nanm] = np.nan
        return out

    @staticmethod
    def median_nan(x: np.ndarray, win: int) -> np.ndarray:
        """Rolling NaN-aware median (also fills isolated NaNs)."""
        x = np.asarray(x, dtype=np.float64)
        n = len(x)
        win = min(win, n if n % 2 == 1 else n - 1)
        if win < 3:
            return x.copy()
        half = win // 2
        pad = np.pad(x, (half, half), mode="edge")
        with quiet():
            return np.nanmedian(sliding_window_view(pad, win), axis=1)

    @staticmethod
    def hampel(a: np.ndarray, win: int, sigma: float) -> np.ndarray:
        """Hampel outlier filter on (N, M) array; outliers become NaN."""
        a = np.asarray(a, dtype=np.float64)
        n, m = a.shape
        win = min(win, n if n % 2 == 1 else n - 1)
        if win < 5:
            return a.copy()
        half = win // 2
        out = a.copy()
        with quiet():
            floor = 0.01 * np.nanstd(a, axis=0)
            for c0 in range(0, m, 6):
                blk = a[:, c0:c0 + 6]
                pad = np.pad(blk, ((half, half), (0, 0)), mode="edge")
                w = sliding_window_view(pad, win, axis=0)          # (n, k, win)
                med = np.nanmedian(w, axis=2)
                mad = 1.4826 * np.nanmedian(np.abs(w - med[:, :, None]), axis=2)
                thr = sigma * np.maximum(mad, floor[c0:c0 + 6])
                bad = np.abs(blk - med) > thr
                block_out = out[:, c0:c0 + 6]        # view -> writes through
                block_out[bad] = np.nan
        return out

    @staticmethod
    def autocorr_period(x: np.ndarray, fps: float, fmin: float = 0.2,
                        fmax: float = 2.0) -> Tuple[float, float]:
        """Dominant frequency (Hz) and periodicity quality (0..1) via autocorrelation."""
        x = np.asarray(x, dtype=np.float64)
        n = len(x)
        ok = ~np.isnan(x)
        if n < 12 or ok.mean() < 0.5:
            return float("nan"), 0.0
        xv = x.copy()
        m = np.mean(xv[ok])
        xv[~ok] = m
        xv = xv - m
        t = np.arange(n)
        xv = xv - np.polyval(np.polyfit(t, xv, 1), t)
        f = np.fft.rfft(xv, 2 * n)
        ac = np.fft.irfft(f * np.conj(f))[:n]
        ac = ac / np.maximum(n - np.arange(n), 1)
        if ac[0] <= 1e-12:
            return float("nan"), 0.0
        ac = ac / ac[0]
        lag_min = max(2, int(fps / fmax))
        lag_max = min(int(fps / fmin), n - 2)
        if lag_max <= lag_min + 2:
            return float("nan"), 0.0
        seg = ac[lag_min:lag_max + 1]
        pk, _ = find_peaks(seg)
        if len(pk) == 0:
            return float("nan"), 0.0
        vals = seg[pk]
        cand = pk[vals >= 0.85 * vals.max()][0]
        return fps / (lag_min + cand), float(np.clip(seg[cand], 0.0, 1.0))

    @staticmethod
    def corr(a: np.ndarray, b: np.ndarray) -> float:
        m = ~np.isnan(a) & ~np.isnan(b)
        if m.sum() < 8:
            return float("nan")
        aa, bb = a[m] - a[m].mean(), b[m] - b[m].mean()
        den = math.sqrt(float(np.sum(aa * aa) * np.sum(bb * bb)))
        return float(np.sum(aa * bb) / den) if den > 1e-12 else float("nan")

    @staticmethod
    def ramp(x: float, lo: float, hi: float) -> float:
        if x is None or np.isnan(x):
            return float("nan")
        return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))

    @staticmethod
    def tri(x: float, a: float, b: float, c: float) -> float:
        if x is None or np.isnan(x):
            return float("nan")
        if x <= a or x >= c:
            return 0.0
        return (x - a) / (b - a) if x < b else (c - x) / (c - b)

    @staticmethod
    def run_mask(flag: np.ndarray, min_len: int) -> Tuple[np.ndarray, int]:
        """Mask of runs of True that last >= min_len frames, and number of such runs."""
        n = len(flag)
        mask = np.zeros(n, dtype=bool)
        events, i = 0, 0
        while i < n:
            if flag[i]:
                j = i
                while j < n and flag[j]:
                    j += 1
                if j - i >= min_len:
                    mask[i:j] = True
                    events += 1
                i = j
            else:
                i += 1
        return mask, events


class Geo:
    @staticmethod
    def unit(v: np.ndarray) -> np.ndarray:
        with quiet():
            n = np.linalg.norm(v, axis=-1, keepdims=True)
            return v / np.where(n < 1e-9, np.nan, n)

    @staticmethod
    def dot(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.sum(a * b, axis=-1)

    @staticmethod
    def angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
        """Angle at b (degrees) between b->a and b->c. Works for 2D/3D rows."""
        with quiet():
            v1, v2 = a - b, c - b
            den = np.linalg.norm(v1, axis=-1) * np.linalg.norm(v2, axis=-1)
            cosv = np.clip(np.sum(v1 * v2, axis=-1) / den, -1.0, 1.0)
            return np.degrees(np.arccos(cosv))


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass
class PoseData:
    img: np.ndarray            # (N, NJ, 3) x_px, y_px, visibility
    wld: np.ndarray            # (N, NJ, 3) metric world coords (hip-centred)
    fps: float
    width: int
    height: int
    detect_ratio: float = 0.0
    rotation_rescues: int = 0

    @property
    def n(self) -> int:
        return self.img.shape[0]


@dataclass
class ViewTrack:
    codes: np.ndarray          # (N,) per-frame view code
    conf: np.ndarray           # (N,)
    q: np.ndarray
    ds: np.ndarray
    db: np.ndarray
    up: np.ndarray             # (N, 3) world "up" direction per frame
    dominant: int
    dominant_ratio: float


@dataclass
class Working:
    P: np.ndarray              # (N, NJ, 3) working coordinates (planar px or world m)
    planar: np.ndarray         # (N,) bool
    up: np.ndarray
    mid_sh: np.ndarray
    mid_hip: np.ndarray
    mid_an: np.ndarray
    h: np.ndarray              # head direction (hip -> shoulder)
    l: np.ndarray              # lateral axis (right -> left shoulder), NaN when planar
    d: np.ndarray              # dorsal axis
    torso: np.ndarray


@dataclass
class Biomech:
    elbow: Dict[str, np.ndarray]
    knee: Dict[str, np.ndarray]
    roll: np.ndarray
    pitch: np.ndarray
    hipdev: np.ndarray
    dorsal_up: np.ndarray
    rel_up: Dict[str, np.ndarray]
    rel_long: Dict[str, np.ndarray]
    e_up: Dict[str, np.ndarray]
    sig: Dict[str, List[np.ndarray]]      # arm -> [rel_up, rel_long, rel_lat] signals
    ankle_rel: Dict[str, np.ndarray]


@dataclass
class StyleResult:
    best: str
    second: str
    scores: Dict[str, float]
    shares: Dict[str, float]
    conf: float
    features: Dict[str, float]
    frames: int


@dataclass
class StrokeResult:
    cand_id: int
    primary: str
    quality: Dict[str, float]
    freq_hz: float
    peaks: Dict[str, np.ndarray]
    signals: Dict[str, np.ndarray]
    mult: int
    cycles: int
    total_strokes: int
    spm_avg: float
    spm_inst: np.ndarray
    strokes_so_far: np.ndarray


@dataclass
class SymmetryResult:
    series: np.ndarray
    global_pct: float
    amp: Dict[str, float]
    min_elbow: Dict[str, float]
    note: str


@dataclass
class PerfResult:
    speed: np.ndarray
    stroke_len: np.ndarray
    eff_idx: np.ndarray
    swolf: np.ndarray
    mean_speed: float
    max_speed: float
    distance: float
    swolf_est: float
    eff_mean: float
    sl_mean: float
    lengths: List[Tuple[int, float, int, float]]
    mpp_median: float
    pool_length_m: float = 25.0


@dataclass
class Evaluation:
    status: Dict[str, np.ndarray]
    crit_mask: np.ndarray
    crit_text: List[str]
    events: Dict[str, int]
    red_frames: Dict[str, int]


@dataclass
class PhaseResult:
    codes: Dict[str, np.ndarray]      # arm -> (N,) int8 phase code, see PH_*
    dist: Dict[str, float]            # phase name -> fraction of known frames


@dataclass
class ConfidenceResult:
    conf: np.ndarray                  # (N,) per-frame confidence 0..1
    meas_err_deg: np.ndarray          # (N,) joint-angle error estimate (deg)
    mean_conf: float
    low_ratio: float                  # fraction of frames with conf < 0.5
    high_ratio: float                 # fraction of frames with conf >= 0.8


@dataclass
class Results:
    pose_raw: PoseData
    pose: PoseData
    track: ViewTrack
    work: Working
    bio: Biomech
    style_init: StyleResult
    style_full: StyleResult
    style_final: str
    strokes: StrokeResult
    perf: PerfResult
    sym: SymmetryResult
    evalr: Evaluation
    phases: PhaseResult
    confr: ConfidenceResult
    video_path: str


# ---------------------------------------------------------------------------
# 1. Pose extraction
# ---------------------------------------------------------------------------
# MediaPipe Tasks API model bundles (shipped in ./models, auto-downloaded otherwise)
_TASK_MODEL_NAME = {0: "pose_landmarker_lite.task",
                    1: "pose_landmarker_full.task",
                    2: "pose_landmarker_heavy.task"}
_TASK_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/"
                   "pose_landmarker/pose_landmarker_{name}/float16/latest/{file}")


class PoseExtractor:
    """MediaPipe Pose with lighting normalisation and rotation fallback.

    Two interchangeable backends with identical output (PoseData):
      * legacy  -> mp.solutions.pose      (mediapipe 0.10.x, Python 3.10-3.12)
      * tasks   -> PoseLandmarker Tasks   (mediapipe >= 1.0,  Python 3.10-3.14)
    The backend is auto-detected from the installed mediapipe version.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        self._luts = {}
        for g in (0.7, 1.3):
            self._luts[g] = np.array([((i / 255.0) ** g) * 255 for i in range(256)], np.uint8)
        self._frame_idx = 0
        self._fps = 30.0
        self._last_ts = -1
        try:
            import mediapipe as mp
        except ImportError:
            raise RuntimeError(
                "MediaPipe peyda nashod. Dastoor: pip install -r requirements.txt")
        self._mp = mp
        if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
            self._backend = "legacy"
            self._init_legacy(cfg)
        else:
            self._backend = "tasks"
            self._init_tasks(cfg)

    # ------------------------------------------------------------------
    def _init_legacy(self, cfg: "Config") -> None:
        self._mp_pose = self._mp.solutions.pose
        kw = dict(model_complexity=cfg.model_complexity,
                  min_detection_confidence=0.4)
        self.pose_video = self._mp_pose.Pose(static_image_mode=False,
                                             smooth_landmarks=True,
                                             min_tracking_confidence=0.4, **kw)
        self.pose_static = self._mp_pose.Pose(static_image_mode=True, **kw)
        Console.say("[1/6] Backend: legacy mp.solutions.pose (mediapipe %s)"
                    % getattr(self._mp, "__version__", "?"))

    def _init_tasks(self, cfg: "Config") -> None:
        try:
            from mediapipe.tasks.python import BaseOptions, vision
        except ImportError as exc:
            raise RuntimeError(
                "NasKhe-ye MediaPipe nasb-shode az Tasks API poshtibani nemikonad. "
                "Dastoor: pip install -U mediapipe") from exc
        model_path = self._resolve_task_model(cfg.model_complexity)
        common = dict(
            base_options=BaseOptions(model_asset_path=model_path),
            num_poses=1,
            min_pose_detection_confidence=0.4,
            min_pose_presence_confidence=0.4,
            min_tracking_confidence=0.4)
        try:
            self.landmarker_video = vision.PoseLandmarker.create_from_options(
                vision.PoseLandmarkerOptions(
                    running_mode=vision.RunningMode.VIDEO, **common))
            self.landmarker_image = vision.PoseLandmarker.create_from_options(
                vision.PoseLandmarkerOptions(
                    running_mode=vision.RunningMode.IMAGE, **common))
        except OSError as exc:
            # MediaPipe >= 1.0 links against EGL even for CPU inference, so a
            # headless Linux box without the GL/EGL runtime fails here with a
            # bare "libEGL.so.1" message.  Explain how to fix it.
            raise RuntimeError(
                "MediaPipe sakhte nashod (%s).\n"
                "  Linux: sudo apt-get install -y libegl1 libgl1 libglib2.0-0\n"
                "  Windows: Visual C++ Redistributable 2015-2022 ra nasb konid.\n"
                "  Ya az mediapipe 0.10.x estefade konid (backend-e legacy)."
                % exc) from exc
        Console.say("[1/6] Backend: MediaPipe Tasks API | model: "
                    + os.path.basename(model_path))

    @staticmethod
    def _resolve_task_model(complexity: int) -> str:
        name = "heavy" if complexity == 2 else ("lite" if complexity == 0 else "full")
        fname = _TASK_MODEL_NAME.get(complexity, _TASK_MODEL_NAME[1])
        root = os.path.dirname(os.path.abspath(__file__))
        env_path = (os.environ.get("SETARGAN_POSE_MODEL")
                    or os.environ.get("SWIM_POSE_MODEL"))
        candidates = []
        if env_path:
            candidates.append(env_path)
        candidates += [os.path.join(root, "models", fname),
                       os.path.join(os.getcwd(), "models", fname)]
        # نصب‌شده در Program Files قابل نوشتن نیست؛ پوشه مدل کاربر را هم بگرد
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(os.path.join(os.environ["LOCALAPPDATA"],
                                           "Setargan-Darya", "models", fname))
            candidates.append(os.path.join(os.environ["LOCALAPPDATA"],
                                           "SWIM-AI", "models", fname))
        for p in candidates:
            if p and os.path.isfile(p):
                return p
        # heavy is optional (30 MB): fall back to the bundled full model
        if name == "heavy":
            full = _TASK_MODEL_NAME[1]
            for p in (os.path.join(root, "models", full),
                      os.path.join(os.getcwd(), "models", full)):
                if os.path.isfile(p):
                    Console.say("[1/6] Model-e heavy mojood nist; full estefade mishavad.")
                    return p
        # best-effort official download (works on normal internet connections)
        url = _TASK_MODEL_URL.format(name=name, file=fname)
        dst = os.path.join(root, "models", fname)
        if not os.access(os.path.dirname(dst) or ".", os.W_OK):
            # e.g. installed under C:\Program Files
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            dst = os.path.join(base, "Setargan-Darya", "models", fname)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            Console.say("[1/6] Daryaft-e model-e PoseLandmarker az internet...")
            urllib.request.urlretrieve(url, dst)
            return dst
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Model-e %s peyda nashod va download ham movaffagh nabood (%s). "
                "An ra dakhel-e pooshe-ye models/ qarar dahid ya az %s begirid."
                % (fname, exc, url))

    # ------------------------------------------------------------------
    def _enhance(self, frame: np.ndarray) -> np.ndarray:
        """CLAHE + adaptive gamma on the L channel (glare, shadows, dim pools)."""
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        mean_l = float(l.mean())
        l = self.clahe.apply(l)
        if mean_l < 70:
            l = cv2.LUT(l, self._luts[0.7])
        elif mean_l > 190:
            l = cv2.LUT(l, self._luts[1.3])
        return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    def _unrotate(self, x: float, y: float, rot: Optional[str]):
        if rot == "cw":          # undo ROTATE_90_CLOCKWISE
            return y, 1.0 - x
        if rot == "ccw":         # undo ROTATE_90_COUNTERCLOCKWISE
            return 1.0 - y, x
        return x, y

    def _pack_legacy(self, res, w: int, h: int, rot: Optional[str]):
        if res.pose_landmarks is None:
            return None
        img = np.full((NJ, 3), np.nan, np.float32)
        wld = np.full((NJ, 3), np.nan, np.float32)
        for k, idx in enumerate(MP_INDEX):
            lm = res.pose_landmarks.landmark[idx]
            x, y = self._unrotate(lm.x, lm.y, rot)
            img[k] = (x * w, y * h, lm.visibility)
        if res.pose_world_landmarks is not None:
            for k, idx in enumerate(MP_INDEX):
                lm = res.pose_world_landmarks.landmark[idx]
                wx, wy, wz = lm.x, lm.y, lm.z
                if rot == "cw":
                    wx, wy = wy, -wx
                elif rot == "ccw":
                    wx, wy = -wy, wx
                if self.cfg.flip_depth:
                    wz = -wz
                wld[k] = (wx, wy, wz)
        return img, wld

    def _pack_tasks(self, result, w: int, h: int, rot: Optional[str]):
        if not result.pose_landmarks:
            return None
        pl = result.pose_landmarks[0]
        wl = (result.pose_world_landmarks[0]
              if result.pose_world_landmarks else None)
        img = np.full((NJ, 3), np.nan, np.float32)
        wld = np.full((NJ, 3), np.nan, np.float32)
        for k, idx in enumerate(MP_INDEX):
            lm = pl[idx]
            x, y = self._unrotate(lm.x, lm.y, rot)
            img[k] = (x * w, y * h, lm.visibility)
            if wl is not None:
                wlm = wl[idx]
                wx, wy, wz = wlm.x, wlm.y, wlm.z
                if rot == "cw":
                    wx, wy = wy, -wx
                elif rot == "ccw":
                    wx, wy = -wy, wx
                if self.cfg.flip_depth:
                    wz = -wz
                wld[k] = (wx, wy, wz)
        return img, wld

    def _process_legacy(self, enh: np.ndarray, w: int, h: int):
        res = self.pose_video.process(cv2.cvtColor(enh, cv2.COLOR_BGR2RGB))
        out = self._pack_legacy(res, w, h, None)
        if out is not None:
            return out, False
        if self.cfg.rotation_fallback:
            for rot, code in (("cw", cv2.ROTATE_90_CLOCKWISE),
                              ("ccw", cv2.ROTATE_90_COUNTERCLOCKWISE)):
                r = self.pose_static.process(
                    cv2.cvtColor(cv2.rotate(enh, code), cv2.COLOR_BGR2RGB))
                out = self._pack_legacy(r, w, h, rot)
                if out is not None:
                    return out, True
        return None, False

    def _process_tasks(self, enh: np.ndarray, w: int, h: int):
        rgb = cv2.cvtColor(enh, cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        # VIDEO mode needs strictly monotonically increasing timestamps (ms)
        ts = max(self._last_ts + 1,
                 int(round(self._frame_idx * 1000.0 / max(self._fps, 1e-6))))
        self._last_ts = ts
        result = self.landmarker_video.detect_for_video(mp_img, ts)
        out = self._pack_tasks(result, w, h, None)
        if out is not None:
            return out, False
        if self.cfg.rotation_fallback:
            for rot, code in (("cw", cv2.ROTATE_90_CLOCKWISE),
                              ("ccw", cv2.ROTATE_90_COUNTERCLOCKWISE)):
                rrgb = cv2.cvtColor(cv2.rotate(enh, code), cv2.COLOR_BGR2RGB)
                rimg = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                                      data=rrgb)
                r = self.landmarker_image.detect(rimg)
                out = self._pack_tasks(r, w, h, rot)
                if out is not None:
                    return out, True
        return None, False

    def _process(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        enh = self._enhance(frame)
        if self._backend == "legacy":
            return self._process_legacy(enh, w, h)
        return self._process_tasks(enh, w, h)

    def _close_backend(self) -> None:
        """Release MediaPipe graphs (safe to call twice / after a failure)."""
        with contextlib.suppress(Exception):
            if self._backend == "legacy":
                self.pose_video.close()
                self.pose_static.close()
            else:
                self.landmarker_video.close()
                self.landmarker_image.close()

    def extract(self, path: str, on_progress=None,
                max_frames: int | None = None) -> PoseData:
        """استخراج اسکلت از ویدیو.

        max_frames: فقط برای عیب‌یابی (tools/diagnose_engine.py) — تعداد
        فریم‌های پردازش‌شده را محدود می‌کند. None یعنی کل ویدیو.
        """
        with open_capture(path) as cap:
            fps = cap.get(cv2.CAP_PROP_FPS)
            if not fps or math.isnan(fps) or fps <= 0:
                fps = 30.0
            self._fps = float(fps)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            imgs, wlds, rescues, found = [], [], 0, 0
            nxt = 10
            self._frame_idx = 0
            self._last_ts = -1
            try:
                while True:
                    # cooperative cancellation (GUI "stop" button)
                    if self._frame_idx % 8 == 0:
                        self.cfg.checkpoint()
                    ok, frame = cap.read()
                    if not ok:
                        break
                    out, rescued = self._process(frame)
                    self._frame_idx += 1
                    if max_frames and len(imgs) >= int(max_frames):
                        break
                    if out is None:
                        imgs.append(np.full((NJ, 3), np.nan, np.float32))
                        wlds.append(np.full((NJ, 3), np.nan, np.float32))
                    else:
                        imgs.append(out[0])
                        wlds.append(out[1])
                        found += 1
                        rescues += int(rescued)
                    if on_progress is not None:
                        on_progress(len(imgs), total)
                    if total > 0:
                        pct = len(imgs) * 100 // total
                        if pct >= nxt:
                            Console.say("[1/6] Estekhraj-e Eskelet (Pose): %d%%" % pct)
                            nxt += 10
            finally:
                self._close_backend()
        if not imgs:
            raise IOError("Hich frami az video khande nashod.")
        return PoseData(np.stack(imgs), np.stack(wlds), float(fps), width, height,
                        found / len(imgs), rescues)


# ---------------------------------------------------------------------------
# 2. Noise cleaning
# ---------------------------------------------------------------------------
class LandmarkCleaner:
    """Visibility gate -> bone-length gate -> Hampel -> gap fill -> smoothing."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def clean(self, pose: PoseData) -> PoseData:
        cfg, fps, n = self.cfg, pose.fps, pose.n
        img, wld = pose.img.copy(), pose.wld.copy()

        low = ~(img[:, :, 2] >= cfg.min_vis)          # NaN visibility counts as low
        img[low, 0:2] = np.nan
        wld[low, :] = np.nan

        # bone-length consistency gate (world coordinates have constant bone length)
        with quiet():
            for a, b in BONES:
                length = np.linalg.norm(wld[:, a, :] - wld[:, b, :], axis=1)
                med = np.nanmedian(length)
                if np.isnan(med) or med <= 0:
                    continue
                bad = np.abs(length - med) > cfg.bone_tol * med
                wld[bad, b, :] = np.nan
                img[bad, b, 0:2] = np.nan

        win_h = SignalTools.odd(fps * cfg.hampel_sec)
        max_gap = max(1, int(cfg.max_gap_sec * fps))
        win_s = SignalTools.odd(fps * cfg.smooth_sec)

        def process(flat: np.ndarray) -> np.ndarray:
            flat = SignalTools.hampel(flat, win_h, cfg.hampel_sigma)
            for c in range(flat.shape[1]):
                flat[:, c] = SignalTools.smooth(SignalTools.fill_gaps(flat[:, c], max_gap), win_s)
            return flat

        img[:, :, 0:2] = process(img[:, :, 0:2].reshape(n, -1)).reshape(n, NJ, 2)
        wld = process(wld.reshape(n, -1)).reshape(n, NJ, 3)
        return PoseData(img, wld.astype(np.float32), fps, pose.width, pose.height,
                        pose.detect_ratio, pose.rotation_rescues)


# ---------------------------------------------------------------------------
# 3. Camera view classification
# ---------------------------------------------------------------------------
class ViewClassifier:
    """
    Estimates the camera orientation relative to the swimmer for every frame.

    Features
      q  = 2D shoulder width / 2D body length (shoulder->ankle). For a horizontal swimmer:
           SIDE ~ 0, OBLIQUE/OVERHEAD ~ 0.33, FRONT/BACK (head-on, foreshortened) >> 0.5.
      ds = |depth component| of the 3D shoulder axis (1 = pointing at camera, i.e. side view).
      db = |depth component| of the 3D body axis   (1 = swimming towards/away from camera).
    """
    Q_SIDE, Q_FRONT, DS_OVER, DB_FRONT = 0.12, 0.60, 0.35, 0.80

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def classify(self, pose: PoseData) -> ViewTrack:
        n, fps = pose.n, pose.fps
        img, wld = pose.img[:, :, :2], pose.wld.astype(np.float64)
        with quiet():
            mid_sh = (img[:, L_SH] + img[:, R_SH]) / 2
            mid_hip = (img[:, L_HIP] + img[:, R_HIP]) / 2
            mid_an = np.nanmean(np.stack([img[:, L_AN], img[:, R_AN]]), axis=0)
            w2 = np.linalg.norm(img[:, L_SH] - img[:, R_SH], axis=1)
            t2 = np.linalg.norm(mid_sh - mid_hip, axis=1)
            span2 = np.linalg.norm(mid_sh - mid_an, axis=1)
            body = np.where(np.isnan(span2), t2 * (ANTHRO_SPAN / ANTHRO["torso"]), span2)
            q = w2 / body
            sw = Geo.unit(wld[:, L_SH] - wld[:, R_SH])
            bw = Geo.unit((wld[:, L_SH] + wld[:, R_SH]) / 2 - (wld[:, L_HIP] + wld[:, R_HIP]) / 2)
            ds, db = np.abs(sw[:, 2]), np.abs(bw[:, 2])

        win = SignalTools.odd(fps * 1.0)
        q_s = SignalTools.median_nan(q, win)
        ds_s = SignalTools.median_nan(ds, win)
        db_s = SignalTools.median_nan(db, win)

        codes = np.full(n, -1, dtype=int)
        conf = np.zeros(n)
        with quiet():
            valid = ~np.isnan(q_s)
            front = valid & ((q_s >= self.Q_FRONT) | ((db_s >= self.DB_FRONT) & (q_s >= 0.30)))
            side = valid & ~front & (q_s < self.Q_SIDE)
            over = valid & ~front & ~side & (ds_s < self.DS_OVER)
            obl = valid & ~front & ~side & ~over
            codes[front], codes[side], codes[over], codes[obl] = VIEW_FRONT, VIEW_SIDE, VIEW_OVERHEAD, VIEW_OBLIQUE
            conf[side] = 0.5 + 0.5 * np.clip((self.Q_SIDE - q_s[side]) / self.Q_SIDE, 0, 1)
            conf[front] = 0.5 + 0.5 * np.clip((q_s[front] - self.Q_FRONT) / 0.4, 0, 1)
            conf[over] = 0.5 + 0.5 * np.clip((self.DS_OVER - ds_s[over]) / self.DS_OVER, 0, 1)
            conf[obl] = 0.5 + 0.5 * np.clip(np.nan_to_num((ds_s[obl] - self.DS_OVER) / 0.65, nan=0.3), 0, 1)

        # majority vote over +-1 s -> stable view labels
        onehot = np.zeros((n, 4))
        for c in range(4):
            onehot[codes == c, c] = 1.0
        cs = np.vstack([np.zeros((1, 4)), np.cumsum(onehot, axis=0)])
        half = int(fps)
        lo = np.clip(np.arange(n) - half, 0, n)
        hi = np.clip(np.arange(n) + half + 1, 0, n)
        votes = cs[hi] - cs[lo]
        smooth_codes = votes.argmax(axis=1)
        smooth_codes[votes.sum(axis=1) == 0] = -1

        totals = onehot.sum(axis=0)
        dominant = int(totals.argmax()) if totals.sum() > 0 else VIEW_SIDE
        ratio = float(totals.max() / totals.sum()) if totals.sum() > 0 else 0.0
        smooth_codes[smooth_codes < 0] = dominant

        # frames without a valid per-frame decision have no confidence of their
        # own; label them with the clip-wide median instead of a misleading 0 %.
        missing = ~np.isfinite(conf) | (conf <= 0.0)
        if missing.any():
            fallback = float(np.median(conf[~missing])) if (~missing).any() else 0.5
            conf[missing] = fallback

        if self.cfg.view_override is not None:
            smooth_codes[:] = self.cfg.view_override
            dominant, ratio = self.cfg.view_override, 1.0
            conf[:] = 1.0

        up = np.zeros((n, 3))
        up[:, 1] = -1.0                         # image "up" (y axis points down)
        up[smooth_codes == VIEW_OVERHEAD] = (0.0, 0.0, -1.0)   # towards the camera
        return ViewTrack(smooth_codes, conf, q_s, ds_s, db_s, up, dominant, ratio)


# ---------------------------------------------------------------------------
# 4. View adaptation (perspective handling / canonical body frame)
# ---------------------------------------------------------------------------
class ViewAdapter:
    """
    SIDE view      -> planar image coordinates (arms move in the image plane).
    Other views    -> metric 3D world landmarks, which are rotation-invariant, so joint
                      angles and body-frame projections do not suffer from perspective
                      foreshortening.
    Both cases are expressed in a body-aligned canonical frame:
        h = head direction, l = lateral (right->left shoulder), d = dorsal direction.
    """

    @staticmethod
    def build(pose: PoseData, track: ViewTrack) -> Working:
        n = pose.n
        no_world = np.all(np.isnan(pose.wld[:, :, 0]), axis=1)
        planar = (track.codes == VIEW_SIDE) | no_world
        img3 = np.dstack([pose.img[:, :, 0], pose.img[:, :, 1], np.zeros((n, NJ))]).astype(np.float64)
        P = np.where(planar[:, None, None], img3, pose.wld.astype(np.float64))
        up = track.up
        with quiet():
            mid_sh = (P[:, L_SH] + P[:, R_SH]) / 2
            mid_hip = (P[:, L_HIP] + P[:, R_HIP]) / 2
            mid_an = np.nanmean(np.stack([P[:, L_AN], P[:, R_AN]]), axis=0)
            torso = np.linalg.norm(mid_sh - mid_hip, axis=1)
            h = Geo.unit(mid_sh - mid_hip)
            l_raw = P[:, L_SH] - P[:, R_SH]
            l3 = Geo.unit(l_raw - Geo.dot(l_raw, h)[:, None] * h)
            d3 = Geo.unit(np.cross(h, l3))
            perp = np.stack([-h[:, 1], h[:, 0], np.zeros(n)], axis=1)
            perp = np.where(Geo.dot(perp, up)[:, None] < 0, -perp, perp)
            l = np.where(planar[:, None], np.nan, l3)
            d = np.where(planar[:, None], perp, d3)
        return Working(P, planar, up, mid_sh, mid_hip, mid_an, h, l, d, torso)


# ---------------------------------------------------------------------------
# 5. Biomechanics
# ---------------------------------------------------------------------------
class BiomechanicsEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def compute(self, pose: PoseData, track: ViewTrack, work: Working) -> Biomech:
        P, up, torso, fps = work.P, work.up, work.torso, pose.fps
        over = track.codes == VIEW_OVERHEAD
        sm = SignalTools.odd(fps * 0.2)

        elbow = {"L": Geo.angle(P[:, L_SH], P[:, L_EL], P[:, L_WR]),
                 "R": Geo.angle(P[:, R_SH], P[:, R_EL], P[:, R_WR])}
        knee = {"L": 180.0 - Geo.angle(P[:, L_HIP], P[:, L_KN], P[:, L_AN]),
                "R": 180.0 - Geo.angle(P[:, R_HIP], P[:, R_KN], P[:, R_AN])}

        with quiet():
            # prone / supine from metric world landmarks (handedness): c = l x h is ventral
            w = pose.wld.astype(np.float64)
            wl = Geo.unit(w[:, L_SH] - w[:, R_SH])
            wh = Geo.unit((w[:, L_SH] + w[:, R_SH]) / 2 - (w[:, L_HIP] + w[:, R_HIP]) / 2)
            wl_perp = Geo.unit(wl - Geo.dot(wl, wh)[:, None] * wh)
            dorsal = np.cross(wh, wl_perp)
            dorsal_up = Geo.dot(dorsal, up)
            roll = np.degrees(np.arcsin(np.clip(Geo.dot(wl, up), -1, 1)))
            roll[over] = np.nan

            # body pitch: head-minus-feet vector vs. horizon (positive = legs sinking)
            bvec = np.where(np.isnan(work.mid_an[:, :1]), work.mid_sh - work.mid_hip,
                            work.mid_sh - work.mid_an)
            pitch = np.degrees(np.arcsin(np.clip(Geo.dot(Geo.unit(bvec), up), -1, 1)))
            pitch[over] = np.nan

            # hip deviation from the shoulder-ankle line (negative = hips dropped)
            line = work.mid_an - work.mid_sh
            t = Geo.dot(work.mid_hip - work.mid_sh, line) / np.maximum(Geo.dot(line, line), 1e-12)
            proj = work.mid_sh + t[:, None] * line
            hipdev = Geo.dot(work.mid_hip - proj, up) / torso
            hipdev[over] = np.nan

        rel_up, rel_long, e_up, sig, ankle_rel = {}, {}, {}, {}, {}
        arms = {"L": (L_SH, L_EL, L_WR, L_HIP, L_AN), "R": (R_SH, R_EL, R_WR, R_HIP, R_AN)}
        with quiet():
            for arm, (sh, el, wr, hip, an) in arms.items():
                rel = P[:, wr] - P[:, sh]
                ru = Geo.dot(rel, up) / torso
                rl = Geo.dot(rel, work.h) / torso
                rt = Geo.dot(rel, work.l) / torso
                rel_up[arm], rel_long[arm] = ru, rl
                e_up[arm] = Geo.dot(P[:, el] - P[:, wr], up) / torso
                sig[arm] = [SignalTools.smooth(s, sm) for s in (ru, rl, rt)]
                ankle_rel[arm] = SignalTools.smooth(Geo.dot(P[:, an] - P[:, hip], up) / torso, sm)

        return Biomech(elbow, knee, roll, pitch, hipdev, dorsal_up, rel_up, rel_long, e_up, sig, ankle_rel)


# ---------------------------------------------------------------------------
# 6. Style classification
# ---------------------------------------------------------------------------
class StyleClassifier:
    NAMES = ["CRAWL", "BACK", "FLY", "BREAST"]

    @staticmethod
    def _wavg(items: List[Tuple[float, float]]) -> float:
        num = den = 0.0
        for w, v in items:
            if v is not None and not np.isnan(v):
                num += w * v
                den += w
        return num / den if den > 0 else 0.0

    def classify(self, bio: Biomech, fps: float, a: int, b: int) -> StyleResult:
        sl = slice(a, b)
        n = b - a
        R, T = SignalTools.ramp, SignalTools.tri
        with quiet():
            dorsal_up = float(np.nanmedian(bio.dorsal_up[sl]))

            rhos = [SignalTools.corr(bio.sig["L"][c][sl], bio.sig["R"][c][sl]) for c in (0, 1)]
            rhos = [r for r in rhos if not np.isnan(r)]
            rho_arm = float(np.mean(rhos)) if rhos else float("nan")

            lrho = [SignalTools.corr(bio.knee["L"][sl], bio.knee["R"][sl]),
                    SignalTools.corr(bio.ankle_rel["L"][sl], bio.ankle_rel["R"][sl])]
            lrho = [r for r in lrho if not np.isnan(r)]
            rho_leg = float(np.mean(lrho)) if lrho else float("nan")

            rec = [np.nanpercentile(bio.rel_up[k][sl], 90)
                   if np.any(~np.isnan(bio.rel_up[k][sl])) else np.nan for k in "LR"]
            recov = float(np.nanmax(rec)) if np.any(~np.isnan(rec)) else float("nan")
            kn = np.concatenate([bio.knee["L"][sl], bio.knee["R"][sl]])
            knee_p95 = float(np.nanpercentile(kn, 95)) if np.any(~np.isnan(kn)) else float("nan")
            hd = bio.hipdev[sl]
            undul = float(np.nanpercentile(hd, 95) - np.nanpercentile(hd, 5)) if np.any(~np.isnan(hd)) else float("nan")

            beat = float("nan")
            if n / fps >= 2.5:
                kf = [SignalTools.autocorr_period(bio.ankle_rel[k][sl], fps, 0.8, 5.0) for k in "LR"]
                af = [SignalTools.autocorr_period(bio.sig[k][c][sl], fps, 0.2, 2.0) for k in "LR" for c in (0, 1)]
                kf = max(kf, key=lambda t: t[1])
                af = max(af, key=lambda t: t[1])
                if kf[1] >= 0.2 and af[1] >= 0.2 and not np.isnan(kf[0]) and not np.isnan(af[0]):
                    beat = kf[0] / af[0]

        prone = R(dorsal_up, -0.1, 0.35)
        supine = R(-dorsal_up, -0.1, 0.35)
        sync = R(rho_arm, -0.15, 0.45)
        alt = 1.0 - sync if not np.isnan(sync) else float("nan")
        lsync = R(rho_leg, -0.15, 0.45)
        lalt = 1.0 - lsync if not np.isnan(lsync) else float("nan")
        rec = R(recov, 0.0, 0.35)
        deep = R(knee_p95, 70.0, 110.0)
        und = R(undul, 0.10, 0.35)
        inv = lambda x: (1.0 - x) if not np.isnan(x) else float("nan")
        b_hi, b_fly, b_br = R(beat, 2.3, 3.3), T(beat, 1.4, 2.0, 2.8), T(beat, 0.5, 1.0, 1.6)

        W = self._wavg
        scores = {
            "BACK": W([(0.50, supine), (0.15, alt), (0.05, lalt), (0.15, rec), (0.05, inv(deep)), (0.10, b_hi)]),
            "CRAWL": W([(0.35, prone), (0.25, alt), (0.10, lalt), (0.10, rec), (0.10, inv(deep)),
                        (0.10, inv(und)), (0.10, b_hi)]),
            "FLY": W([(0.25, prone), (0.25, sync), (0.10, lsync), (0.15, rec), (0.15, und),
                      (0.05, inv(deep)), (0.10, b_fly)]),
            "BREAST": W([(0.25, prone), (0.25, sync), (0.10, lsync), (0.15, inv(rec)), (0.15, deep),
                         (0.05, inv(und)), (0.10, b_br)]),
        }
        order = sorted(scores, key=scores.get, reverse=True)
        best, second = order[0], order[1]
        total = sum(scores.values()) + 1e-9
        shares = {k: v / total for k, v in scores.items()}
        margin = (scores[best] - scores[second]) / max(scores[best], 1e-6)
        conf = float(np.clip(0.5 * margin + 0.5 * scores[best], 0.0, 1.0))
        feats = {"dorsal_up": dorsal_up, "arm_corr": rho_arm, "leg_corr": rho_leg,
                 "recovery_height": float(recov), "knee_flex_p95": knee_p95,
                 "undulation": undul, "kick_arm_beat": beat}
        return StyleResult(best, second, scores, shares, conf, feats, n)


# ---------------------------------------------------------------------------
# 7a. Stroke counting
# ---------------------------------------------------------------------------
class StrokeAnalyzer:
    def analyze(self, bio: Biomech, style: str, fps: float, n: int) -> StrokeResult:
        best_cid, best_score, info = 0, -1.0, {}
        for cid in (0, 1, 2):
            q = {arm: SignalTools.autocorr_period(bio.sig[arm][cid], fps, 0.2, 2.0) for arm in "LR"}
            info[cid] = q
            sc = max(q["L"][1], q["R"][1])
            if sc > best_score + 1e-9:
                best_cid, best_score = cid, sc
        q = info[best_cid]
        primary = "L" if q["L"][1] >= q["R"][1] else "R"
        freq = q[primary][0]

        peaks, signals = {}, {}
        for arm in "LR":
            sig = bio.sig[arm][best_cid]
            signals[arm] = sig
            peaks[arm] = self._peaks(sig, fps, q[arm][0]) if q[arm][1] >= 0.15 else np.array([], dtype=int)

        mult = 2 if ALTERNATING[style] else 1
        pk = peaks[primary]
        cycles = len(pk)
        spm_avg = 0.0
        if cycles >= 2:
            # median inter-peak interval is robust against one missed / spurious peak
            interval = float(np.median(np.diff(pk))) / fps
            spm_avg = 60.0 * mult / max(interval, 1e-6)
        elif cycles == 1 and np.isfinite(freq) and freq > 0:
            # a single peak cannot give an interval: use the periodicity estimate
            spm_avg = 60.0 * mult * float(freq)
        elif cycles == 1 and n > 0:
            spm_avg = cycles / (n / fps) * 60.0 * mult

        spm_inst = np.full(n, np.nan)
        for k in range(2, len(pk)):
            lo = max(0, k - 3)
            interval = np.mean(np.diff(pk[lo:k + 1])) / fps
            end = pk[k + 1] if k + 1 < len(pk) else n
            spm_inst[pk[k]:end] = 60.0 * mult / interval
        so_far = (np.searchsorted(pk, np.arange(n), side="right") * mult).astype(float)

        return StrokeResult(best_cid, primary, {a: q[a][1] for a in "LR"}, freq, peaks, signals,
                            mult, cycles, cycles * mult, spm_avg, spm_inst, so_far)

    @staticmethod
    def _peaks(sig: np.ndarray, fps: float, freq: float) -> np.ndarray:
        valid = sig[~np.isnan(sig)]
        if valid.size < fps:
            return np.array([], dtype=int)
        amp = np.percentile(valid, 95) - np.percentile(valid, 5)
        prom = max(0.35 * amp, 1e-3)
        dist = max(1, int(0.55 / freq * fps)) if not np.isnan(freq) else max(1, int(0.45 * fps))
        filled = np.where(np.isnan(sig), np.median(valid), sig)
        pk, _ = find_peaks(filled, distance=dist, prominence=prom)
        return pk[~np.isnan(sig[pk])]


# ---------------------------------------------------------------------------
# 7b. Speed (auto-calibration), SWOLF, efficiency
# ---------------------------------------------------------------------------
class SpeedEstimator:
    """
    Auto-calibration from standard swimmer proportions.
    Each visible body segment (and the shoulder-to-ankle end-to-end span, i.e. the skeleton
    bounding length) gives a metres-per-pixel estimate  m/px = true_length / pixel_length.
    Foreshortening only makes pixel lengths SHORTER, so the true scale is bounded by the
    smallest estimates -> a low percentile across segments is used. A pinhole model
    (assumed FOV) turns the scale into camera distance Z so that motion along the camera axis
    (front/back views) is also captured. Assumes a static camera.

    The velocity is the component of the displacement that is *perpendicular to gravity*:
    a swimmer bobs up and down around a constant depth, and that oscillation is not forward
    motion. Without this projection a swimmer standing still in the frame (vertical kicking,
    a pause at the wall) is reported with a non-zero speed.
    """

    @staticmethod
    def _weighted_quantile(vals: np.ndarray, weights: np.ndarray, q: float) -> np.ndarray:
        """Column-wise weighted quantile (NaN entries get zero weight)."""
        v = np.asarray(vals, dtype=np.float64)
        w = np.asarray(weights, dtype=np.float64)
        bad = ~np.isfinite(v) | ~np.isfinite(w) | (w <= 0)
        v = np.where(bad, np.inf, v)
        w = np.where(bad, 0.0, w)
        order = np.argsort(v, axis=0)
        vs = np.take_along_axis(v, order, 0)
        ws = np.take_along_axis(w, order, 0)
        cw = np.cumsum(ws, axis=0)
        total = cw[-1]
        pick = np.argmax(cw >= (q * total)[None, :], axis=0)
        out = vs[pick, np.arange(v.shape[1])]
        return np.where(total > 0, out, np.nan)

    def estimate(self, pose: PoseData, cfg: Config,
                 track: Optional[ViewTrack] = None) -> Tuple[np.ndarray, np.ndarray]:
        n, fps, W, H = pose.n, pose.fps, pose.width, pose.height
        img = pose.img[:, :, :2].astype(np.float64)
        Hm = cfg.swimmer_height_m
        segs = [(L_SH, L_EL, ANTHRO["upper_arm"]), (L_EL, L_WR, ANTHRO["forearm"]),
                (R_SH, R_EL, ANTHRO["upper_arm"]), (R_EL, R_WR, ANTHRO["forearm"]),
                (L_HIP, L_KN, ANTHRO["thigh"]), (L_KN, L_AN, ANTHRO["shank"]),
                (R_HIP, R_KN, ANTHRO["thigh"]), (R_KN, R_AN, ANTHRO["shank"])]
        est, plen = [], []
        with quiet():
            for a, b, frac in segs:
                pix = np.linalg.norm(img[:, a] - img[:, b], axis=1)
                pix[pix < 8] = np.nan
                est.append(frac * Hm / pix)
                plen.append(pix)
            mid_sh = (img[:, L_SH] + img[:, R_SH]) / 2
            mid_hip = (img[:, L_HIP] + img[:, R_HIP]) / 2
            mid_an = np.nanmean(np.stack([img[:, L_AN], img[:, R_AN]]), axis=0)
            for p, q_, frac in ((mid_sh, mid_hip, ANTHRO["torso"]), (mid_sh, mid_an, ANTHRO_SPAN)):
                pix = np.linalg.norm(p - q_, axis=1)
                pix[pix < 8] = np.nan
                est.append(frac * Hm / pix)
                plen.append(pix)
            est = np.array(est)
            est[~np.isfinite(est)] = np.nan

            # A low quantile of the per-segment estimates is the natural choice
            # (foreshortening can only inflate m/px), but a 20 px forearm carries
            # several percent of keypoint jitter and drags the quantile down.
            # Weighting each estimate by its pixel length keeps the long, stable
            # segments (torso, shoulder-ankle span) in charge.
            scale = self._weighted_quantile(est, np.array(plen), 0.30)

            scale = SignalTools.median_nan(SignalTools.fill_gaps(scale, int(fps)), SignalTools.odd(fps * 0.5))
            if cfg.meters_per_pixel is not None:
                scale = np.full(n, float(cfg.meters_per_pixel))
            f_px = (W / 2.0) / math.tan(math.radians(cfg.fov_deg / 2.0))
            centre = np.where(np.isnan(mid_hip), mid_sh, mid_hip)
            X = (centre[:, 0] - W / 2.0) * scale
            Y = (centre[:, 1] - H / 2.0) * scale

            # Depth is far more delicate than the image plane: Z = scale * f, so
            # the +-2 % wobble of the limb-based scale (±0.3 m at 15 m) would be
            # mistaken for motion.  Hence a strongly smoothed scale for Z, and a
            # frozen Z in side views, where depth is not observable at all.
            if cfg.meters_per_pixel is not None:
                Z = np.zeros(n)
            else:
                z_scale = SignalTools.median_nan(scale, SignalTools.odd(fps * 1.5))
                z_scale = SignalTools.smooth(
                    SignalTools.fill_gaps(z_scale, int(fps * 2)), SignalTools.odd(fps * 0.6))
                Z = z_scale * f_px
                if track is not None:
                    side = track.codes == VIEW_SIDE
                    if side.any() and np.any(~np.isnan(Z[side])):
                        Z[side] = float(np.nanmedian(Z[side]))
            pos = np.stack([X, Y, Z], axis=1)
            win = SignalTools.odd(fps * 0.3)
            for c in range(3):
                pos[:, c] = SignalTools.smooth(SignalTools.fill_gaps(pos[:, c], int(fps)), win)

            delta = max(1, int(round(0.5 * fps)))
            idx = np.arange(n)
            i0, i1 = np.clip(idx - delta, 0, n - 1), np.clip(idx + delta, 0, n - 1)
            dt = (i1 - i0) / fps
            disp = pos[i1] - pos[i0]

            # remove the gravity-aligned component (vertical bobbing is not travel)
            gvec = np.zeros((n, 3))
            gvec[:, 1] = -1.0                          # image up (y axis points down)
            if track is not None:
                gvec = np.where(np.isfinite(track.up), track.up, gvec)
            gnorm = np.linalg.norm(gvec, axis=1, keepdims=True)
            gvec = gvec / np.where(gnorm < 1e-9, 1.0, gnorm)
            disp = disp - np.sum(disp * gvec, axis=1)[:, None] * gvec

            vel = np.linalg.norm(disp, axis=1) / np.maximum(dt, 1e-6)
            vel[dt <= 0] = np.nan
            speed = SignalTools.median_nan(vel, SignalTools.odd(fps * 0.4))
            speed[speed > 3.5] = np.nan          # physically impossible for swimming
        return speed, scale


class PerformanceMetrics:
    def compute(self, speed: np.ndarray, scale: np.ndarray, strokes: StrokeResult,
                fps: float, cfg: Config) -> PerfResult:
        n = len(speed)
        L = cfg.pool_length_m
        spm = strokes.spm_inst
        with quiet():
            v = np.where(speed > 0.15, speed, np.nan)
            t_len = L / v
            sl = v * 60.0 / spm                               # metres per stroke
            eff = v * sl                                      # Costill stroke index
            swolf = t_len + spm / 60.0 * t_len                # time + strokes for one length

            # average over *all* valid samples: filtering out the near-zero ones
            # (the previous behaviour) turned a stationary swimmer into "no speed"
            # and, worse, averaged only the residual spikes of the noise
            finite = speed[np.isfinite(speed)]
            mean_v = float(finite.mean()) if finite.size else float("nan")
            max_v = float(finite.max()) if finite.size else float("nan")
            dist = float(np.nansum(np.where(np.nan_to_num(speed) > 0.1, speed, 0.0)) / fps)
            spm_avg = strokes.spm_avg
            swolf_est = (L / mean_v) * (1.0 + spm_avg / 60.0) if mean_v and mean_v > 0 else float("nan")
            sl_mean = mean_v * 60.0 / spm_avg if spm_avg > 0 and finite.size else float("nan")
            eff_mean = mean_v * sl_mean if finite.size else float("nan")

            lengths = []
            cum = np.cumsum(np.where(np.isnan(speed) | (speed < 0.1), 0.0, speed)) / fps
            k = 1
            prev_idx = 0
            while cum[-1] >= k * L:
                idx = int(np.searchsorted(cum, k * L))
                t_seg = (idx - prev_idx) / fps
                st_seg = int(round(strokes.strokes_so_far[min(idx, n - 1)] - strokes.strokes_so_far[prev_idx]))
                lengths.append((k, t_seg, st_seg, t_seg + st_seg))
                prev_idx, k = idx, k + 1
        return PerfResult(speed, sl, eff, swolf, mean_v, max_v, dist, swolf_est, eff_mean,
                          sl_mean, lengths,
                          float(np.nanmedian(scale)) if np.any(~np.isnan(scale)) else float("nan"),
                          float(L))


# ---------------------------------------------------------------------------
# 7c. Pull symmetry
# ---------------------------------------------------------------------------
class SymmetryAnalyzer:
    def analyze(self, strokes: StrokeResult, bio: Biomech, fps: float, n: int) -> SymmetryResult:
        ev: Dict[str, list] = {"L": [], "R": []}
        for arm in "LR":
            pk, sig, elb = strokes.peaks[arm], strokes.signals[arm], bio.elbow[arm]
            for a, b in zip(pk[:-1], pk[1:]):
                seg = sig[a:b + 1]
                if np.all(np.isnan(seg)):
                    continue
                with quiet():
                    amp = float(np.nanmax(seg) - np.nanmin(seg))
                    me = float(np.nanmin(elb[a:b + 1])) if np.any(~np.isnan(elb[a:b + 1])) else float("nan")
                ev[arm].append((int(b), amp, me))

        series = np.full(n, np.nan)
        if len(ev["L"]) >= 1 and len(ev["R"]) >= 1:
            ptr, last = {"L": 0, "R": 0}, {"L": None, "R": None}
            for i in range(n):
                for arm in "LR":
                    while ptr[arm] < len(ev[arm]) and ev[arm][ptr[arm]][0] <= i:
                        last[arm] = ev[arm][ptr[arm]]
                        ptr[arm] += 1
                if last["L"] and last["R"] and (i - last["L"][0]) <= 3 * fps and (i - last["R"][0]) <= 3 * fps:
                    series[i] = self._si(last["L"], last["R"])
        with quiet():
            glob = float(np.nanmean(series)) if np.any(~np.isnan(series)) else float("nan")
            amp = {a: float(np.nanmean([e[1] for e in ev[a]])) if ev[a] else float("nan") for a in "LR"}
            mel = {a: float(np.nanmean([e[2] for e in ev[a]])) if ev[a] else float("nan") for a in "LR"}
        note = "OK" if not np.isnan(glob) else "Bazoye dovom be ghadr-e kafi dide nashod (symmetry namojud)"
        return SymmetryResult(series, glob, amp, mel, note)

    @staticmethod
    def _si(a, b) -> float:
        s_amp = 1.0 - abs(a[1] - b[1]) / max((a[1] + b[1]) / 2.0, 1e-6)
        s_amp = float(np.clip(s_amp, 0, 1))
        if np.isnan(a[2]) or np.isnan(b[2]):
            return 100.0 * s_amp
        s_elb = float(np.clip(1.0 - abs(a[2] - b[2]) / 45.0, 0, 1))
        return 100.0 * (0.5 * s_amp + 0.5 * s_elb)


# ---------------------------------------------------------------------------
# 8. Technique evaluation (GREEN / YELLOW / RED)
# ---------------------------------------------------------------------------
class TechniqueEvaluator:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _elbow(self, angle, rel_up, e_up, rel_long, over, style) -> np.ndarray:
        cfg = self.cfg
        st = np.zeros(len(angle), dtype=np.int8)
        with quiet():
            below = -rel_up
            pull_up = ~np.isnan(angle) & (below > cfg.pull_enter) & ~over
            if style in ("CRAWL", "FLY", "BREAST"):
                m = pull_up
                g = m & (e_up > cfg.elbow_margin) & (angle <= cfg.straight_warn)
                y = m & ((np.abs(e_up) <= cfg.elbow_margin) | (angle > cfg.straight_warn))
                r = m & ((e_up < -cfg.elbow_margin) | ((angle > cfg.straight_crit) & (below > cfg.straight_depth)))
                band_over = ~np.isnan(angle) & over & (rel_long < -0.10)
            else:
                g = y = r = np.zeros(len(angle), dtype=bool)
                band_over = ~np.isnan(angle) & over & (rel_long < -0.10)
            # catch-angle band rule: backstroke (up views) and any style in overhead view
            band = (pull_up if style == "BACK" else np.zeros(len(angle), dtype=bool)) | band_over
            g = g | (band & (angle >= 80) & (angle <= 135))
            y = y | (band & (((angle >= 50) & (angle < 80)) | ((angle > 135) & (angle <= 160))))
            r = r | (band & ((angle > 160) | (angle < 50)))
            st[g], st[y], st[r] = 1, 2, 3
        return st

    @staticmethod
    def _knee(flex, style) -> np.ndarray:
        lim = {"CRAWL": (45, 70), "BACK": (45, 70), "FLY": (80, 100), "BREAST": (125, 140)}[style]
        st = np.zeros(len(flex), dtype=np.int8)
        with quiet():
            ok = ~np.isnan(flex)
            st[ok & (flex <= lim[0])] = 1
            st[ok & (flex > lim[0]) & (flex <= lim[1])] = 2
            st[ok & (flex > lim[1])] = 3
        return st

    def _graded(self, val, warn, crit, cap=3) -> np.ndarray:
        st = np.zeros(len(val), dtype=np.int8)
        with quiet():
            a = np.abs(val)
            ok = ~np.isnan(val)
            st[ok & (a <= warn)] = 1
            st[ok & (a > warn) & (a <= crit)] = 2
            st[ok & (a > crit)] = min(3, cap)
        return st

    def evaluate(self, bio: Biomech, track: ViewTrack, style: str, fps: float,
                 sym_series: np.ndarray) -> Evaluation:
        cfg, n = self.cfg, len(track.codes)
        over = track.codes == VIEW_OVERHEAD
        st: Dict[str, np.ndarray] = {}
        for arm in "LR":
            st["elbow_" + arm] = self._elbow(bio.elbow[arm], bio.rel_up[arm], bio.e_up[arm],
                                             bio.rel_long[arm], over, style)
            st["knee_" + arm] = self._knee(bio.knee[arm], style)
        pscale = 1.8 if style in ("FLY", "BREAST") else 1.0
        st["pitch"] = self._graded(bio.pitch, cfg.pitch_warn * pscale, cfg.pitch_crit * pscale)
        st["hipdev"] = (self._graded(bio.hipdev, cfg.hipdev_warn, cfg.hipdev_crit)
                        if style in ("CRAWL", "BACK") else np.zeros(n, dtype=np.int8))
        roll_lim = (65.0, 80.0) if style in ("CRAWL", "BACK") else (15.0, 30.0)
        st["roll"] = self._graded(bio.roll, roll_lim[0], roll_lim[1], cap=2)
        st["torso"] = np.maximum(st["pitch"], st["hipdev"])
        sym = np.zeros(n, dtype=np.int8)
        ok = ~np.isnan(sym_series)
        sym[ok & (sym_series >= cfg.sym_warn)] = 1
        sym[ok & (sym_series < cfg.sym_warn) & (sym_series >= cfg.sym_crit)] = 2
        sym[ok & (sym_series < cfg.sym_crit)] = 3
        st["sym"] = sym

        min_len = max(2, int(cfg.min_event_sec * fps))
        crit_mask = np.zeros(n, dtype=bool)
        crit_text = [""] * n
        events, red_frames = {}, {}
        for key in ("elbow_L", "elbow_R", "pitch", "hipdev", "sym"):
            mask, cnt = SignalTools.run_mask(st[key] == 3, min_len)
            events[key] = cnt
            red_frames[key] = int(np.sum(st[key] == 3))
            for i in np.flatnonzero(mask):
                if crit_text[i]:
                    continue
                crit_mask[i] = True
                if key.startswith("elbow"):
                    side = "LEFT" if key.endswith("L") else "RIGHT"
                    crit_text[i] = ("DROPPED ELBOW (%s)" if style in ("CRAWL", "FLY", "BREAST")
                                    else "BAD CATCH ANGLE (%s)") % side
                elif key == "pitch":
                    crit_text[i] = ("BAD BODY PITCH - LEGS SINKING" if bio.pitch[i] > 0
                                    else "BAD BODY PITCH - HEAD TOO LOW")
                elif key == "hipdev":
                    crit_text[i] = "HIPS DROPPING" if bio.hipdev[i] < 0 else "HIPS PIKED UP"
                else:
                    crit_text[i] = "ASYMMETRIC PULL"
        return Evaluation(st, crit_mask, crit_text, events, red_frames)


# ---------------------------------------------------------------------------
# 8b. Stroke-cycle phase recognition + 8c. per-frame confidence engine
# ---------------------------------------------------------------------------
class PhaseRecognizer:
    """Labels every frame of each arm with its stroke-cycle phase.

    Phase anchors are the stroke peaks found by StrokeAnalyzer (one per arm
    cycle); the fractional position inside the peak-to-peak cycle maps to
    ENTRY -> CATCH -> PULL -> PUSH -> RECOVERY. Symmetric styles (FLY/BREAST)
    share the primary arm's anchors for both arms. Frames that cannot be
    assigned to any cycle stay UNKNOWN.
    """

    # fractional cycle boundaries: entry | catch | pull | push | recovery
    BOUNDS = (0.12, 0.30, 0.55, 0.78)

    def recognize(self, strokes: StrokeResult, style: str,
                  fps: float, n: int) -> PhaseResult:
        primary = strokes.peaks.get(strokes.primary,
                                    np.array([], dtype=int))
        codes: Dict[str, np.ndarray] = {}
        for arm in "LR":
            if ALTERNATING.get(style, True):
                anchors = np.asarray(strokes.peaks.get(arm, []), dtype=float)
                if anchors.size == 0 and primary.size:
                    # other arm missed: same rhythm, half a cycle later
                    anchors = self._shifted(primary, strokes, fps, n)
            else:
                anchors = np.asarray(primary, dtype=float)
            period = self._period(anchors, strokes, fps)
            codes[arm] = self._label(anchors, period, n)
        dist: Dict[str, float] = {}
        with quiet():
            all_codes = np.concatenate([codes["L"], codes["R"]])
            known = all_codes[all_codes != PH_UNKNOWN]
            total = max(len(known), 1)
            for code in (PH_ENTRY, PH_CATCH, PH_PULL, PH_PUSH, PH_RECOVERY):
                dist[PHASE_HUD[code]] = float(np.sum(known == code) / total)
        return PhaseResult(codes, dist)

    @staticmethod
    def _period(anchors: np.ndarray, strokes: StrokeResult,
                fps: float) -> float:
        if anchors.size >= 2:
            return float(np.median(np.diff(np.sort(anchors))))
        if np.isfinite(strokes.freq_hz) and strokes.freq_hz > 0:
            return float(fps / strokes.freq_hz)
        return float("nan")

    @staticmethod
    def _shifted(primary: np.ndarray, strokes: StrokeResult,
                 fps: float, n: int) -> np.ndarray:
        period = PhaseRecognizer._period(np.asarray(primary, dtype=float),
                                         strokes, fps)
        if not np.isfinite(period) or period <= 0:
            return np.array([], dtype=float)
        out = np.asarray(primary, dtype=float) + period / 2.0
        return out[(out >= 0) & (out < n)]

    def _label(self, anchors: np.ndarray, period: float,
               n: int) -> np.ndarray:
        out = np.full(n, PH_UNKNOWN, dtype=np.int8)
        if anchors.size == 0 or not np.isfinite(period) or period <= 1:
            return out
        pk = np.sort(anchors)
        b0, b1, b2, b3 = self.BOUNDS
        idx = np.arange(n, dtype=float)
        # cycle index k for every frame (extrapolated outside the peaks)
        k = np.searchsorted(pk, idx, side="right") - 1
        prev = np.where(k >= 0, pk[np.clip(k, 0, len(pk) - 1)],
                        pk[0] - period * (0 - k))
        nxt = np.where(k + 1 < len(pk), pk[np.clip(k + 1, 0, len(pk) - 1)],
                       pk[-1] + period * (k + 2 - len(pk)))
        span = np.maximum(nxt - prev, 1e-6)
        frac = (idx - prev) / span
        # only trust frames within ~1.5 cycles of a real anchor
        nearest = np.minimum(np.abs(idx - pk[0]), np.abs(idx - pk[-1]))
        ok = (k >= 0) & (k + 1 < len(pk)) | (nearest <= 1.5 * period)
        phase = np.full(n, PH_UNKNOWN, dtype=np.int8)
        phase[(frac < b0)] = PH_ENTRY
        phase[(frac >= b0) & (frac < b1)] = PH_CATCH
        phase[(frac >= b1) & (frac < b2)] = PH_PULL
        phase[(frac >= b2) & (frac < b3)] = PH_PUSH
        phase[(frac >= b3)] = PH_RECOVERY
        out[ok] = phase[ok]
        return out


class ConfidenceEngine:
    """Per-frame trust score + joint-angle measurement-error estimate.

    confidence[i] = 0.45 * visibility_coverage
                  + 0.35 * landmark_completeness (after cleaning)
                  + 0.20 * camera-view confidence

    Missed detections score ~0; clean side-view frames score ~1. The
    measurement error maps confidence to degrees (2 deg at conf=1 up to
    ~27 deg at conf=0) so coaches see an honest error bar on every angle.
    """

    def assess(self, pose_raw: PoseData, pose: PoseData,
               track: ViewTrack, cfg: Config) -> ConfidenceResult:
        n = pose.n
        with quiet():
            vis = pose_raw.img[:, :, 2].astype(np.float64)
            vis_cov = np.mean(np.where(np.isnan(vis), 0.0,
                                       (vis >= cfg.min_vis).astype(float)),
                              axis=1)
            ok = (~np.isnan(pose.img[:, :, 0])
                  & ~np.isnan(pose.img[:, :, 1]))
            completeness = ok.mean(axis=1)
            view = np.clip(np.nan_to_num(track.conf.astype(float), nan=0.5),
                           0.0, 1.0)
            conf = np.clip(0.45 * vis_cov + 0.35 * completeness
                           + 0.20 * view, 0.0, 1.0)
            err = 2.0 + 25.0 * np.power(1.0 - conf, 1.5)
        return ConfidenceResult(
            conf=conf, meas_err_deg=err,
            mean_conf=float(np.mean(conf)),
            low_ratio=float(np.mean(conf < 0.5)),
            high_ratio=float(np.mean(conf >= 0.8)))


# ---------------------------------------------------------------------------
# 9. HUD rendering
# ---------------------------------------------------------------------------
class VideoRenderer:
    def __init__(self, cfg: Config, res: Results):
        self.cfg, self.r = cfg, res

    @staticmethod
    def _txt(img, text, org, scale, color, thick=1):
        cv2.putText(img, text, org, FONT, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
        cv2.putText(img, text, org, FONT, scale, color, thick, cv2.LINE_AA)

    @staticmethod
    def _f(x, spec="%.0f") -> str:
        return "--" if x is None or np.isnan(x) else spec % x

    def _skeleton(self, frame, i, fs):
        r = self.r
        img = r.pose.img[i, :, :2]
        st = r.evalr.status
        base = max(1, int(round(min(frame.shape[:2]) / 360)))

        def pt(j):
            if np.isnan(img[j]).any():
                return None
            return int(img[j, 0]), int(img[j, 1])

        segs = [(L_SH, L_EL, "elbow_L"), (L_EL, L_WR, "elbow_L"), (R_SH, R_EL, "elbow_R"),
                (R_EL, R_WR, "elbow_R"), (L_HIP, L_KN, "knee_L"), (L_KN, L_AN, "knee_L"),
                (R_HIP, R_KN, "knee_R"), (R_KN, R_AN, "knee_R"), (L_SH, R_SH, "torso"),
                (L_SH, L_HIP, "torso"), (R_SH, R_HIP, "torso"), (L_HIP, R_HIP, "torso")]
        for a, b, key in segs:
            pa, pb = pt(a), pt(b)
            if pa is None or pb is None:
                continue
            col = STATUS_COLORS[int(st[key][i])]
            cv2.line(frame, pa, pb, (0, 0, 0), base * 2 + 3, cv2.LINE_AA)
            cv2.line(frame, pa, pb, col, base * 2 + 1, cv2.LINE_AA)
        for j in range(NJ):
            p = pt(j)
            if p is not None:
                cv2.circle(frame, p, base * 3, (255, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(frame, p, base * 3, (0, 0, 0), 1, cv2.LINE_AA)

        # angle arcs and numbers at elbows / knees
        for arm, (sh, el, wr, hp, kn, an) in {"L": (L_SH, L_EL, L_WR, L_HIP, L_KN, L_AN),
                                              "R": (R_SH, R_EL, R_WR, R_HIP, R_KN, R_AN)}.items():
            ang = r.bio.elbow[arm][i]
            pe, ps, pw = pt(el), pt(sh), pt(wr)
            if pe and ps and pw and not np.isnan(ang):
                col = STATUS_COLORS[int(st["elbow_" + arm][i])]
                a1 = math.degrees(math.atan2(ps[1] - pe[1], ps[0] - pe[0]))
                a2 = math.degrees(math.atan2(pw[1] - pe[1], pw[0] - pe[0]))
                diff = (a2 - a1 + 180.0) % 360.0 - 180.0
                rad = max(16, int(0.2 * np.hypot(ps[0] - pe[0], ps[1] - pe[1])))
                cv2.ellipse(frame, pe, (rad, rad), 0, min(a1, a1 + diff), max(a1, a1 + diff), col, base + 1, cv2.LINE_AA)
                self._txt(frame, "%d" % round(ang), (pe[0] + 10, pe[1] - 10), 0.6 * fs, col, 1 + base // 2)
            kf = r.bio.knee[arm][i]
            pk = pt(kn)
            if pk and not np.isnan(kf):
                self._txt(frame, "%d" % round(kf), (pk[0] + 8, pk[1] + 18), 0.5 * fs,
                          STATUS_COLORS[int(st["knee_" + arm][i])], 1)

    def _hud(self, frame, i, fs):
        r = self.r
        st = r.evalr.status
        f = self._f
        code = int(r.track.codes[i])
        sty = r.style_final
        sym = r.sym.series[i]
        sp = r.perf.speed[i]
        spm = r.strokes.spm_inst[i]
        warn = bool(r.evalr.crit_text[i]) or any(int(st[k][i]) == 2 for k in ("elbow_L", "elbow_R", "pitch", "hipdev"))
        status_txt = r.evalr.crit_text[i] if r.evalr.crit_text[i] else ("WARNING: CHECK FORM" if warn else "FORM OK")
        status_col = RED if r.evalr.crit_text[i] else (YELLOW if warn else GREEN)

        lines = [
            [("SETARGAN  VIEW: %s (%d%%)" % (VIEW_HUD[code], round(100 * r.track.conf[i])), CYAN)],
            [("STYLE: %s (%d%%)" % (STYLE_HUD[sty], round(100 * r.style_full.conf if r.style_final == r.style_full.best
                                                       else 100 * r.style_init.conf)), WHITE)],
            [("SPEED %s m/s   SPM %s" % (f(sp, "%.2f"), f(spm)), WHITE)],
            [("STROKES %d   SWOLF %s   SI %s" % (int(r.strokes.strokes_so_far[i]), f(r.perf.swolf[i]),
                                                 f(r.perf.eff_idx[i], "%.1f")), WHITE)],
            [("ELBOW L ", WHITE), (f(r.bio.elbow["L"][i]), STATUS_COLORS[int(st["elbow_L"][i])]),
             ("  R ", WHITE), (f(r.bio.elbow["R"][i]), STATUS_COLORS[int(st["elbow_R"][i])])],
            [("KNEE  L ", WHITE), (f(r.bio.knee["L"][i]), STATUS_COLORS[int(st["knee_L"][i])]),
             ("  R ", WHITE), (f(r.bio.knee["R"][i]), STATUS_COLORS[int(st["knee_R"][i])])],
            [("ROLL ", WHITE), (f(r.bio.roll[i]), STATUS_COLORS[int(st["roll"][i])]),
             ("  PITCH ", WHITE), (f(r.bio.pitch[i]), STATUS_COLORS[int(st["pitch"][i])]),
             ("  HIP ", WHITE), (f(r.bio.hipdev[i], "%.2f"), STATUS_COLORS[int(st["hipdev"][i])])],
            [("SYMMETRY ", WHITE), (f(sym) + ("%" if not np.isnan(sym) else ""), STATUS_COLORS[int(st["sym"][i])])],
            [("STATUS: ", WHITE), (status_txt, status_col)],
        ]
        scale = 0.55 * fs
        lh = int(30 * fs)
        pad = int(10 * fs)
        box_w = int(480 * fs)
        box_h = lh * len(lines) + 2 * pad
        x0, y0 = 10, 10
        x1, y1 = min(frame.shape[1] - 1, x0 + box_w), min(frame.shape[0] - 1, y0 + box_h)
        roi = frame[y0:y1, x0:x1]
        frame[y0:y1, x0:x1] = cv2.addWeighted(roi, 0.40, np.zeros_like(roi), 0.60, 0)
        c = int(18 * fs)                     # futuristic corner brackets
        for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            cv2.line(frame, (cx, cy), (cx + sx * c, cy), CYAN, 2, cv2.LINE_AA)
            cv2.line(frame, (cx, cy), (cx, cy + sy * c), CYAN, 2, cv2.LINE_AA)
        for k, segs in enumerate(lines):
            x = x0 + pad
            y = y0 + pad + lh * (k + 1) - int(8 * fs)
            for text, col in segs:
                self._txt(frame, text, (x, y), scale, col, 1)
                x += cv2.getTextSize(text, FONT, scale, 1)[0][0]

    def _banner(self, frame, i, fps, fs):
        r = self.r
        if not r.evalr.crit_mask[i]:
            return
        period = max(1, int(self.cfg.flash_period_sec * fps))
        if (i // period) % 2 != 0:
            return
        text = "!! CRITICAL: %s !!" % r.evalr.crit_text[i]
        h, w = frame.shape[:2]
        scale = 0.9 * fs
        tw = cv2.getTextSize(text, FONT, scale, 2)[0]
        x0, y0 = max(0, (w - tw[0]) // 2 - 20), h - int(90 * fs)
        x1, y1 = min(w - 1, x0 + tw[0] + 40), min(h - 1, y0 + int(60 * fs))
        roi = frame[y0:y1, x0:x1]
        red = np.zeros_like(roi)
        red[:] = RED
        frame[y0:y1, x0:x1] = cv2.addWeighted(roi, 0.25, red, 0.75, 0)
        cv2.putText(frame, text, (x0 + 20, y0 + int(40 * fs)), FONT, scale, (255, 255, 255), 2, cv2.LINE_AA)

    def render(self, in_path: str, out_path: str) -> None:
        r = self.r
        fps = r.pose.fps
        n, nxt, show = r.pose.n, 10, self.cfg.show
        with open_capture(in_path) as cap:
            ok, first = cap.read()
            if not ok:
                raise IOError("Video baraye render baz nashod.")
            # trust the decoded frame size: a rotated / re-encoded input can
            # differ from the resolution reported during pose extraction
            h, w = first.shape[:2]
            with open_writer(out_path, fps, (w, h)) as writer:
                fs = max(0.6, min(w, h) / 720.0)
                for i in range(n):
                    if i:
                        ok, frame = cap.read()
                        if not ok:
                            Console.say("[6/6] Hoshdar: video zoodtar tamam shod.")
                            break
                    else:
                        frame = first
                    if i % 8 == 0:
                        self.cfg.checkpoint()     # cancellable render
                    self._skeleton(frame, i, fs)
                    self._hud(frame, i, fs)
                    self._banner(frame, i, fps, fs)
                    writer.write(frame)
                    if show:
                        cv2.imshow("Setargan-Darya (ESC = khoroj)", frame)
                        if cv2.waitKey(1) & 0xFF == 27:
                            show = False
                            cv2.destroyAllWindows()
                    pct = (i + 1) * 100 // max(n, 1)
                    if pct >= nxt:
                        Console.say("[6/6] Sakht-e Video-ye Khoroji: %d%%" % pct)
                        nxt += 10
        if show:
            cv2.destroyAllWindows()


# ---------------------------------------------------------------------------
# 10. Export (JSON) and report (Finglish)
# ---------------------------------------------------------------------------
class JsonExporter:
    @staticmethod
    def _c(x):
        if isinstance(x, (np.floating, float)):
            return None if (np.isnan(x) or np.isinf(x)) else round(float(x), 4)
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.bool_,)):
            return bool(x)
        if isinstance(x, dict):
            return {str(k): JsonExporter._c(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [JsonExporter._c(v) for v in x]
        if isinstance(x, np.ndarray):
            return [JsonExporter._c(v) for v in x.tolist()]
        return x

    def export(self, r: Results, path: str) -> None:
        n, fps = r.pose.n, r.pose.fps
        st = r.evalr.status
        frames = []
        for i in range(n):
            frames.append({
                "frame": i, "time_s": round(i / fps, 4),
                "view": VIEW_HUD[int(r.track.codes[i])], "style": r.style_final,
                "elbow_angle_deg": {"left": r.bio.elbow["L"][i], "right": r.bio.elbow["R"][i]},
                "knee_flexion_deg": {"left": r.bio.knee["L"][i], "right": r.bio.knee["R"][i]},
                "shoulder_roll_deg": r.bio.roll[i], "body_pitch_deg": r.bio.pitch[i],
                "hip_deviation_norm": r.bio.hipdev[i],
                "speed_mps": r.perf.speed[i], "stroke_rate_spm": r.strokes.spm_inst[i],
                "strokes_total": r.strokes.strokes_so_far[i], "stroke_length_m": r.perf.stroke_len[i],
                "efficiency_index": r.perf.eff_idx[i], "swolf_est": r.perf.swolf[i],
                "symmetry_pct": r.sym.series[i],
                "stroke_phase": {"left": PHASE_HUD[int(r.phases.codes["L"][i])],
                                 "right": PHASE_HUD[int(r.phases.codes["R"][i])]},
                "confidence": r.confr.conf[i],
                "meas_error_deg": r.confr.meas_err_deg[i],
                "status_codes": {k: int(v[i]) for k, v in st.items()},
                "critical_warning": r.evalr.crit_text[i],
            })
        summary = {
            "video": os.path.basename(r.video_path), "fps": fps, "frames": n,
            "resolution": [r.pose.width, r.pose.height],
            "detect_ratio": r.pose_raw.detect_ratio, "rotation_rescues": r.pose_raw.rotation_rescues,
            "view_dominant": VIEW_HUD[r.track.dominant], "view_dominant_ratio": r.track.dominant_ratio,
            "style_initial": {"name": r.style_init.best, "conf": r.style_init.conf,
                              "frames": r.style_init.frames, "shares": r.style_init.shares},
            "style_full": {"name": r.style_full.best, "conf": r.style_full.conf,
                           "shares": r.style_full.shares, "features": r.style_full.features},
            "style_final": r.style_final,
            "strokes": {"cycles_primary_arm": r.strokes.cycles, "total_strokes": r.strokes.total_strokes,
                        "spm_avg": r.strokes.spm_avg, "primary_arm": r.strokes.primary,
                        "arm_frequency_hz": r.strokes.freq_hz},
            "speed": {"mean_mps": r.perf.mean_speed, "max_mps": r.perf.max_speed,
                      "distance_m": r.perf.distance, "median_m_per_px": r.perf.mpp_median},
            "performance": {"pool_length_m": r.perf.pool_length_m,
                            "swolf_estimated": r.perf.swolf_est, "stroke_length_m": r.perf.sl_mean,
                            "efficiency_index": r.perf.eff_mean,
                            "lengths": [{"n": a, "time_s": b, "strokes": c, "swolf": d} for a, b, c, d in r.perf.lengths]},
            "symmetry": {"global_pct": r.sym.global_pct, "amplitude": r.sym.amp,
                         "min_elbow_deg": r.sym.min_elbow, "note": r.sym.note},
            "phases": {"distribution": r.phases.dist},
            "confidence": {"mean": r.confr.mean_conf,
                           "low_ratio": r.confr.low_ratio,
                           "high_ratio": r.confr.high_ratio},
            "critical_events": r.evalr.events, "red_frames": r.evalr.red_frames,
        }
        with open(path, "w", encoding="ascii") as f:
            json.dump(self._c({"summary": summary, "frames": frames}), f, indent=1, ensure_ascii=True)


class ReportPrinter:
    @staticmethod
    def _v(x, spec="%.1f", unit="") -> str:
        return "namoshakhas" if x is None or (isinstance(x, float) and np.isnan(x)) else (spec % x) + unit

    def print(self, r: Results, out_video: Optional[str], out_json: Optional[str]) -> None:
        v = self._v
        n, fps = r.pose.n, r.pose.fps
        S = Console.say
        S("")
        Console.rule("=")
        S("   SETARGAN-DARYA  |  Gozaresh-e Nahayi-ye Tahlil-e Shena")
        Console.rule("=")
        S("Video                         : " + os.path.basename(r.video_path))
        S("Modat / Tedad-e Frame / FPS   : %.1f sanieh / %d / %.1f" % (n / fps, n, fps))
        S("Rezolushen                    : %d x %d" % (r.pose.width, r.pose.height))
        S("Darsad-e Tashkhis-e Eskelet   : %.1f%%  (Najat ba Charkhesh: %d frame)" %
          (100 * r.pose_raw.detect_ratio, r.pose_raw.rotation_rescues))
        Console.rule("-")
        S("[Zaviye-ye Doorbin]")
        S("Nama-ye Ghalebe               : %s  (soorat: %.0f%% az frame-ha)" %
          (VIEW_FINGLISH[r.track.dominant], 100 * r.track.dominant_ratio))
        Console.rule("-")
        S("[Tashkhis-e Sabk-e Shena]")
        S("Sabk dar %d frame-e avval      : %s  (etminan %.0f%%)" %
          (r.style_init.frames, STYLE_FINGLISH[r.style_init.best], 100 * r.style_init.conf))
        S("Sabk dar kol-e video          : %s  (etminan %.0f%%)" %
          (STYLE_FINGLISH[r.style_full.best], 100 * r.style_full.conf))
        S("Natije-ye Nahayi              : %s" % STYLE_FINGLISH[r.style_final])
        shares = ", ".join("%s %.0f%%" % (k, 100 * s) for k, s in
                           sorted(r.style_full.shares.items(), key=lambda kv: -kv[1]))
        S("Sahm-e Emtiaz-e Sabk-ha       : " + shares)
        Console.rule("-")
        S("[Zarbe va Sorat]")
        S("Bazoye Asli (Tahlil shode)    : %s" % ("Chap" if r.strokes.primary == "L" else "Rast"))
        S("Tedad-e Charkhe-ye Bazoye Asli: %d" % r.strokes.cycles)
        S("Tedad-e Kol-e Zarbe-ha        : %d" % r.strokes.total_strokes)
        S("Nerkh-e Zarbe (SPM) Miyangin  : %s" % v(r.strokes.spm_avg, "%.1f"))
        S("Sorat-e Miyangin              : %s" % v(r.perf.mean_speed, "%.2f", " m/s"))
        S("Sorat-e Hadeaksar             : %s" % v(r.perf.max_speed, "%.2f", " m/s"))
        S("Masafat-e Takhmini            : %s" % v(r.perf.distance, "%.1f", " metr"))
        S("Tool-e Zarbe (Stroke Length)  : %s" % v(r.perf.sl_mean, "%.2f", " metr/zarbe"))
        S("Shakhes-e Karaee (Eff. Index) : %s" % v(r.perf.eff_mean, "%.2f"))
        S("SWOLF (Takhmini, %.0f m)       : %s" % (r.perf.pool_length_m, v(r.perf.swolf_est, "%.1f")))
        if r.perf.lengths:
            for k, t, s, sw in r.perf.lengths:
                S("   Tool %d: zaman %.1f s | zarbe %d | SWOLF %.1f" % (k, t, s, sw))
        else:
            S("   (Hich tool-e kamel dar video tashkhis dade nashod; SWOLF az roye sorat va SPM bar-avard shod)")
        Console.rule("-")
        S("[Zavaye-ye Mafasel]")
        with quiet():
            for arm, name in (("L", "Chap"), ("R", "Rast")):
                e = r.bio.elbow[arm]
                S("Aranj %-4s  miyangin %s | kamtarin %s" % (name, v(np.nanmean(e), "%.0f", " deg"),
                                                           v(np.nanmin(e), "%.0f", " deg")))
            for arm, name in (("L", "Chap"), ("R", "Rast")):
                S("Kham-shodan-e Zanu %-4s: bishtarin %s" % (name, v(np.nanmax(r.bio.knee[arm]), "%.0f", " deg")))
            S("Charkhesh-e Shane (Roll)      : %s ta %s" % (v(np.nanpercentile(r.bio.roll, 5), "%.0f", " deg"),
                                                           v(np.nanpercentile(r.bio.roll, 95), "%.0f", " deg")))
            S("Shib-e Badan (Pitch) miyangin : %s" % v(np.nanmean(r.bio.pitch), "%.1f", " deg"))
            S("Oftadegi/Moojshodan-e Lagan   : %s" % v(np.nanmean(r.bio.hipdev), "%.2f", " (nesbat be tane)"))
        Console.rule("-")
        S("[Tagharon-e Kesh (Pull Symmetry)]")
        S("Tagharon-e Kolli              : %s" % v(r.sym.global_pct, "%.0f", "%"))
        S("Amplitude Chap / Rast         : %s / %s" % (v(r.sym.amp["L"], "%.2f"), v(r.sym.amp["R"], "%.2f")))
        S("Aranj-e Kam Chap / Rast       : %s / %s" % (v(r.sym.min_elbow["L"], "%.0f", " deg"),
                                                       v(r.sym.min_elbow["R"], "%.0f", " deg")))
        S("Vaziat                        : " + r.sym.note)
        Console.rule("-")
        S("[Faz-haye Charkhe-ye Zarbe (Stroke Phases)]")
        for code in (PH_ENTRY, PH_CATCH, PH_PULL, PH_PUSH, PH_RECOVERY):
            S("%-28s: %.1f%% az frame-ha" % (PHASE_FINGLISH[code],
              100 * r.phases.dist.get(PHASE_HUD[code], 0.0)))
        Console.rule("-")
        S("[Etminan-e Tahlil (Confidence)]")
        S("Etminan-e Miyangin            : %.0f%%" % (100 * r.confr.mean_conf,))
        S("Frame-haye Kam-etminan (<50%%)  : %.1f%%" % (100 * r.confr.low_ratio,))
        S("Frame-haye Por-etminan (>=80%%) : %.1f%%" % (100 * r.confr.high_ratio,))
        with quiet():
            S("Khataye Andazegiri-ye Zavaya   : %s" % v(np.nanmean(r.confr.meas_err_deg), "%.1f", " deg"))
        Console.rule("-")
        S("[Khata-haye Tehnik (Bohrani)]")
        names = {"elbow_L": "Khataye Aranj Chap (Aranj Oftade / Zaviye-ye Gir-e Bad)",
                 "elbow_R": "Khataye Aranj Rast (Aranj Oftade / Zaviye-ye Gir-e Bad)",
                 "pitch": "Shib-e Nadorost-e Badan (Pitch)", "hipdev": "Oftadegi/Bala-amadegi-ye Lagan",
                 "sym": "Na-tagharon-e Kesh"}
        total = 0
        for k, nm in names.items():
            S("%-56s: %d bar (%d frame)" % (nm, r.evalr.events[k], r.evalr.red_frames[k]))
            total += r.evalr.events[k]
        S("Majmoo-e Khata-haye Bohrani   : %d" % total)
        S("Natije: " + ("Tehnik Alie, khata-ye bohrani peyda nashod." if total == 0
                        else "Khataye Tehnik Tashkhis Dade Shod - gozaresh-e bala va video ra barresi konid."))
        Console.rule("-")
        if out_video:
            S("Video-ye Khoroji   : " + out_video)
        if out_json:
            S("Faile JSON         : " + out_json)
        S("Tavajoh: Dorosti-ye natayej be zaviye-ye doorbin, rooshanayi, va sabet bodan-e doorbin vabaste ast.")
        Console.rule("=")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class SwimAnalysisPipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def analyze(self, video_path: str, pose_raw: Optional[PoseData] = None) -> Results:
        cfg = self.cfg
        if pose_raw is None:
            pose_raw = PoseExtractor(cfg).extract(video_path)
        if pose_raw.detect_ratio < 0.05:
            raise RuntimeError("Dar hich frami badan tashkhis dade nashod. Rooshanayi/zaviye ra barresi konid.")
        n, fps = pose_raw.n, pose_raw.fps
        cfg.checkpoint()

        Console.say("[2/6] Pak-sazi-ye noise (Hampel, gap-fill, smoothing)...")
        pose = LandmarkCleaner(cfg).clean(pose_raw)
        cfg.checkpoint()

        Console.say("[3/6] Tashkhis-e zaviye-ye doorbin va tatbigh-e perspective...")
        track = ViewClassifier(cfg).classify(pose)
        work = ViewAdapter.build(pose, track)
        cfg.checkpoint()

        Console.say("[4/6] Mohasebe-ye biomechanic va tashkhis-e sabk...")
        bio = BiomechanicsEngine(cfg).compute(pose, track, work)
        sc = StyleClassifier()
        win = min(n, max(10, cfg.classify_frames))
        s_init = sc.classify(bio, fps, 0, win)
        s_full = sc.classify(bio, fps, 0, n)
        style_final = s_full.best if n >= fps * 4 else s_init.best
        cfg.checkpoint()

        Console.say("[5/6] Shomaresh-e zarbe, sorat, SWOLF, tagharon, faz-haye zarbe, etminan va arzyabi-ye tehnik...")
        strokes = StrokeAnalyzer().analyze(bio, style_final, fps, n)
        speed, scale = SpeedEstimator().estimate(pose, cfg, track)
        perf = PerformanceMetrics().compute(speed, scale, strokes, fps, cfg)
        sym = SymmetryAnalyzer().analyze(strokes, bio, fps, n)
        evalr = TechniqueEvaluator(cfg).evaluate(bio, track, style_final, fps, sym.series)
        phases = PhaseRecognizer().recognize(strokes, style_final, fps, n)
        confr = ConfidenceEngine().assess(pose_raw, pose, track, cfg)

        return Results(pose_raw, pose, track, work, bio, s_init, s_full, style_final,
                       strokes, perf, sym, evalr, phases, confr, video_path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Setargan-Darya: Tahlil-e khodkar-e sabk va tehnik-e shena az video")
    p.add_argument("input", help="Masir-e video-ye vorudi")
    p.add_argument("-o", "--output", default=None, help="Masir-e video-ye khoroji (pishfarz: <vorudi>_swimai.mp4)")
    p.add_argument("--json", default=None, help="Masir-e file-e JSON (pishfarz: <vorudi>_swimai.json)")
    p.add_argument("--view", choices=["auto", "side", "front", "overhead", "oblique"], default="auto",
                   help="Zaviye-ye doorbin (auto = tashkhis-e khodkar)")
    p.add_argument("--height", type=float, default=1.75, help="Ghad-e shenagar be metr baraye kalibrasion")
    p.add_argument("--pool-length", type=float, default=25.0, help="Tool-e estakhr be metr baraye SWOLF")
    p.add_argument("--fov", type=float, default=65.0, help="Zaviye-ye did-e ofoghi-ye doorbin (daraje)")
    p.add_argument("--meters-per-pixel", type=float, default=None, help="Kalibrasion-e dasti (metr bar pixel)")
    p.add_argument("--classify-frames", type=int, default=45,
                   help="Tedad-e frame-e avval baraye tashkhis-e sabk (pishfarz 45)")
    p.add_argument("--model-complexity", type=int, choices=[0, 1, 2], default=1, help="Pichidegi-ye model-e MediaPipe")
    p.add_argument("--flip-depth", action="store_true",
                   help="Agar prone/supine bar-aks tashkhis dade mishavad, ealamat-e omgh (z) ra barax konid")
    p.add_argument("--no-rotation-fallback", action="store_true", help="Gheyr-faal kardan-e charkhesh-e 90 darajeei")
    p.add_argument("--no-render", action="store_true", help="Video-ye khoroji sakhte nashavad")
    p.add_argument("--show", action="store_true", help="Namayesh-e zende hengam-e render")
    return p.parse_args()


def main() -> int:
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(errors="replace")
    args = parse_args()
    if not os.path.isfile(args.input):
        Console.say("Khata: file-e vorudi peyda nashod: " + args.input)
        return 1

    cfg = Config(model_complexity=args.model_complexity,
                 rotation_fallback=not args.no_rotation_fallback,
                 flip_depth=args.flip_depth,
                 classify_frames=int(np.clip(args.classify_frames, 10, 600)),
                 swimmer_height_m=args.height, fov_deg=args.fov,
                 meters_per_pixel=args.meters_per_pixel, pool_length_m=args.pool_length,
                 view_override=None if args.view == "auto" else VIEW_ARG[args.view],
                 render=not args.no_render, show=args.show)

    stem = os.path.splitext(args.input)[0]
    out_video = args.output or stem + "_swimai.mp4"
    out_json = args.json or stem + "_swimai.json"

    try:
        Console.say("Setargan-Darya shoroo shod. Video: " + args.input)
        results = SwimAnalysisPipeline(cfg).analyze(args.input)
        if cfg.render:
            VideoRenderer(cfg, results).render(args.input, out_video)
        else:
            out_video = None
        JsonExporter().export(results, out_json)
        ReportPrinter().print(results, out_video, out_json)
    except AnalysisCancelled as e:
        Console.say("Tahlil motevaghaf shod: " + str(e))
        return 130
    except (IOError, RuntimeError) as e:
        Console.say("Khata: " + str(e))
        return 1
    except KeyboardInterrupt:
        Console.say("Tahlil tavasot-e karbar ghata shod (Ctrl+C).")
        return 130
    except Exception as e:  # noqa: BLE001 - never dump a raw traceback on users
        Console.say("Khata-ye gheyr-montazere: %s: %s" % (type(e).__name__, e))
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
