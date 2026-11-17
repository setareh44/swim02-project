#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ریشه مخزن: فقط اجرا را به پوشه اصلی پروژه (swim02/) می‌سپارد.

`python doctor.py` از ریشه یا از داخل swim02/ — هر دو همین بررسی محیط
(Setargan-Darya doctor) را اجرا می‌کنند.
"""
from __future__ import annotations

import os
import runpy
import sys


def main() -> int:
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "swim02")
    os.chdir(target)
    if target not in sys.path:
        sys.path.insert(0, target)
    sys.argv[0] = os.path.join(target, "doctor.py")
    runpy.run_path(os.path.join(target, "doctor.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
