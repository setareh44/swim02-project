# -*- coding: utf-8 -*-
"""
پس‌زمینه متحرک استخر با OpenGL (GLSL 330 core):
گرادیان عمیق اقیانوسی + کاستیک‌های متحرک نور + پرتوهای نور + حباب + vignette.
اگر بستر OpenGL در دسترس نباشد، به‌طور خودکار نسخه QPainter جایگزین می‌شود.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QTimer, Qt, Signal
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPen,
                           QRadialGradient)
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from . import branding, gl_render

try:
    from OpenGL import GL  # noqa: F401  (در صورت نصب pyOpenGL)
except Exception:  # pragma: no cover
    GL = None


VERT = """
#version 330 core
layout (location = 0) in vec2 a_pos;
out vec2 v_uv;
void main() {
    v_uv = a_pos * 0.5 + 0.5;
    gl_Position = vec4(a_pos, 0.0, 1.0);
}
"""

FRAG = """
#version 330 core
in vec2 v_uv;
out vec4 frag;
uniform float u_time;
uniform vec2  u_res;

// امواج سینوسی لایه‌ای برای شبیه‌سازی کاستیک نور زیر آب
float caustics(vec2 uv, float t) {
    vec2 p = uv * 6.0;
    float c = 0.0;
    c += sin(p.x * 1.3 + t * 0.9);
    c += sin(p.y * 1.7 - t * 1.1);
    c += sin((p.x + p.y) * 1.1 + t * 0.6);
    vec2 m = vec2(sin(t * 0.35), cos(t * 0.28)) * 2.2;
    c += sin(length(p - m) * 1.6 - t * 1.25);
    c += sin(length(p + m * 0.7) * 2.1 + t * 0.8);
    return pow(max(0.0, 0.5 + c * 0.18), 3.2);
}

