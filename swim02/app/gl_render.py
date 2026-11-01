# -*- coding: utf-8 -*-
"""پل باریک بین کد ما و توابع OpenGL.

چرا این فایل جدا شده است؟
    PySide6 کلاس ``QOpenGLFunctions`` را ارائه می‌دهد ولی **ثابت‌های GL**
    (مثل ``GL_COLOR_BUFFER_BIT``) را ندارد؛ این‌ها در C++ از ``qopengl.h``
    می‌آیند و در پایتون تعریف نشده‌اند. استفاده از
    ``QOpenGLFunctions.GL_COLOR_BUFFER_BIT`` باعث می‌شود در هر فریم
    ``AttributeError`` رخ دهد و پس‌زمینه هرگز رسم نشود.

راه‌حل: مقدارهای عددی استاندارد OpenGL به‌صورت ثابت اینجا تعریف شده‌اند
(همان اعدادی که در ``GL/gl.h`` آمده‌اند) و اگر PyOpenGL نصب باشد از آن
خوانده می‌شوند. تابع ``paint`` هم هیچ وابستگی‌ای به PySide6 ندارد تا
بتوان بدون ساخت پنجره تستش کرد.
"""
from __future__ import annotations

from typing import Any

try:  # اگر PyOpenGL نصب باشد، از منبع رسمی استفاده می‌کنیم
    from OpenGL import GL as _GL
except Exception:  # pragma: no cover - مسیر معمول روی ویندوز
    _GL = None


def _const(name: str, default: int) -> int:
    value = getattr(_GL, name, None) if _GL is not None else None
    return int(value) if isinstance(value, int) else default


# مقادیر استاندارد OpenGL (gl.h)
GL_COLOR_BUFFER_BIT = _const("GL_COLOR_BUFFER_BIT", 0x4000)
GL_FLOAT = _const("GL_FLOAT", 0x1406)
GL_TRIANGLES = _const("GL_TRIANGLES", 0x0004)


def paint(functions: Any, program: Any, vbo: Any, width: int, height: int,
          time_s: float, u_time: int = -1, u_res: int = -1) -> None:
    """رسم یک مثلث تمام‌صفحه (فقط با ثابت‌های عددی).

    ``functions`` همان چیزی است که ``QOpenGLContext.functions()`` برمی‌گرداند؛
    هر شیئی که متدهای ``glViewport/glClearColor/glClear/glDrawArrays`` را
    داشته باشد پذیرفته می‌شود (برای تست با mock). ``u_time`` و ``u_res``
    مختصات uniform هستند (وقتی ‎-1 باشند یعنی shader آن‌ها را ندارد).
    """
    functions.glViewport(0, 0, int(width), int(height))
    functions.glClearColor(0.01, 0.04, 0.09, 1.0)
    functions.glClear(GL_COLOR_BUFFER_BIT)
    program.bind()
    vbo.bind()
    program.enableAttributeArray(0)
    program.setAttributeBuffer(0, GL_FLOAT, 0, 2)
    program.setUniformValue1f(u_time, float(time_s))
    program.setUniformValue2f(u_res, float(width), float(height))
    functions.glDrawArrays(GL_TRIANGLES, 0, 3)
    program.disableAttributeArray(0)
    program.release()
    vbo.release()
