# -*- coding: utf-8 -*-
"""ساخت تصویر دکمه‌های پخش/توقف/مکث (گوی شیشه‌ای براق با رینگ فلزی).

چرا تصویر و نه استایل Qt؟
    این دکمه‌ها گویِ براق با رینگ فلزی نقش‌دار، گرادیان شعاعی، درخشش پایین و
    بازتاب شیشه‌ای هستند. QSS در Qt گرادیان شعاعی و درخشش لبه‌ای ندارد؛ ساختن
    آن با ویجت‌های تودرتو هم کند و ناپایدار است. پس یک‌بار به تصویر تبدیل و در
    ``app/assets/media`` ذخیره می‌شوند (فایل‌ها در مخزن هستند؛ اجرای برنامه به
    Pillow نیاز ندارد).

اعداد هندسی از روی تصویر مرجع کاربر اندازه‌گیری شده‌اند (نسبت به قطر دکمه):
    ضخامت رینگ ۰.۱۱۹ · قطر گوی ۰.۷۶۲ · عرض نماد ۰.۳۰۴ · ارتفاع نماد ۰.۳۳۸
    جابه‌جایی افقی نماد ۰.۰۴۷ به راست (تراز نوری)

اجرا (فقط برای تغییر طرح):
    python tools/make_media_buttons.py
"""
from __future__ import annotations

import math
import pathlib

from PIL import Image, ImageDraw, ImageFilter

OUT = pathlib.Path(__file__).resolve().parent.parent / "app" / "assets" / "media"
SIZE = 112          # اندازهٔ نهایی فایل (۲× اندازهٔ نمایش)
SS = 4              # سوپرسمپل برای لبه‌های نرم

# --- هندسه (نسبت به قطر دکمه) ----------------------------------------------
RIM = 0.116         # ضخامت رینگ فلزی (نسبت به قطر)
GLYPH_W = 0.306     # نسبت به قطر دکمه
GLYPH_H = 0.340
GLYPH_DX = 0.047    # جابه‌جایی نوری به راست
GLYPH_R = 0.043     # شعاع گوشه‌های نماد

# --- رنگ‌ها (نمونه‌برداری‌شده از تصویر مرجع) --------------------------------
RIM_STOPS = [                     # رینگ فلزی: سفید در بالا، خاکستری در پایین
    (0.00, (252, 253, 255)),
    (0.06, (236, 236, 241)),
    (0.14, (226, 225, 231)),
    (0.30, (206, 205, 212)),
    (0.50, (163, 163, 168)),
    (0.68, (144, 143, 149)),
    (0.84, (130, 129, 134)),
    (1.00, (114, 114, 120)),
]
ORB_STOPS = [                     # پروفایل عمودی گوی، نمونه‌برداری از تصویر مرجع
    (0.00, (52, 78, 188)),
    (0.05, (73, 105, 210)),
    (0.14, (105, 143, 230)),
    (0.23, (115, 150, 233)),
    (0.32, (123, 148, 233)),
    (0.50, (134, 144, 238)),
    (0.64, (152, 139, 245)),
    (0.69, (169, 157, 251)),
    (0.74, (197, 189, 253)),
    (0.79, (229, 224, 255)),
    (0.86, (248, 247, 255)),
    (1.00, (252, 252, 255)),
]
GLYPH_TOP = (30, 42, 148)
GLYPH_BOTTOM = (34, 40, 200)


def _lerp(stops, t):
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        if a <= t <= b:
            k = (t - a) / max(b - a, 1e-9)
            return tuple(int(ca[j] + (cb[j] - ca[j]) * k) for j in range(len(ca)))
    return stops[-1][1]


def _radial(w, cx, cy, rx, ry, stops, scale):
    lay = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    px = lay.load()
    for y in range(w):
        for x in range(w):
            d = math.hypot((x / scale - cx) / rx, (y / scale - cy) / ry)
            if d > 1:
                continue
            col = _lerp(stops, d)
            px[x, y] = col if len(col) == 4 else col + (255,)
    return lay


