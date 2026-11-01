# -*- coding: utf-8 -*-
"""Synthetic swimmer generator for the SWIM-AI tests.

A side-view front-crawl clip is rendered analytically: the body travels along
the image x axis, the hands follow a crawl path, the elbow is solved with
two-link inverse kinematics (so every bone keeps its anthropometric length) and
the whole skeleton is projected through a pinhole camera.  Because the ground
truth is known, the engine's style, stroke-rate, speed and calibration
estimates can be checked against it.
"""
from __future__ import annotations

import numpy as np

import swim_ai as S

HEIGHT = 1.75
TORSO = S.ANTHRO["torso"] * HEIGHT
UA = S.ANTHRO["upper_arm"] * HEIGHT
FA = S.ANTHRO["forearm"] * HEIGHT
THIGH = S.ANTHRO["thigh"] * HEIGHT
SHANK = S.ANTHRO["shank"] * HEIGHT
HALF_SW = 0.20
HALF_HIP = 0.09

F_PX = 700.0
Z0 = 12.0
W, H = 1280, 720
TRUE_MPP = Z0 / F_PX


def _arm_points(phase: float, side_sign: float):
    """Elbow and wrist (world x, y, z) for crawl stroke phase in [0, 1)."""
    p = phase % 1.0
    z = 0.20 * side_sign
    if p < 0.5:                      # underwater pull: hand sweeps backwards
        u = p / 0.5
        wx = 0.55 * np.cos(np.pi * u)
        wy = 0.18 + 0.02 * np.sin(np.pi * u)
    else:                            # recovery above water: hand sweeps forward
        u = (p - 0.5) / 0.5
        wx = -0.55 * np.cos(np.pi * u)
        wy = -0.12 - 0.16 * np.sin(np.pi * u)

    n = float(np.hypot(wx, wy))
    n = float(np.clip(n, abs(UA - FA) + 1e-3, UA + FA - 1e-3))
    a = (UA * UA - FA * FA + n * n) / (2.0 * n)
    h = float(np.sqrt(max(UA * UA - a * a, 0.0)))
    ux, uy = wx / n, wy / n
    px, py = -uy, ux
    if py > 0:                       # keep the elbow above the shoulder-wrist chord
        px, py = -px, -py
    elbow = np.array([a * ux + h * px, a * uy + h * py, z])
    wrist = np.array([wx, wy, z])
    return elbow, wrist


def make_pose(n: int = 240, fps: float = 60.0, period_s: float = 1.30,
              speed_mps: float = 1.50, bob_m: float = 0.10,
              start_x: float = -2.0, noise_px: float = 1.0,
              seed: int = 7) -> S.PoseData:
    """Build a synthetic PoseData clip (side view, front crawl)."""
    rng = np.random.default_rng(seed)
    img = np.full((n, S.NJ, 3), np.nan, np.float32)
    wld = np.full((n, S.NJ, 3), np.nan, np.float32)
    for i in range(n):
        t = i / fps
        x0 = start_x + speed_mps * t
        y0 = bob_m * np.sin(2 * np.pi * t / period_s)
        phase = t / period_s

        def P(x, y, z):
            return np.array([x0 + x, y0 + y, z])

        el_l, wr_l = _arm_points(phase, +1.0)
        el_r, wr_r = _arm_points(phase + 0.5, -1.0)
        kick = 0.12 * np.sin(4 * np.pi * t / period_s)
        pts = {
            S.NOSE: P(0.14, -0.03, 0.0),
            S.L_SH: P(0.0, 0.0, +HALF_SW), S.R_SH: P(0.0, 0.0, -HALF_SW),
            S.L_EL: P(*el_l), S.R_EL: P(*el_r),
            S.L_WR: P(*wr_l), S.R_WR: P(*wr_r),
            S.L_HIP: P(-TORSO, 0.02, +HALF_HIP),
            S.R_HIP: P(-TORSO, 0.02, -HALF_HIP),
            S.L_KN: P(-TORSO - THIGH, 0.03 + kick, +HALF_HIP),
            S.R_KN: P(-TORSO - THIGH, 0.03 - kick, -HALF_HIP),
            S.L_AN: P(-TORSO - THIGH - SHANK, 0.04 + 1.6 * kick, +HALF_HIP),
            S.R_AN: P(-TORSO - THIGH - SHANK, 0.04 - 1.6 * kick, -HALF_HIP),
        }
        for j, p in pts.items():
            wld[i, j] = p
            depth = max(Z0 - p[2], 0.5)
            u = W / 2.0 + F_PX * p[0] / depth
            v = H / 2.0 + F_PX * p[1] / depth
            img[i, j] = (u + rng.normal(0, noise_px),
                         v + rng.normal(0, noise_px), 0.92)
    return S.PoseData(img, wld.astype(np.float32), float(fps), W, H, 1.0, 0)


def run_pipeline(pose: S.PoseData, **cfg_kwargs) -> S.Results:
    """Analyse a synthetic clip without touching the video decoder."""
    cfg = S.Config(render=False, **cfg_kwargs)
    return S.SwimAnalysisPipeline(cfg).analyze("synthetic.mp4", pose_raw=pose)
