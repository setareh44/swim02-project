# -*- coding: utf-8 -*-
"""آزمون موتور تحلیل **بدون رابط کاربری** — برای پیدا کردن علت بسته‌شدن برنامه.

    python tools/diagnose_engine.py                 # ویدیوی video.mp4
    python tools/diagnose_engine.py "C:\\path\\v.mp4" --frames 40

این ابزار همان مسیر واقعی تحلیل را طی می‌کند (MediaPipe → پاک‌سازی →
بیومکانیک) ولی بدون Qt و بدون پنجره. بنابراین:
  * اگر این‌جا هم برنامه بسته شود، مشکل از MediaPipe/OpenCV است (نه از رابط
    کاربری) و آخرین خطوط در fatal.log ذخیره می‌شود.
  * اگر این‌جا سالم تمام شود ولی پنجره بسته شود، مشکل از رابط کاربری/OpenGL
    است؛ در آن حالت با run_debug.bat (حالت امن) اجرا کنید.

برای دیدن جزئیات کامل، فایل‌های کنار همین اسکریپت را ببینید:
    fatal.log ، crash_log.txt ، console.log  (در %LOCALAPPDATA%\\Setargan-Darya یا
    در همین پوشه پروژه)
"""
from __future__ import annotations

import argparse
import platform
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _say(text: str = "") -> None:
    print(text, flush=True)


def _versions() -> dict:
    out = {"python": sys.version.split()[0], "platform": platform.platform()}
    for mod in ("numpy", "cv2", "mediapipe", "PySide6", "pyqtgraph"):
        try:
            m = __import__(mod)
            out[mod] = getattr(m, "__version__", "?")
        except Exception as exc:                       # noqa: BLE001
            out[mod] = "MISSING (%s)" % exc
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Setargan-Darya engine diagnostic")
    ap.add_argument("video", nargs="?", default=str(ROOT / "video.mp4"))
    ap.add_argument("--frames", type=int, default=20,
                    help="چند فریم بررسی شود (پیش‌فرض ۲۰)")
    ap.add_argument("--model", type=int, default=1, choices=(0, 1, 2))
    args = ap.parse_args()

    # ثبت کرش نیتیو (همان مکانیزم برنامه)
    from app import diagnostics
    fatal = diagnostics.install_faulthandler()

    _say("=" * 64)
    _say("  Setargan-Darya - آزمون موتور تحلیل (بدون رابط کاربری)")
    _say("=" * 64)
    for key, value in _versions().items():
        _say("  %-10s %s" % (key, value))
    _say("  log files  %s" % diagnostics.log_dir())
    _say("  fatal log  %s" % fatal)

    # --- OpenCV: علت اصلی کرش خاموش در نسخه‌های جدید
    try:
        import cv2
        major = int(str(cv2.__version__).split(".")[0])
        if major >= 5:
            _say("\n  [WARN] OpenCV %s نصب است؛ MediaPipe با OpenCV 5 کرش می‌کند."
                 % cv2.__version__)
            _say("         راه‌حل:  run.bat را دوباره اجرا کنید (خودش تعمیر "
                 "می‌کند) یا:")
            _say("         .venv\\Scripts\\python.exe -m pip install -c "
                 "constraints.txt --force-reinstall --no-deps "
                 "\"opencv-python-headless>=4.8,<5\"")
        else:
            _say("  [ OK ] OpenCV %s (شاخهٔ 4، سازگار با MediaPipe)"
                 % cv2.__version__)
    except Exception as exc:                            # noqa: BLE001
        _say("  [FAIL] OpenCV import نشد: %s" % exc)

    video = Path(args.video)
    if not video.is_file():
        _say("\n  [FAIL] فایل ویدیو پیدا نشد: %s" % video)
        _say("         یک ویدیو به‌عنوان آرگومان بدهید.")
        return 2

    _say("\n  ویدیو: %s" % video)
    try:
        from swim_ai import Config, PoseExtractor

        _say("\n  [1/3] ساخت PoseExtractor (همین‌جا کرش‌های MediaPipe رخ "
             "می‌دهد) ...")
        cfg = Config(model_complexity=args.model, render=False)
        extractor = PoseExtractor(cfg)
        _say("        backend: %s" % getattr(extractor, "_backend", "?"))

        _say("\n  [2/3] استخراج اسکلت از %d فریم ..." % args.frames)
        pose = extractor.extract(str(video), max_frames=args.frames)
        _say("        فریم‌ها: %d  ·  نسبت تشخیص: %.0f٪"
             % (pose.n, 100 * getattr(pose, "detect_ratio", 0.0)))

        _say("\n  [3/3] اجرای پایپلاین بیومکانیک (بدون رندر) ...")
        from swim_ai import SwimAnalysisPipeline
        res = SwimAnalysisPipeline(cfg).analyze(str(video), pose_raw=pose)
        _say("        سبک: %s  ·  SPM: %.1f  ·  سرعت: %.2f m/s"
             % (res.style_final, res.strokes.spm_avg, res.perf.mean_speed))
    except Exception:                                   # noqa: BLE001
        _say("\n  [FAIL] خطای پایتون:")
        _say(traceback.format_exc())
        _say("  گزارش کامل: %s" % fatal)
        return 1

    _say("\n" + "=" * 64)
    _say("  [ OK ] موتور تحلیل سالم است.")
    _say("  اگر این آزمون سالم بود ولی پنجرهٔ برنامه بسته می‌شود، مشکل از")
    _say("  رابط کاربری/OpenGL است: با run_debug.bat (حالت امن) اجرا کنید")
    _say("  و فایل fatal.log را بفرستید.")
    _say("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
