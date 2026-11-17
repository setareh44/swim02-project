# -*- coding: utf-8 -*-
"""Longitudinal analysis history and progress tracking (Qt-free).

Every finished analysis is archived per athlete::

    <data_dir>/analyses/<athlete_id>/<analysis_id>.json   (full engine JSON)
    <data_dir>/analyses/<athlete_id>/index.json           (summaries)

ProgressTracker turns the stored summaries into trend lines (linear
regression slope), delta percentages and a one-step-ahead forecast, so the
coach panel, the athlete dashboard and the motivational engine all share one
implementation.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .auth import alog, data_dir, utcnow_iso

ANALYSES_DIR = "analyses"

# metric -> True when "lower is better" (SWOLF); everything else higher=better
LOWER_IS_BETTER = {"swolf": True, "spm": False, "mean_speed": False,
                   "symmetry": False, "confidence": False}

METRIC_FA = {"swolf": "SWOLF", "spm": "نرخ ضربه (SPM)",
             "mean_speed": "سرعت میانگین", "symmetry": "تقارن",
             "confidence": "اطمینان تحلیل"}
METRIC_FINGLISH = {"swolf": "SWOLF", "spm": "SPM",
                   "mean_speed": "mean-speed", "symmetry": "symmetry",
                   "confidence": "confidence"}


def _finite(value, default: Optional[float] = None) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


# ---------------------------------------------------------------------------
@dataclass
class AnalysisSummary:
    analysis_id: str
    athlete_id: str
    date_iso: str
    video_name: str
    style: str = ""
    spm: Optional[float] = None
    swolf: Optional[float] = None
    mean_speed: Optional[float] = None
    symmetry: Optional[float] = None
    confidence: Optional[float] = None
    json_file: str = ""
    video_out: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisSummary":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in (data or {}).items() if k in known}
        obj = cls(analysis_id=str(clean.get("analysis_id", "")),
                  athlete_id=str(clean.get("athlete_id", "")),
                  date_iso=str(clean.get("date_iso", "")),
                  video_name=str(clean.get("video_name", "")))
        for key in ("style", "json_file", "video_out"):
            setattr(obj, key, str(clean.get(key, "") or ""))
        for key in ("spm", "swolf", "mean_speed", "symmetry", "confidence"):
            setattr(obj, key, _finite(clean.get(key)))
        return obj

    def metric(self, name: str) -> Optional[float]:
        return _finite(getattr(self, name, None))


# ---------------------------------------------------------------------------
class HistoryStore:
    """Per-athlete archive of past analysis JSON files."""

    def __init__(self, root: Optional[str] = None):
        self.root = root or os.path.join(data_dir(), ANALYSES_DIR)
        os.makedirs(self.root, exist_ok=True)

    # -- paths ------------------------------------------------------------
    def athlete_dir(self, athlete_id: str) -> str:
        safe = "".join(c for c in str(athlete_id) if c.isalnum() or c in "-_")
        path = os.path.join(self.root, safe or "unknown")
        os.makedirs(path, exist_ok=True)
        return path

    def _index_path(self, athlete_id: str) -> str:
        return os.path.join(self.athlete_dir(athlete_id), "index.json")

    # -- recording --------------------------------------------------------
    @staticmethod
    def _summarise_engine_json(engine: dict, athlete_id: str,
                               video_name: str, json_file: str,
                               video_out: str,
                               analysis_id: str) -> AnalysisSummary:
        s = engine.get("summary", {}) if isinstance(engine, dict) else {}
        strokes = s.get("strokes", {}) or {}
        perf = s.get("performance", {}) or {}
        speed = s.get("speed", {}) or {}
        sym = s.get("symmetry", {}) or {}
        conf = s.get("confidence", {}) or {}
        return AnalysisSummary(
            analysis_id=analysis_id, athlete_id=athlete_id,
            date_iso=utcnow_iso(), video_name=video_name,
            style=str(s.get("style_final", "") or ""),
            spm=_finite(strokes.get("spm_avg")),
            swolf=_finite(perf.get("swolf_estimated")),
            mean_speed=_finite(speed.get("mean_mps")),
            symmetry=_finite(sym.get("global_pct")),
            confidence=_finite(conf.get("mean")),
            json_file=json_file, video_out=video_out)

    def record(self, athlete_id: str, engine_json: dict, video_name: str,
               json_file: str = "", video_out: str = "",
               analysis_id: Optional[str] = None) -> AnalysisSummary:
        """Archive one finished analysis and return its summary."""
        folder = self.athlete_dir(athlete_id)
        stamp = utcnow_iso().replace(":", "").replace("+", "z")
        aid = analysis_id or ("A-%s" % stamp)
        # keep the full engine JSON next to the index for later inspection
        try:
            with open(os.path.join(folder, aid + ".json"), "w",
                      encoding="ascii") as f:
                json.dump(engine_json, f, ensure_ascii=True, indent=1)
        except (OSError, TypeError, ValueError) as exc:
            alog("Hoshdar: zakhire JSON namovafagh bood: %s" % exc)
        summary = self._summarise_engine_json(engine_json, athlete_id,
                                              video_name, json_file,
                                              video_out, aid)
        items = self.list(athlete_id)
        items.append(summary)
        self._write_index(athlete_id, items)
        alog("Natije dar history zakhire shod: %s / %s" % (athlete_id, aid))
        return summary

    def record_from_files(self, athlete_id: str, engine_json_path: str,
                          video_out: str = "") -> Optional[AnalysisSummary]:
        try:
            with open(engine_json_path, "r", encoding="ascii") as f:
                engine = json.load(f)
        except (OSError, ValueError) as exc:
            alog("Hoshdar: khandane JSON namovafagh bood: %s" % exc)
            return None
        video_name = ""
        if isinstance(engine, dict):
            video_name = str((engine.get("summary") or {}).get("video", ""))
        return self.record(athlete_id, engine, video_name or
                           os.path.basename(engine_json_path),
                           json_file=engine_json_path, video_out=video_out)

    # -- reading ----------------------------------------------------------
    def _write_index(self, athlete_id: str,
                     items: List[AnalysisSummary]) -> None:
        tmp = self._index_path(athlete_id) + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in items], f,
                          ensure_ascii=False, indent=1)
            os.replace(tmp, self._index_path(athlete_id))
        except OSError as exc:
            alog("Hoshdar: zakhire index namovafagh bood: %s" % exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def list(self, athlete_id: str) -> List[AnalysisSummary]:
        path = self._index_path(athlete_id)
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [AnalysisSummary.from_dict(d) for d in data
                if isinstance(d, dict)]

    def load_full(self, athlete_id: str, analysis_id: str) -> Optional[dict]:
        path = os.path.join(self.athlete_dir(athlete_id),
                            analysis_id + ".json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="ascii") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def athlete_ids(self) -> List[str]:
        try:
            names = sorted(os.listdir(self.root))
        except OSError:
            return []
        return [n for n in names
                if os.path.isdir(os.path.join(self.root, n))]


# ---------------------------------------------------------------------------
class ProgressTracker:
    """Trends, deltas and forecasts over a list of summaries (stdlib only)."""

    IMPROVING, DECLINING, STABLE = "improving", "declining", "stable"

    def __init__(self, summaries: Sequence[AnalysisSummary]):
        self.items = sorted(list(summaries or []),
                            key=lambda s: (s.date_iso, s.analysis_id))

    # -- raw series -------------------------------------------------------
    def series(self, metric: str) -> List[Tuple[str, float]]:
        out = []
        for s in self.items:
            v = s.metric(metric)
            if v is not None:
                out.append((s.date_iso, v))
        return out

    @staticmethod
    def _linreg(values: Sequence[float]) -> Tuple[float, float]:
        """Least-squares slope + intercept over x = 0..n-1 (stdlib)."""
        n = len(values)
        if n == 0:
            return 0.0, 0.0
        if n == 1:
            return 0.0, float(values[0])
        mean_x = (n - 1) / 2.0
        mean_y = sum(values) / n
        num = sum((i - mean_x) * (v - mean_y)
                  for i, v in enumerate(values))
        den = sum((i - mean_x) ** 2 for i in range(n))
        slope = num / den if den else 0.0
        return slope, mean_y - slope * mean_x

    # -- verdicts ---------------------------------------------------------
    def trend(self, metric: str, min_rel_slope: float = 0.01) -> str:
        vals = [v for _, v in self.series(metric)]
        if len(vals) < 2:
            return self.STABLE
        slope, _ = self._linreg(vals)
        scale = abs(sum(vals) / len(vals)) or 1.0
        rel = slope * (len(vals) - 1) / scale   # total relative change
        if abs(rel) < min_rel_slope:
            return self.STABLE
        good_when_down = LOWER_IS_BETTER.get(metric, False)
        improving = (rel < 0) if good_when_down else (rel > 0)
        return self.IMPROVING if improving else self.DECLINING

    def delta_pct(self, metric: str) -> Optional[float]:
        vals = [v for _, v in self.series(metric)]
        if len(vals) < 2 or not vals[0]:
            return None
        return 100.0 * (vals[-1] - vals[0]) / abs(vals[0])

    def predict_next(self, metric: str) -> Optional[float]:
        """One-step-ahead forecast from the linear trend (None if < 2 pts)."""
        vals = [v for _, v in self.series(metric)]
        if len(vals) < 2:
            return None
        slope, intercept = self._linreg(vals)
        return slope * len(vals) + intercept

    def overall(self) -> str:
        """Majority verdict over the key metrics (SWOLF counts double)."""
        votes = []
        for metric in ("swolf", "spm", "mean_speed", "symmetry"):
            if len(self.series(metric)) >= 2:
                votes.append(self.trend(metric))
                if metric == "swolf":
                    votes.append(self.trend(metric))
        if not votes:
            return self.STABLE
        if votes.count(self.IMPROVING) > votes.count(self.DECLINING):
            return self.IMPROVING
        if votes.count(self.DECLINING) > votes.count(self.IMPROVING):
            return self.DECLINING
        return self.STABLE

    # -- human-readable reports -------------------------------------------
    def report_lines_finglish(self) -> List[str]:
        lines = ["Sessions: %d" % len(self.items)]
        if not self.items:
            return ["Hich session sabt nashode ast."]
        for metric in ("swolf", "spm", "mean_speed", "symmetry"):
            vals = [v for _, v in self.series(metric)]
            if not vals:
                continue
            name = METRIC_FINGLISH[metric]
            line = "%s: last=%.2f trend=%s" % (name, vals[-1],
                                               self.trend(metric))
            if len(vals) >= 2:
                d = self.delta_pct(metric)
                nxt = self.predict_next(metric)
                line += " delta=%+.1f%%" % d
                if nxt is not None:
                    line += " forecast=%.2f" % nxt
            lines.append(line)
        lines.append("Overall: %s" % self.overall())
        return lines

    def report_text_fa(self) -> str:
        if not self.items:
            return "هنوز جلسه‌ای برای این شناگر ثبت نشده است."
        rows = ["تعداد جلسات: %d" % len(self.items)]
        fa_verdict = {self.IMPROVING: "رو به بهبود ↑",
                      self.DECLINING: "نیازمند توجه ↓",
                      self.STABLE: "ثابت →"}
        for metric in ("swolf", "spm", "mean_speed", "symmetry"):
            vals = [v for _, v in self.series(metric)]
            if not vals:
                continue
            row = "%s: آخرین %.1f — %s" % (
                METRIC_FA[metric], vals[-1],
                fa_verdict[self.trend(metric)])
            if len(vals) >= 2:
                d = self.delta_pct(metric) or 0.0
                nxt = self.predict_next(metric)
                row += " (تغییر %+.1f%%" % d
                if nxt is not None:
                    row += "، پیش‌بینی جلسه بعد %.1f" % nxt
                row += ")"
            rows.append(row)
        rows.append("جمع‌بندی: %s" % fa_verdict[self.overall()])
        return "\n".join(rows)
