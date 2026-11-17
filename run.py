#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ریشه مخزن: فقط اجرا را به پوشه اصلی پروژه (swim02/) می‌سپارد.

پروژه واقعی (app/‎، tools/‎، models/‎) داخل پوشه swim02/ است؛ این فایل فقط
وارد آن پوشه می‌شود و لانچر واقعی را اجرا می‌کند، پس فرقی نمی‌کند
`run.bat` ریشه یا `swim02\\run.bat` را دابل‌کلیک کنید — نتیجه یکی است.
"""
from __future__ import annotations

import os
import runpy
import sys


def _project_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "swim02")


def main() -> int:
    target = _project_dir()
    os.chdir(target)
    if target not in sys.path:
        sys.path.insert(0, target)
    sys.argv[0] = os.path.join(target, "run.py")
    runpy.run_path(os.path.join(target, "run.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