def _inset_polygon(pts, r):
    """رأس‌های چندضلعی را به اندازهٔ ``r`` به داخل می‌برد (برای گِرد کردن گوشه‌ها)."""
    out = []
    n = len(pts)
    for i in range(n):
        a, v, b = pts[i - 1], pts[i], pts[(i + 1) % n]
        u1 = (a[0] - v[0], a[1] - v[1])
        u2 = (b[0] - v[0], b[1] - v[1])
        l1 = math.hypot(*u1) or 1.0
        l2 = math.hypot(*u2) or 1.0
        u1 = (u1[0] / l1, u1[1] / l1)
        u2 = (u2[0] / l2, u2[1] / l2)
        bis = (u1[0] + u2[0], u1[1] + u2[1])
        lb = math.hypot(*bis) or 1.0
        bis = (bis[0] / lb, bis[1] / lb)
        half = math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))) / 2
        dist = r / max(math.sin(half), 0.15)
        out.append((v[0] + bis[0] * dist, v[1] + bis[1] * dist))
    return out


def _glyph(w, c, glyph, scale, d):
    """نماد دکمه: مثلث پخش، دو ستون مکث یا مربع توقف. ``d`` = قطر دکمه."""
    def P(v):
        return int(round(v * scale))

    mask = Image.new("L", (w, w), 0)
    md = ImageDraw.Draw(mask)
    if glyph == "play":
        gw, gh = GLYPH_W * d, GLYPH_H * d
        x0 = c - gw / 2 + GLYPH_DX * d
        pts = [(x0, c - gh / 2), (x0 + gw, c), (x0, c + gh / 2)]
        r = GLYPH_R * d
        inner = _inset_polygon(pts, r)
        md.polygon([(P(x), P(y)) for (x, y) in inner], fill=255)
        # اتحاد چندضلعیِ کوچک‌شده با کپسول‌های لبه‌ها = چندضلعیِ گِردشده
        for i in range(3):
            a, b = inner[i], inner[(i + 1) % 3]
            md.line([P(a[0]), P(a[1]), P(b[0]), P(b[1])],
                    fill=255, width=max(1, P(2 * r)))
        for (vx, vy) in inner:
            md.ellipse([P(vx - r), P(vy - r), P(vx + r), P(vy + r)], fill=255)
    elif glyph == "pause":
        bw, bh, gap = 0.100 * d, 0.330 * d, 0.088 * d
        for sx in (-1, 1):
            x = c + sx * (gap / 2 + bw / 2) - bw / 2 + GLYPH_DX * d * 0.5
            md.rounded_rectangle([P(x), P(c - bh / 2), P(x + bw), P(c + bh / 2)],
                                 radius=P(0.034 * d), fill=255)
    else:                                    # stop
        s_ = 0.250 * d
        x = c - s_ / 2 + GLYPH_DX * d * 0.5
        md.rounded_rectangle([P(x), P(c - s_ / 2), P(x + s_), P(c + s_ / 2)],
                             radius=P(0.060 * d), fill=255)

    # گرادیان عمودی روی نماد (بالا تیره‌تر، پایین آبی‌تر)
    grad = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    gpx = grad.load()
    top, bot = GLYPH_TOP, GLYPH_BOTTOM
    for y in range(w):
        t = y / (w - 1)
        col = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,)
        for x in range(w):
            gpx[x, y] = col
    gl = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    gl.paste(grad, (0, 0), mask)
    return gl


