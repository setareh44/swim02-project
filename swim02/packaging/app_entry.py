# -*- coding: utf-8 -*-
"""Entry point for the frozen (PyInstaller) build.

The launcher ``run.py`` is intentionally *not* used here: it manages virtual
environments, which a bundled executable does not need.
"""
from __future__ import annotations

import os
import sys


def _fix_paths() -> None:
    if not getattr(sys, "frozen", False):
        return
    # When the user double-clicks the .exe, the current directory is often
    # C:\Windows\System32; work from the folder that holds the executable.
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    try:
        os.chdir(exe_dir)
    except OSError:
        pass


def main() -> int:
    _fix_paths()
    from app.main import main as app_main
    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
