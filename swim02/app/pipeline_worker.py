# -*- coding: utf-8 -*-
"""اجرای پایپلاین swim_ai در نخ جدا با سیگنال پیشرفت و لاگ زنده."""
from __future__ import annotations

import os
import re
import sys
import time
import traceback

from PySide6.QtCore import QObject, Signal

from swim_ai import (AnalysisCancelled, Config, JsonExporter, PoseExtractor,
                     SwimAnalysisPipeline, VideoRenderer, VIEW_ARG)

from . import about_info as AI

_STAGE_RE = re.compile(r"\[(\d)/6\]")


class _StdoutCatcher:
    """صدور خطوط stdout به صورت سیگنال (مسیر لاگ فینگلیش swim_ai)."""

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, on_line):
        self._buf = ""
        self._on_line = on_line

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                self._on_line(line)
        return len(s)

    def writelines(self, lines) -> None:  # pragma: no cover - rarely used
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        if self._buf.strip():
            self._on_line(self._buf.strip())
            self._buf = ""

    def isatty(self) -> bool:
        return False

    def fileno(self):
        raise OSError("stream has no fileno")


class AnalysisWorker(QObject):
    stage = Signal(int, str)          # مرحله ۰..۵ + متن
    progress = Signal(int, int)       # فریم فعلی / کل (مرحله استخراج)
    log = Signal(str)
    finished = Signal(object, str, str)   # Results، مسیر ویدیو، مسیر JSON
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, video_path: str, settings: dict):
        super().__init__()
        self.video_path = video_path
        self.settings = settings
        self._stop = False
        self._last_emit = 0.0

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """درخواست توقف؛ خود پایپلاین بین فریم‌ها آن را بررسی می‌کند."""
        self._stop = True

    @property
    def stopped(self) -> bool:
        return self._stop

    # ------------------------------------------------------------------
    def run(self) -> None:
        old_stdout = sys.stdout

        def _on_line(line: str) -> None:
            self.log.emit(line)
            m = _STAGE_RE.match(line)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx <= 4:
                    self.stage.emit(idx, line)

        catcher = _StdoutCatcher(_on_line)
        sys.stdout = catcher
        out_video = ""
        out_json = ""
        # banner first: every run (and every bug-report screenshot) shows
        # exactly which app version produced it.
        print("%s %s - tahlil shoroo shod: %s"
              % (AI.APP_NAME, AI.APP_VERSION,
                 os.path.basename(self.video_path)))
        try:
            s = self.settings
            cfg = Config(
                model_complexity=int(s.get("model_complexity", 1)),
                swimmer_height_m=float(s.get("height", 1.75)),
                pool_length_m=float(s.get("pool_length", 25.0)),
                fov_deg=float(s.get("fov", 65.0)),
                view_override=VIEW_ARG.get(s.get("view", "auto"))
                if s.get("view", "auto") != "auto" else None,
                render=bool(s.get("render", True)),
                cancel=lambda: self._stop,
            )

            stem = os.path.splitext(self.video_path)[0]
            out_video = stem + "_swimai.mp4"
            out_json = stem + "_swimai.json"

            pipeline = SwimAnalysisPipeline(cfg)

            # مرحله ۱: استخراج اسکلت با پیشرفت فریم‌به‌فریم (throttle ~۸ هرتز)
            self.stage.emit(0, "استخراج اسکلت بدن…")
            extractor = PoseExtractor(cfg)

            def _emit_progress(i: int, n: int) -> None:
                now = time.monotonic()
                if i == n or now - self._last_emit >= 0.12:
                    self._last_emit = now
                    self.progress.emit(i, n)

            pose_raw = extractor.extract(
                self.video_path, on_progress=_emit_progress,
            )
            self.progress.emit(pose_raw.n, pose_raw.n)

            # مراحل ۲..۵ داخل analyze انجام می‌شوند؛ تغییر مرحله از روی لاگ
            results = pipeline.analyze(self.video_path, pose_raw=pose_raw)

            # مرحله ۶: خروجی‌ها
            if cfg.render:
                self.stage.emit(5, "رندر ویدیوی خروجی با داشبورد HUD…")
                VideoRenderer(cfg, results).render(self.video_path, out_video)
            else:
                out_video = ""
            self.stage.emit(5, "ذخیره گزارش JSON…")
            JsonExporter().export(results, out_json)

            self.finished.emit(results, out_video, out_json)
        except AnalysisCancelled:
            self._remove_partial(out_video)
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._remove_partial(out_video)
            self.failed.emit(str(e))
        finally:
            sys.stdout = old_stdout

    @staticmethod
    def _remove_partial(path: str) -> None:
        """خروجی نیمه‌تمام (ویدیوی رندر‌شدهٔ ناقص) را پاک می‌کند."""
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # اتصال سیگنال مرحله به خطوط لاگ [k/6]
    def handle_log_line(self, line: str) -> None:
        m = _STAGE_RE.match(line)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx <= 4:
                self.stage.emit(idx, line)