def build(glyph: str, variant: str = "normal") -> Image.Image:
    w = SIZE * SS
    c = SIZE / 2

    def P(v):
        return int(round(v * SS))

    def disc(radius):
        m = Image.new("L", (w, w), 0)
        ImageDraw.Draw(m).ellipse([P(c - radius), P(c - radius),
                                   P(c + radius), P(c + radius)], fill=255)
        return m

    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))

    def add(layer, radius, keep_alpha=False):
        layer.putalpha(Image.composite(layer.getchannel("A"),
                                       Image.new("L", (w, w), 0), disc(radius)))
        img.alpha_composite(layer)

    R = 0.482 * SIZE
    rim = RIM * SIZE
    Ro = R - rim

    # ۱) سایهٔ نرم زیر دکمه
    sh = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse(
        [P(c - R * 0.98), P(c - R * 0.88 + 0.05 * SIZE),
         P(c + R * 0.98), P(c + R * 1.06 + 0.05 * SIZE)],
        fill=(2, 5, 16, 115))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(P(0.030 * SIZE))))

    # ۲) رینگ فلزی با گرادیان عمودی
    ring = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    rpx = ring.load()
    for y in range(P(c - R), P(c + R) + 1):
        t = (y / SS - (c - R)) / (2 * R)          # ۰ بالا، ۱ پایین
        base = _lerp(RIM_STOPS, min(1.0, max(0.0, t)))
        for x in range(P(c - R), P(c + R) + 1):
            d = math.hypot(x / SS - c, y / SS - c)
            if d > R:
                continue
            u = min(1.0, max(0.0, (d - Ro) / rim))   # ۰ لبهٔ داخلی، ۱ لبهٔ بیرونی
            # پروفایل مقطع رینگ: لبهٔ بیرونی روشن‌تر، سمت داخلی کمی تیره‌تر
            k = 0.88 + 0.13 * math.sin(math.pi * min(1.0, u * 1.15)) + 0.10 * u
            rpx[x, y] = tuple(max(0, min(255, int(v * k))) for v in base) + (255,)
    add(ring, R)

    outer = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    od2 = ImageDraw.Draw(outer)
    od2.ellipse([P(c - R), P(c - R), P(c + R), P(c + R)],
                outline=(188, 190, 198, 255), width=max(1, P(0.003 * SIZE)))
    od2.arc([P(c - R), P(c - R), P(c + R), P(c + R)], start=20, end=160,
            fill=(70, 70, 82, 255), width=max(1, P(0.004 * SIZE)))
    img.alpha_composite(outer)

    # ۳) نقش ستاره‌های شش‌پره روی رینگ
    orn = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    od = ImageDraw.Draw(orn)
    count = 44
    rr = R - rim * 0.50
    arm = 0.0130 * SIZE
    for i in range(count):
        a = 2 * math.pi * i / count + math.pi / count
        ox, oy = c + rr * math.cos(a), c + rr * math.sin(a)
        for k in range(3):
            ang = a + k * math.pi / 3 + math.pi / 6
            od.line([P(ox - arm * math.cos(ang)), P(oy - arm * math.sin(ang)),
                     P(ox + arm * math.cos(ang)), P(oy + arm * math.sin(ang))],
                    fill=(104, 106, 116, 255), width=max(1, P(0.0046 * SIZE)))
    add(orn, R)

    # ۴) شیار تیرهٔ داخلی رینگ
    bevel = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bevel)
    bd.ellipse([P(c - Ro), P(c - Ro), P(c + Ro), P(c + Ro)],
               outline=(52, 52, 70, 255), width=max(1, P(0.006 * SIZE)))
    bd.arc([P(c - Ro - 0.008 * SIZE), P(c - Ro - 0.008 * SIZE),
            P(c + Ro + 0.008 * SIZE), P(c + Ro + 0.008 * SIZE)],
           start=150, end=390, fill=(226, 226, 240, 255),
           width=max(1, P(0.005 * SIZE)))
    add(bevel, Ro + 0.010 * SIZE)

    # ۵) بدنهٔ گوی: گرادیان عمودی (تیره در بالا، یاسی/سفید در پایین)
    stops = [(t, tuple(col[:3]) + (255,)) for t, col in ORB_STOPS]
    orb = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    opx = orb.load()
    for y in range(P(c - Ro), P(c + Ro) + 1):
        t = (y / SS - (c - Ro)) / (2 * Ro)
        col = _lerp(stops, min(1.0, max(0.0, t)))
        for x in range(P(c - Ro), P(c + Ro) + 1):
            opx[x, y] = col
    add(orb, Ro)

    # ۶) سایهٔ نرم داخل لبهٔ بالای گوی (عمق شیشه)
    inner_shadow = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    isd = ImageDraw.Draw(inner_shadow)
    isd.arc([P(c - Ro + 0.008 * SIZE), P(c - Ro + 0.008 * SIZE),
             P(c + Ro - 0.008 * SIZE), P(c + Ro - 0.008 * SIZE)],
            start=196, end=344, fill=(26, 36, 104, 150),
            width=max(1, P(0.045 * SIZE)))
    add(inner_shadow.filter(ImageFilter.GaussianBlur(P(0.016 * SIZE))), Ro)

    # ۷) تاریکی لبه‌های چپ و راست گوی (حجم کره)
    edge = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    epx = edge.load()
    for y in range(P(c - Ro), P(c + Ro) + 1):
        for x in range(P(c - Ro), P(c + Ro) + 1):
            d = math.hypot(x / SS - c, y / SS - c) / Ro
            if d < 0.62:
                continue
            a = int(104 * min(1.0, (d - 0.60) / 0.40) ** 1.3)
            epx[x, y] = (34, 40, 120, a)
    add(edge, Ro)

    # ۸) نقطهٔ نور سفید پایین (منبع نور از پایین، مثل مرجع)
    add(_radial(w, c + 0.01 * SIZE, c + 0.36 * SIZE, 0.190 * SIZE, 0.125 * SIZE,
                [(0.0, (255, 255, 255, 226)), (0.40, (255, 255, 255, 160)),
                 (0.70, (250, 248, 255, 66)), (1.0, (248, 246, 255, 0))], SS), Ro)

    # ۹) ستون نور شیشه‌ای نیمهٔ بالا (بازتاب سقف) + بازتاب بالا-چپ
    glass = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glass)
    gd.ellipse([P(c + 0.018 * SIZE), P(c - 0.40 * SIZE),
                P(c + 0.100 * SIZE), P(c + 0.14 * SIZE)],
               fill=(255, 255, 255, 52))
    add(glass.filter(ImageFilter.GaussianBlur(P(0.017 * SIZE))), Ro)

    add(_radial(w, c - 0.19 * SIZE, c - 0.240 * SIZE, 0.135 * SIZE, 0.058 * SIZE,
                [(0.0, (255, 255, 255, 70)), (0.6, (255, 255, 255, 20)),
                 (1.0, (255, 255, 255, 0))], SS), Ro)

    # ۱۰) نماد
    img.alpha_composite(_glyph(w, c, glyph, SS, 2 * R))

    # حالت‌ها: هوور روشن‌تر، غیرفعال محوتر (روی کل تصویر، یکدست)
    if variant == "hover":
        k, desat = 1.12, 0.0
    elif variant == "disabled":
        k, desat = 0.62, 0.35
    else:
        k = 1.0
        desat = 0.0
    if k != 1.0 or desat:
        r, g, b, a = img.split()
        conv = img.convert("RGB")
        px = conv.load()
        for y in range(w):
            for x in range(w):
                cr, cg, cb = px[x, y]
                grey = 0.299 * cr + 0.587 * cg + 0.114 * cb
                cr = (cr * (1 - desat) + grey * desat) * k
                cg = (cg * (1 - desat) + grey * desat) * k
                cb = (cb * (1 - desat) + grey * desat) * k
                px[x, y] = (min(255, int(cr)), min(255, int(cg)), min(255, int(cb)))
        conv = conv.convert("RGBA")
        conv.putalpha(a)
        img = conv

    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for glyph in ("play", "pause", "stop"):
        for variant in ("normal", "hover", "disabled"):
            name = glyph if variant == "normal" else "%s_%s" % (glyph, variant)
            path = OUT / ("%s.png" % name)
            build(glyph, variant).save(path, optimize=True)
            made.append((path.name, path.stat().st_size))
    total = sum(size for _, size in made)
    for name, size in made:
        print("  %-22s %6.1f KB" % (name, size / 1024))
    print("  %d فایل، مجموع %.1f KB -> %s" % (len(made), total / 1024, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
