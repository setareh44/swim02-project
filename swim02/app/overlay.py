# -*- coding: utf-8 -*-
"""ترسیم اسکلت روی فریم ویدیو (فقط OpenCV + NumPy، بدون وابستگی به Qt).

این توابع از ``video_player`` جدا شده‌اند تا مستقل از محیط گرافیکی تست شوند.
نکته مهم که یک کرش واقعی ساخته بود: مختصات ``x`` و ``y`` هر مفصل مستقل از
هم ممکن است ``NaN`` باشند (فیلترهای پاک‌سازی هر کانال را جدا میان‌یابی
می‌کنند). اگر فقط یکی بررسی شود، ``int(nan)`` در ``cv2.circle`` خطای
``ValueError: cannot convert float NaN to integer`` می‌دهد و پخش ویدیو
متوقف می‌شود.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

MIN_VIS = 0.4


def valid_mask(pts: np.ndarray, min_vis: float = MIN_VIS) -> np.ndarray:
    """ماسک مفصل‌های قابل ترسیم: هر دو مختصات متناهی و visibility کافی."""
    pts = np.asarray(pts, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] < 3 or pts.shape[0] == 0:
        return np.zeros((pts.shape[0] if pts.ndim else 0,), dtype=bool)
    vis = np.where(np.isfinite(pts[:, 2]), pts[:, 2], 0.0)
    return (np.isfinite(pts[:, 0]) & np.isfinite(pts[:, 1])
            & (vis >= min_vis))


def points(pts: np.ndarray, width: int, height: int,
           min_vis: float = MIN_VIS) -> List[Optional[Tuple[int, int]]]:
    """مختصات صحیح نقاط معتبر (کلیپ‌شده در کادر) یا None برای نقاط نامعتبر."""
    pts = np.asarray(pts, dtype=np.float64)
    mask = valid_mask(pts, min_vis)
    out: List[Optional[Tuple[int, int]]] = []
    max_x, max_y = max(0, width - 1), max(0, height - 1)
    for j in range(pts.shape[0]):
        if not mask[j]:
            out.append(None)
            continue
        x = int(round(float(np.clip(pts[j, 0], 0, max_x))))
        y = int(round(float(np.clip(pts[j, 1], 0, max_y))))
        out.append((x, y))
    return out


def draw_skeleton(frame: np.ndarray,
                  pts: np.ndarray,
                  bones: Sequence[Tuple[int, int]],
                  status: Optional[Dict[int, int]] = None,
                  colors: Optional[Dict[int, Tuple[int, int, int]]] = None,
                  default_color: Tuple[int, int, int] = (220, 220, 255),
                  highlights: Sequence[int] = (),
                  min_vis: float = MIN_VIS) -> np.ndarray:
    """رسم استخوان‌ها (سفید نیمه‌شفاف) و مفصل‌های رنگی روی ``frame``.

    ``frame`` به‌صورت درجا تغییر می‌کند و برگردانده می‌شود.
    """
    if frame is None or frame.size == 0:
        return frame
    h, w = frame.shape[:2]
    pix = points(pts, w, h, min_vis)
    colors = colors or {}
    status = status or {}

    overlay = frame.copy()
    for a, b in bones:
        pa = pix[a] if 0 <= a < len(pix) else None
        pb = pix[b] if 0 <= b < len(pix) else None
        if pa is None or pb is None:
            continue
        cv2.line(overlay, pa, pb, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    for j, p in enumerate(pix):
        if p is None:
            continue
        color = colors.get(status.get(j, 0), default_color)
        radius = 7 if j in highlights else 5
        cv2.circle(frame, p, radius, color, -1, cv2.LINE_AA)
        cv2.circle(frame, p, radius, (255, 255, 255), 1, cv2.LINE_AA)
    return frame
