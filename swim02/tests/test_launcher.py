# -*- coding: utf-8 -*-
"""Launcher regression tests: `python run.py` must survive a bare interpreter."""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run as launcher  # noqa: E402


def test_venv_python_path_is_platform_aware():
    exe = launcher._venv_python()
    if sys.platform.startswith("win"):
        assert exe.name == "python.exe"
        assert exe.parent.name == "Scripts"
    else:
        assert exe.name == "python"
        assert exe.parent.name == "bin"


def test_candidate_interpreters_include_supported_versions():
    cands = [" ".join(c) for c in launcher._candidate_interpreters()]
    for ver in ("3.14", "3.13", "3.12", "3.11", "3.10"):
        assert any(ver in c for c in cands), ver


def test_version_check_accepts_312_and_rejects_315():
    """The check must say yes for 3.12 and no for 3.15 (evaluated for real)."""
    # evaluate the expression itself for each version
    for version, expected in (((3, 12), 0), ((3, 10), 0), ((3, 14), 0),
                              ((3, 15), 1), ((3, 9), 1)):
        expr = launcher.VERSION_CHECK.split("raise SystemExit(")[1].rsplit(")", 1)[0]
        expr = expr.replace("sys.version_info[:2]", repr(version))
        assert eval(expr, {}) == expected, version


def test_missing_dependency_message_points_at_run_bat(capsys):
    rc = launcher._missing_dependency(ModuleNotFoundError("PySide6"))
    out = capsys.readouterr().out
    assert rc == 1
    assert "run.bat" in out
    assert "PySide6" in out


def test_bad_python_message_has_exact_install_command(capsys):
    rc = launcher._bad_python()
    out = capsys.readouterr().out
    assert rc == 1
    assert "winget install -e --id Python.Python.3.12" in out


def test_run_bat_prefers_existing_venv_and_never_needs_venv_activate():
    text = (ROOT / "run.bat").read_text(encoding="utf-8")
    # the launcher must reuse an existing environment before hunting for python
    assert text.index('if exist "%VPY%"') < text.index("where python")
    # and it must call the venv interpreter directly (no activate/PATH magic)
    assert '"%VPY%" run.py' in text
    assert "activate.bat" not in text
    # no unescaped parentheses inside echo lines that would break cmd parsing
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("echo") and ("(" in stripped or ")" in stripped):
            pytest.fail("unescaped parenthesis in echo line: %r" % line)


def test_run_bat_uses_crlf_line_endings_or_lf_only():
    raw = (ROOT / "run.bat").read_bytes()
    # mixing line endings confuses cmd.exe label parsing
    assert b"\r\n" not in raw or b"\n" not in raw.replace(b"\r\n", b"")


def test_run_debug_delegates_to_run_bat():
    text = (ROOT / "run_debug.bat").read_text(encoding="utf-8")
    assert 'call "%~dp0run.bat" --safe' in text


def test_run_bat_version_check_is_shared_with_run_py():
    """The same check string is used by run.bat and run.py."""
    text = (ROOT / "run.bat").read_text(encoding="utf-8")
    vcheck = launcher.VERSION_CHECK
    assert vcheck in text


def test_run_bat_never_escapes_with_caret():
    """رگرسیون: cmd.exe کاراکتر ^ را داخل کوتیشن‌ها عینا نگه می‌دارد.

    نسخه قبلی از  ^<=  استفاده می‌کرد و در نتیجه رشته پایتون به
    SyntaxError می‌رسید؛ همه نسخه‌های نصب‌شده (حتی ۳.۱۲) رد می‌شدند.
    """
    text = (ROOT / "run.bat").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.lstrip().lower().startswith("rem"):
            continue
        assert "^" not in line, "caret escape found: %r" % line


def test_version_check_uses_membership_test_without_comparisons():
    check = launcher.VERSION_CHECK
    for ch in "<>^&|%":
        assert ch not in check, ch
    assert "sys.version_info[:2] in" in check


def test_supported_versions_prefer_312():
    assert launcher.SUPPORTED_VERSIONS[0] == "3.12"
    assert set(launcher.SUPPORTED_VERSIONS) == {"3.10", "3.11", "3.12",
                                                "3.13", "3.14"}


def test_windows_candidates_cover_standard_install_folders(monkeypatch):
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\u\AppData\Local")
    cands = [" ".join(c) for c in launcher._candidate_interpreters()]
    joined = " | ".join(cands)
    assert "py -3.12" in joined
    assert "Python312" in joined          # default per-user install folder
    assert cands[-1] == "python"          # PATH fallback stays last


def test_launcher_defines_no_unreachable_helpers():
    src = (ROOT / "run.py").read_text(encoding="utf-8")
    for name in ("_bootstrap_venv", "_relaunch", "_install_deps",
                 "_find_supported_interpreter", "_has_deps"):
        assert re.search(r"def %s\(" % name, src), name


# ---------------------------------------------------------------------------
# main() control flow: the launcher must re-use an existing .venv instead of
# importing the app with the (bare) interpreter the user happens to run.
# ---------------------------------------------------------------------------
def test_main_reexecs_into_existing_venv(monkeypatch, tmp_path):
    fake_py = tmp_path / "python"
    fake_py.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    calls = {}

    monkeypatch.setattr(launcher, "_venv_python", lambda: fake_py)
    monkeypatch.setattr(launcher, "_is_supported", lambda exe: True)
    monkeypatch.setattr(launcher, "_has_deps", lambda exe: True)
    def _fake_relaunch(exe):
        calls["exe"] = exe
        return 0

    monkeypatch.setattr(launcher, "_relaunch", _fake_relaunch)

    rc = launcher.main()
    assert rc == 0
    assert calls["exe"] == fake_py


def test_main_bootstraps_when_no_venv(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "_venv_python", lambda: tmp_path / "missing")
    monkeypatch.setattr(launcher, "_bootstrap_venv", lambda: 7)
    monkeypatch.delenv(launcher.REEXEC_FLAG, raising=False)
    assert launcher.main() == 7


def test_main_installs_deps_into_existing_venv(monkeypatch, tmp_path):
    fake_py = tmp_path / "python"
    fake_py.write_text("", encoding="utf-8")
    installed = []
    monkeypatch.setattr(launcher, "_venv_python", lambda: fake_py)
    monkeypatch.setattr(launcher, "_is_supported", lambda exe: True)
    monkeypatch.setattr(launcher, "_has_deps", lambda exe: False)
    monkeypatch.setattr(launcher, "_install_deps",
                        lambda exe: installed.append(exe) or True)
    monkeypatch.setattr(launcher, "_relaunch", lambda exe: 0)

    assert launcher.main() == 0
    assert installed == [fake_py]


def test_bootstrap_without_any_python_reports_steps(monkeypatch, capsys):
    monkeypatch.setattr(launcher, "_find_supported_interpreter", lambda: None)
    rc = launcher._bootstrap_venv()
    out = capsys.readouterr().out
    assert rc == 1
    assert "winget install -e --id Python.Python.3.12" in out
    assert "run.bat" in out


def test_windows_console_fix_never_raises():
    """Must be safe on every platform (no-op outside Windows)."""
    launcher._fix_windows_console()