float haze(vec2 uv, vec2 c, float k) {
    float d = distance(uv, c);
    return 1.0 - smoothstep(0.0, k, d);
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_res.xy;
    float t = u_time;

    // گرادیان پایه‌ی اعماق
    vec3 top    = vec3(0.035, 0.135, 0.245);
    vec3 mid    = vec3(0.020, 0.085, 0.165);
    vec3 bottom = vec3(0.008, 0.030, 0.065);
    vec3 col = mix(bottom, mid, smoothstep(0.0, 0.62, uv.y));
    col = mix(col, top, smoothstep(0.55, 1.0, uv.y));

    // هاله‌های نور متحرک
    vec2 g1 = vec2(0.72 + 0.08 * sin(t * 0.22), 0.78 + 0.05 * cos(t * 0.17));
    vec2 g2 = vec2(0.22 + 0.07 * cos(t * 0.19), 0.30 + 0.06 * sin(t * 0.27));
    col += vec3(0.05, 0.42, 0.55) * haze(uv, g1, 0.62) * 0.30;
    col += vec3(0.10, 0.28, 0.65) * haze(uv, g2, 0.55) * 0.22;

    // کاستیک‌ها (در نیمه بالایی قوی‌ترند)
    float ca = caustics(uv + vec2(t * 0.015, t * 0.01), t);
    col += vec3(0.10, 0.62, 0.72) * ca * (0.10 + 0.16 * uv.y);

    // پرتوهای نور مورب
    float rays = 0.0;
    for (int i = 0; i < 4; i++) {
        float fi = float(i);
        float x = fract(0.22 * fi + t * 0.018);
        float band = exp(-pow((uv.x - x + (1.0 - uv.y) * 0.10) * 9.0, 2.0));
        rays += band * (0.05 + 0.04 * sin(t * 0.7 + fi));
    }
    col += vec3(0.45, 0.78, 0.92) * rays * smoothstep(0.05, 0.95, uv.y) * 0.16;

    // حباب‌های بالارونده
    for (int i = 0; i < 14; i++) {
        float fi = float(i);
    float sx = fract(0.137 * fi * fi + 0.31 * fi);
        float speed = 0.018 + 0.010 * fract(fi * 0.61);
        float by = fract(uv.y * 0.0 + t * speed + fi * 0.173);
        float bx = fract(sx + 0.012 * sin(t * 0.9 + fi * 1.7));
        vec2 bc = vec2(bx, 1.0 - by);
        float r = 0.0035 + 0.0025 * fract(fi * 0.37);
        float b = 1.0 - smoothstep(r, r * 2.6, distance(uv, bc));
        col += vec3(0.55, 0.85, 0.95) * b * 0.22;
    }

    // vignette
    float vig = 1.0 - 0.55 * smoothstep(0.35, 0.95,
                                        distance(uv, vec2(0.5, 0.55)));
    col *= vig;

    // نویز بسیار ملایم برای جلوگیری از باندینگ
    float grain = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233)))
                        * 43758.5453) * 0.012;
    col += grain;

    frag = vec4(col, 1.0);
}
"""


class _GLCanvas(QOpenGLWidget):
    failed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ok = False
        self._failed_emitted = False
        self._t0 = time.monotonic()
        self._program = QOpenGLShaderProgram(self)
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self._loc_time = -1
        self._loc_res = -1
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update)

    def initializeGL(self):
        try:
            if not self.context().isValid():
                raise RuntimeError("invalid GL context")
            if not self._program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERT):
                raise RuntimeError("vertex shader: " + self._program.log())
            if not self._program.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAG):
                raise RuntimeError("fragment shader: " + self._program.log())
            if not self._program.link():
                raise RuntimeError("link: " + self._program.log())
            self._loc_time = self._program.uniformLocation("u_time")
            self._loc_res = self._program.uniformLocation("u_res")
            verts = [-1.0, -1.0, 3.0, -1.0, -1.0, 3.0]
            import numpy as np
            data = np.array(verts, dtype="float32").tobytes()
            self._vbo.create()
            self._vbo.bind()
            self._vbo.allocate(data, len(data))
            self._ok = True
            self._timer.start()
        except Exception:
            self._fail()

    def _fail(self) -> None:
        """توقف رندر GL و اعلام یک‌باره به والد برای سوئیچ به QPainter.

        بدون این محافظ، هر خطا در paintGL هر ۳۳ میلی‌ثانیه تکرار می‌شد و
        پنجره با انبوه پیام خطا عملاً غیرقابل استفاده می‌شد.
        """
        self._ok = False
        try:
            self._timer.stop()
        except Exception:
            pass
        if not self._failed_emitted:
            self._failed_emitted = True
            self.failed.emit()

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if self._ok:
            self._timer.start()

    def paintGL(self):
        if not self._ok:
            return
        try:
            gl_render.paint(self.context().functions(), self._program,
                            self._vbo, self.width(), self.height(),
                            time.monotonic() - self._t0,
                            self._loc_time, self._loc_res)
        except Exception:
            # درایور/کتابخانه نمی‌تواند این صحنه را رسم کند؛ نسخه نرم‌افزاری
            self._fail()


class _PainterCanvas(QWidget):
    """نسخه جایگزین نرم‌افزاری پس‌زمینه (بدون نیاز به OpenGL)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t0 = time.monotonic()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        self._timer.start()

    def paintEvent(self, _):
        t = time.monotonic() - self._t0
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor("#0a2845"))
        g.setColorAt(0.55, QColor("#06172c"))
        g.setColorAt(1.0, QColor("#030b16"))
        p.fillRect(self.rect(), g)

        # هاله‌های نور
        for i, (cx, cy, r, col) in enumerate((
            (0.72, 0.72, 0.62, QColor(34, 211, 238, 38)),
            (0.20, 0.30, 0.55, QColor(56, 120, 248, 34)),
            (0.50, 0.92, 0.50, QColor(45, 212, 191, 26)),
        )):
            gx = cx + 0.05 * math.sin(t * 0.25 + i * 2.1)
            gy = cy + 0.04 * math.cos(t * 0.2 + i * 1.7)
            rg = QRadialGradient(QPointF(gx * w, gy * h), r * max(w, h))
            rg.setColorAt(0.0, col)
            rg.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), rg)

        # خطوط موجی کاستیک
        pen = QPen(QColor(70, 200, 230, 26))
        pen.setWidthF(1.4)
        p.setPen(pen)
        for layer in range(5):
            path = []
            base_y = h * (0.12 + layer * 0.17)
            amp = 10 + layer * 2
            for x in range(0, w + 8, 8):
                y = base_y + amp * math.sin(x * 0.012 + t * (0.7 + layer * 0.12)
                                            + layer * 1.9)
                path.append((x, y))
            for i in range(1, len(path)):
                p.drawLine(int(path[i - 1][0]), int(path[i - 1][1]),
                           int(path[i][0]), int(path[i][1]))

        # حباب‌ها
        p.setBrush(QColor(150, 220, 245, 45))
        p.setPen(Qt.NoPen)
        for i in range(14):
            sx = ((0.137 * i * i + 0.31 * i) % 1.0)
            speed = 0.02 + 0.01 * ((i * 0.61) % 1.0)
            by = (t * speed + i * 0.173) % 1.0
            bx = (sx + 0.012 * math.sin(t * 0.9 + i * 1.7)) % 1.0
            r = 3.0 + 2.0 * ((i * 0.37) % 1.0)
            p.drawEllipse(QPointF(bx * w, (1.0 - by) * h), r, r)

        # vignette
        rg = QRadialGradient(QPointF(w * 0.5, h * 0.55),
                             max(w, h) * 0.75)
        rg.setColorAt(0.55, QColor(0, 0, 0, 0))
        rg.setColorAt(1.0, QColor(0, 0, 0, 120))
        p.fillRect(self.rect(), rg)
        p.end()


