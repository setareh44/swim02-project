# -*- coding: utf-8 -*-
"""تست ایستا برای خطاهای ساخت ویجت.

چرا این تست لازم است؟
    یک بار در `MainWindow.__init__` اشتباهاً ``PoolBackground(fl)`` نوشته شد
    که ``fl`` یک *چیدمان* (QVBoxLayout) است، نه ویجت. خطای Qt در زمان اجرا
    رخ داد و برنامه اصلاً باز نشد:

        TypeError: 'QWidget.__init__' called with wrong argument types

    چون Qt در محیط تست در دسترس نیست، این اشتباه فقط روی کامپیوتر کاربر
    دیده می‌شد. این فایل با تحلیل کد (AST) همان اشتباه را قبل از انتشار
    پیدا می‌کند: هیچ ویجتی نباید یک چیدمان را به‌عنوان والد بگیرد.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: کلاس‌هایی که نمونهٔ آن‌ها «چیدمان» است و هرگز نمی‌تواند والدِ ویجت باشد
LAYOUT_CTORS = {
    "QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout",
    "QStackedLayout", "QBoxLayout", "QLayout", "QGraphicsGridLayout",
    "QGraphicsLinearLayout",
}

SKIP_DIRS = {".venv", "venv", "build", "dist", "__pycache__", ".git",
             "node_modules", "packaging"}

#: متدهایی که بعضی کلاس‌های Qt **ندارند** ولی شبیه بقیه به نظر می‌رسند.
#: (QPlainTextEdit هیچ setAlignment ندارد؛ QLabel و QTextEdit دارند.)
MISSING_METHODS = {
    "QPlainTextEdit": {"setAlignment", "alignment"},
    "QProgressBar": {"setWordWrap"},
}


def _python_files():
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _ctor_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return ""


def _walk_no_defs(node: ast.AST):
    """پیمایش یک محدوده، بدون وارد شدن به بدنهٔ توابع/کلاس‌های تودرتو."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef, ast.Lambda)):
                continue
            stack.append(child)


def _scope_nodes(stmts: list[ast.stmt]) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    for stmt in stmts:
        nodes.extend(_walk_no_defs(stmt))
    return nodes


def _layout_names(body: list[ast.stmt]) -> set[str]:
    """نام متغیرهایی که در همین محدوده از یک سازندهٔ چیدمان ساخته می‌شوند."""
    names: set[str] = set()
    for node in _scope_nodes(body):
        if isinstance(node, ast.Assign):
            if _ctor_name(node.value) in LAYOUT_CTORS:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
                    elif isinstance(target, ast.Attribute):
                        names.add(target.attr)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if _ctor_name(node.value) in LAYOUT_CTORS:
                if isinstance(node.target, ast.Name):
                    names.add(node.target.id)
    return names


def _bad_calls(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    scopes = [("module", tree.body)]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes.append((node.name, node.body))

    for scope, body in scopes:
        layouts = _layout_names(body)
        if not layouts:
            continue
        for node in _scope_nodes(body):
            if not isinstance(node, ast.Call):
                continue
            name = _ctor_name(node)
            if not name or not name[0].isupper():
                continue        # تابع‌ها و متدها مهم نیستند
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id in layouts:
                    problems.append(
                        "%s:%d  %s(...) در %s/%s() یک چیدمان (%s) گرفته است"
                        % (path.relative_to(ROOT), node.lineno, name,
                           path.name, scope, arg.id))
    return problems


def test_no_widget_is_constructed_with_a_layout():
    problems: list[str] = []
    for path in _python_files():
        try:
            problems.extend(_bad_calls(path))
        except SyntaxError as exc:              # pragma: no cover
            problems.append("%s: %s" % (path, exc))
    assert not problems, "والدِ ویجت اشتباه است:\n" + "\n".join(problems)


def _names_from_classes(body: list[ast.stmt], classes: set[str]) -> set[str]:
    """نام متغیرها/صفاتی که از سازندهٔ یکی از this کلاس‌ها ساخته می‌شوند."""
    names: set[str] = set()
    for node in _scope_nodes(body):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is None or _ctor_name(value) not in classes:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else \
                [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Attribute):
                    names.add(target.attr)
    return names


def _bad_method_calls(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    scopes = [("module", tree.body)]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes.append((node.name, node.body))

    for scope, body in scopes:
        for cls, methods in MISSING_METHODS.items():
            names = _names_from_classes(body, {cls})
            if not names:
                continue
            for node in _scope_nodes(body):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute):
                    continue
                if func.attr not in methods:
                    continue
                owner = func.value
                owner_name = None
                if isinstance(owner, ast.Name):
                    owner_name = owner.id
                elif isinstance(owner, ast.Attribute):
                    owner_name = owner.attr
                if owner_name in names:
                    problems.append(
                        "%s:%d  %s.%s() وجود ندارد  (%s/%s())"
                        % (path.relative_to(ROOT), node.lineno, owner_name,
                           func.attr, path.name, scope))
    return problems


def test_no_call_to_a_method_the_widget_does_not_have():
    """رگرسیون: QPlainTextEdit.setAlignment وجود ندارد و برنامه را کرش می‌کرد."""
    problems: list[str] = []
    for path in _python_files():
        try:
            problems.extend(_bad_method_calls(path))
        except SyntaxError as exc:              # pragma: no cover
            problems.append("%s: %s" % (path, exc))
    assert not problems, "فراخوانی متد ناموجود:\n" + "\n".join(problems)


def test_background_is_created_once_with_a_widget():
    """`PoolBackground` باید فقط یک بار و با یک ویجت ساخته شود."""
    src = (ROOT / "app" / "main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _ctor_name(node) == "PoolBackground"
    ]
    assert len(calls) == 1, "PoolBackground باید فقط یک بار ساخته شود (%d بار)" \
        % len(calls)
    arg = calls[0].args[0]
    assert isinstance(arg, ast.Name) and arg.id == "content", \
        "PoolBackground باید با ویجت content ساخته شود، نه %s" % ast.dump(arg)


def test_main_window_init_does_not_build_the_background():
    src = (ROOT / "app" / "main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    window = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
    init = next(node for node in window.body
                if isinstance(node, ast.FunctionDef) and node.name == "__init__")
    # فقط بررسی می‌کنیم که داخل __init__ هیچ فراخوانی PoolBackground نیست
    calls = [n for n in ast.walk(init)
             if isinstance(n, ast.Call) and _ctor_name(n) == "PoolBackground"]
    assert not calls, "ساخت پس‌زمینه باید در _build_body باشد، نه __init__"


def test_main_retries_without_opengl_when_the_window_fails():
    """اگر ساخت پنجره شکست خورد، برنامه یک بار در حالت نرم‌افزاری باز می‌شود."""
    text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "def _build_window(" in text
    assert 'os.environ["SWIM_NO_GL"] = "1"' in text
    assert "win = _build_window(MainWindow)" in text
