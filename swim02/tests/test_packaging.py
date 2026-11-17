# -*- coding: utf-8 -*-
"""تست‌های ساده برای فایل‌های ساخت نسخه ویندوز.

این فایل‌ها با PyInstaller/Inno Setup اجرا می‌شوند و در محیط تست قابل اجرا
نیستند؛ ولی خرابی‌های رایج (پکیج سنگین در requirements، کاراکتر ممنوعه در
.bat، نبود آیکون) را همین‌جا می‌گیریم.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packaging"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


# --------------------------------------------------------------- requirements
def test_requirements_use_essentials_not_full_pyside6():
    text = _read(ROOT / "requirements.txt")
    pins = [ln.strip().lower() for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    joined = "\n".join(pins)
    assert "pyside6-essentials" in joined
    # bare `PySide6` pulls ~600 MB of QtWebEngine/Qt3D/QtQuick
    assert not re.search(r"^pyside6\s*$", joined, re.M)
    assert not re.search(r"^pyside6[=<>]", joined, re.M)


def test_opencv_is_pinned_below_5():
    """رگرسیون کرش: OpenCV 5 باعث بسته‌شدن خاموش MediaPipe می‌شود."""
    req = _read(ROOT / "requirements.txt")
    assert re.search(r"opencv-python-headless>=4\.8,\s*<5", req)

    constraints = _read(ROOT / "constraints.txt")
    for name in ("opencv-python", "opencv-contrib-python",
                 "opencv-python-headless", "opencv-contrib-python-headless"):
        assert re.search(r"^%s<5\s*$" % re.escape(name), constraints, re.M), \
            "%s must be capped below 5" % name


def test_launchers_pass_the_constraints_file():
    for name in ("run.bat", "run.py", "packaging/build_windows.bat"):
        text = _read(ROOT / name)
        assert "constraints.txt" in text, name


def test_requirements_have_no_heavy_unused_packages():
    text = _read(ROOT / "requirements.txt")
    names = {ln.split()[0].lower().split("=")[0].split(">")[0].split("<")[0]
             for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")}
    for banned in ("scipy", "pandas", "matplotlib", "pyside6", "opencv-contrib-python"):
        assert banned not in names, "%s should not be a direct requirement" % banned
    # opencv headless (no GUI) is what the code needs
    assert "opencv-python-headless" in names


def test_engine_does_not_import_scipy():
    src = (ROOT / "swim_ai.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import scipy|from scipy)", src, re.M)
    assert "def find_peaks(" in src


# ------------------------------------------------------------------- the spec
def test_spec_file_is_valid_python():
    import py_compile
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        py_compile.compile(str(PKG / "swim_ai.spec"),
                           cfile=str(Path(tmp) / "spec.pyc"), doraise=True)


def _exec_spec(tmp_path, monkeypatch):
    """اجرای واقعی فایل .spec با PyInstaller جعلی.

    بدون این کار، هر خطای NameError/ترتیب تعریف در .spec فقط روی کامپیوتر
    کاربر و بعد از چند دقیقه بیلد دیده می‌شد.
    """
    import sys as _sys
    import types

    seen = {"data": [], "submodules": []}

    hooks = types.ModuleType("PyInstaller.utils.hooks")

    def collect_data_files(pkg, include_py_files=False):
        seen["data"].append(pkg)
        return [("/fake/%s/data.txt" % pkg, pkg)]

    def collect_submodules(pkg):
        seen["submodules"].append(pkg)
        return ["%s.fake_submodule" % pkg]

    hooks.collect_data_files = collect_data_files
    hooks.collect_submodules = collect_submodules
    utils = types.ModuleType("PyInstaller.utils")
    utils.hooks = hooks
    pyinstaller = types.ModuleType("PyInstaller")
    pyinstaller.utils = utils
    for name, mod in (("PyInstaller", pyinstaller),
                      ("PyInstaller.utils", utils),
                      ("PyInstaller.utils.hooks", hooks)):
        monkeypatch.setitem(_sys.modules, name, mod)

    calls = {}

    def Analysis(*args, **kwargs):
        calls["analysis"] = kwargs
        calls["entry"] = args[0]
        return types.SimpleNamespace(pure=[], binaries=[], datas=[], scripts=[])

    def PYZ(*args, **kwargs):
        return "PYZ"

    def EXE(*args, **kwargs):
        calls["exe"] = kwargs
        return "EXE"

    def COLLECT(*args, **kwargs):
        calls["collect"] = kwargs
        return "COLLECT"

    glb = {
        "SPECPATH": str(PKG),
        "DISTPATH": str(tmp_path / "dist"),
        "Analysis": Analysis,
        "PYZ": PYZ,
        "EXE": EXE,
        "COLLECT": COLLECT,
        "__file__": str(PKG / "swim_ai.spec"),
        "__name__": "swim_ai_spec",
    }
    source = (PKG / "swim_ai.spec").read_text(encoding="utf-8")
    exec(compile(source, "swim_ai.spec", "exec"), glb)
    return calls, seen


def test_spec_runs_and_collects_models_and_excludes(tmp_path, monkeypatch):
    calls, seen = _exec_spec(tmp_path, monkeypatch)

    datas = calls["analysis"]["datas"]
    models = [d for d in datas if d[1] == "models"]
    assert models, "the pose models must be bundled"
    assert all(d[0].endswith(".task") for d in models)
    assert any(d[1] == "mediapipe" for d in datas)
    # the startup sound must ship with the app
    assets = [d for d in datas if d[1] == "app/assets"]
    assert any(d[0].endswith("startup.wav") for d in assets), \
        "app/assets/startup.wav must be bundled"

    assert "mediapipe" in seen["data"]
    assert "pyqtgraph" in seen["data"]
    assert "mediapipe.tasks" in seen["submodules"]

    excludes = calls["analysis"]["excludes"]
    assert "scipy" in excludes and "tkinter" in excludes
    assert calls["exe"]["console"] is False
    assert calls["exe"]["name"] == "Setargan-Darya"
    assert calls["exe"]["icon"].endswith("swim_ai.ico")
    assert calls["collect"]["name"] == "Setargan-Darya"
    assert str(PKG / "app_entry.py") in calls["entry"][0]


def test_spec_excludes_the_expensive_stuff():
    text = _read(PKG / "swim_ai.spec")
    for name in ("scipy", "tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore",
                 "PySide6.QtQml", "PySide6.QtMultimedia", "PyQt5"):
        assert '"%s"' % name in text, "%s must be excluded" % name
    # windowed build + one folder
    assert re.search(r"console\s*=\s*False", text)
    assert "COLLECT(" in text
    assert "app_entry.py" in text


def test_spec_mentions_models_and_entry_point():
    text = _read(PKG / "swim_ai.spec")
    assert "models" in text
    assert (PKG / "app_entry.py").is_file()


# ---------------------------------------------------------------- entry point
def test_app_entry_calls_the_real_main():
    src = _read(PKG / "app_entry.py")
    assert "from app.main import main" in src
    assert 'getattr(sys, "frozen", False)' in src


# ------------------------------------------------------------- batch scripts
def test_build_bat_has_no_forbidden_cmd_characters():
    raw = (PKG / "build_windows.bat").read_bytes()
    text = raw.decode("utf-8")
    # cmd.exe keeps ^ literally inside quotes and `)` breaks if-blocks
    assert "^" not in text
    # `%0`-`%9` would be expanded to the script path, so no printf-style format
    assert not re.search(r"%[0-9]", text.replace("%~dp0", ""))
    # cmd.exe wants CRLF; the .gitattributes rule guarantees it on checkout and
    # in GitHub's zip export even though the blob itself is normalised to LF.
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat text eol=crlf" in attrs
    assert b"\r" not in raw.replace(b"\r\n", b""), "stray carriage returns"


def test_build_bat_uses_project_venv_and_spec():
    text = _read(PKG / "build_windows.bat")
    assert ".venv\\Scripts\\python.exe" in text
    assert "packaging\\swim_ai.spec" in text
    assert "packaging\\installer.iss" in text


def test_build_bat_does_not_uninstall_opencv_contrib():
    text = _read(PKG / "build_windows.bat")
    assert "uninstall" not in text or "opencv-contrib-python opencv-python" not in text


# ------------------------------------------------------------ inno setup file
def test_iss_is_utf8_bom_with_persian_text():
    raw = (PKG / "installer.iss").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "Inno Setup needs a UTF-8 BOM"
    text = _read(PKG / "installer.iss")
    assert "Setargan-Darya-Setup" in text
    assert "dist\\Setargan-Darya\\*" in text or "..\\dist\\Setargan-Darya\\*" in text


def test_diagnose_bat_is_safe_and_uses_the_venv():
    raw = (ROOT / "diagnose.bat").read_bytes()
    text = raw.decode("utf-8")
    assert "^" not in text
    assert ".venv\\Scripts\\python.exe" in text
    assert "tools\\diagnose_engine.py" in text
    # cmd.exe هر دو حالت LF و CRLF را می‌خواند؛ فقط نباید قاطی باشد
    assert raw.count(b"\r\n") in (0, raw.count(b"\n"))
    assert text.lower().count("pause") >= 1


def test_selftest_bat_is_safe_and_runs_the_ui_check():
    raw = (ROOT / "selftest.bat").read_bytes()
    text = raw.decode("utf-8")
    assert "^" not in text
    # پیام‌های بت باید انگلیسی/ASCII باشند تا به codepage وابسته نباشند
    assert text.isascii()
    assert "tools\\selftest_ui.py" in text
    assert text.lower().count("pause") >= 1
    # کنسول UTF-8 شود تا متن فارسی پایتون درست دیده شود
    assert "chcp 65001" in text


def test_selftest_script_never_crashes_on_a_broken_environment():
    """این ابزار عیب‌یابی است؛ خودش نباید Traceback خام بدهد."""
    text = _read(ROOT / "tools" / "selftest_ui.py")
    assert "def check(" in text
    assert "except BaseException" in text


def test_iss_icon_exists():
    text = _read(PKG / "installer.iss")
    icon = re.search(r"SetupIconFile\s*=\s*(\S+)", text)
    assert icon, "SetupIconFile is required"
    assert (PKG / icon.group(1)).is_file()


def test_icon_is_a_valid_ico():
    data = (PKG / "swim_ai.ico").read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00"
    count = int.from_bytes(data[4:6], "little")
    assert count >= 4, "multi-size icon expected"
    assert len(data) > 2000


# ----------------------------------------------------------------- the guide
def test_size_guide_documents_the_numbers():
    text = _read(ROOT / "docs" / "build_windows_fa.md")
    assert "PySide6-Essentials" in text
    assert "1.5" in text.replace("۱.۵", "1.5") or "۱.۵" in text
    assert "dist\\Setargan-Darya" in text
    assert "%LOCALAPPDATA%" in text


def test_media_button_images_are_shipped_in_the_build():
    """تصویرهای گویِ براق باید در بستهٔ ویندوز هم کپی شوند."""
    spec = (ROOT / "packaging" / "swim_ai.spec").read_text(encoding="utf-8")
    assert 'media_dir = assets_dir / "media"' in spec
    assert '"app/assets/media"' in spec
    media = ROOT / "app" / "assets" / "media"
    assert sorted(p.name for p in media.glob("*.png")) == [
        "pause.png", "pause_disabled.png", "pause_hover.png",
        "play.png", "play_disabled.png", "play_hover.png",
        "stop.png", "stop_disabled.png", "stop_hover.png",
    ]