def gl_available() -> bool:
    """پروِب سبک برای سنجش امکان ساخت کانتکست OpenGL.

    با متغیر محیطی SETARGAN_NO_GL=1 می‌توان اجباراً رندر نرم‌افزاری را فعال کرد
    (برای درایورهای گرافیکی ناسازگار). هر خطایی به معنی «در دسترس نبودن» است.
    """
    if branding.gl_disabled():
        return False
    try:
        from PySide6.QtGui import QOpenGLContext
        ctx = QOpenGLContext()
        ok = bool(ctx.create())
        del ctx
        return ok
    except Exception:
        return False


class PoolBackground(QWidget):
    """کانتینر پس‌زمینه: نسخه GL در صورت امکان، وگرنه رندر نرم‌افزاری."""

    def __init__(self, parent=None, force_software: bool = False):
        super().__init__(parent)
        self.canvas = None
        if not force_software and gl_available():
            try:
                self.canvas = _GLCanvas(self)
                self.canvas.failed.connect(self._switch_software)
            except Exception:
                # ساخت ویجت GL روی برخی درایورها ممکن است crash کند؛
                # بی‌سروصدا به رندر نرم‌افزاری برمی‌گردیم.
                self.canvas = None
        if self.canvas is None:
            self.canvas = _PainterCanvas(self)

    def _switch_software(self):
        old = self.canvas
        self.canvas = _PainterCanvas(self)
        self.canvas.resize(self.size())
        self.canvas.show()
        old.deleteLater()

    def pause(self) -> None:
        """توقف انیمیشن پس‌زمینه (در حین تحلیل، برای آزادکردن GPU/CPU)."""
        try:
            if hasattr(self.canvas, "pause"):
                self.canvas.pause()
        except Exception:
            pass

    def resume(self) -> None:
        try:
            if hasattr(self.canvas, "resume"):
                self.canvas.resume()
        except Exception:
            pass

    def resizeEvent(self, e):
        if self.canvas is not None:
            self.canvas.resize(self.size())
        super().resizeEvent(e)
