# -*- coding: utf-8 -*-
"""تست‌های ایستا برای اندازه و رنگ ویجت‌های رابط کاربری.

Qt در محیط توسعه این پروژه اجرا نمی‌شود (کتابخانه‌های گرافیکی نصب نیستند)،
پس اندازه/رنگ دکمه‌ها را از روی کد بررسی می‌کنیم تا تنظیم‌های درخواستی کاربر
دوباره از دست نروند:
  * دکمهٔ پخش و توقف ویدیو: بزرگ، رنگی و گِرد (نه آیکون کوچک سیاه)
  * دکمه‌های کارت گزارش: هر سه یک اندازه
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: قالب QSS داخل app/theme.py به‌صورت متن خوانده می‌شود (Qt لازم نیست)
#: در قالب، آکولادها دوتایی هستند ({{ }})
RAW_STYLE = (ROOT / "app" / "theme.py").read_text(encoding="utf-8")
QSS = RAW_STYLE.replace("{{", "{").replace("}}", "}")


def _rule(selector: str) -> str:
    """بدنهٔ یک قاعدهٔ QSS (بدون آکولادها)."""
    match = re.search(re.escape(selector) + r"\s*\{\{(.*?)\}\}",
                      RAW_STYLE, re.S)
    return match.group(1) if match else ""


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------- video player
def test_play_button_is_big_and_round():
    text = _src("app/video_player.py")
    assert 'setObjectName("playBtn")' in text
    assert "_PLAY_SIZE" in text
    size = int(re.search(r"_PLAY_SIZE\s*=\s*(\d+)", text).group(1))
    assert size >= 48, "دکمهٔ پخش باید حداقل ۴۸ پیکسل باشد"
    assert size == int(re.search(r"_STOP_SIZE\s*=\s*(\d+)", text).group(1)) or \
        size > int(re.search(r"_STOP_SIZE\s*=\s*(\d+)", text).group(1))


def test_play_and_stop_use_fixed_square_geometry():
    text = _src("app/video_player.py")
    assert "setFixedSize(_PLAY_SIZE, _PLAY_SIZE)" in text
    assert "setFixedSize(_STOP_SIZE, _STOP_SIZE)" in text


def test_media_buttons_use_the_glossy_images():
    """دکمه‌ها تصویر گویِ براق دارند، نه آیکون سادهٔ SVG."""
    text = _src("app/video_player.py")
    assert "icons.media_icon(name)" in text
    assert 'icons.media_icon("stop")' in text
    assert 'self._set_play_icon("play")' in text
    assert 'self._set_play_icon("pause")' in text
    # دیگر از آیکون‌های سادهٔ SVG برای این دکمه‌ها استفاده نمی‌شود
    assert 'styled_icon("media_stop"' not in text


def test_media_asset_files_exist_and_are_square():
    from PIL import Image  # noqa: PLC0415 - فقط برای این تست

    media = ROOT / "app" / "assets" / "media"
    for glyph in ("play", "pause", "stop"):
        for variant in ("normal", "hover", "disabled"):
            name = glyph if variant == "normal" else "%s_%s" % (glyph, variant)
            path = media / ("%s.png" % name)
            assert path.exists(), path.name
            with Image.open(path) as im:
                assert im.size == (112, 112), (path.name, im.size)
                assert im.mode == "RGBA", path.name


def test_media_images_have_the_glossy_structure():
    """گویِ براق: رینگ فلزی روشن در بالا، گوی بنفش، نماد تیره در مرکز."""
    from PIL import Image  # noqa: PLC0415

    with Image.open(ROOT / "app" / "assets" / "media" / "play.png") as im:
        im = im.convert("RGBA")
        w, h = im.size
        ring = im.getpixel((w // 2, int(h * 0.055)))   # نوک بالای رینگ
        middle = im.getpixel((w // 2 + 12, h // 2))  # بدنهٔ گوی
        glyph = im.getpixel((w // 2, h // 2))      # مرکز نماد
    assert ring[3] > 200 and min(ring[:3]) > 200, ring      # فلز روشن
    assert middle[2] > middle[0], middle                    # گوی آبی/بنفش
    assert sum(glyph[:3]) < 330, glyph                      # نماد تیره


def test_media_states_are_visibly_different():
    """هوور روشن‌تر و غیرفعال محوتر از حالت عادی باشد (سه حالتِ واقعی، نه کپی)."""
    from PIL import Image  # noqa: PLC0415

    def mean_brightness(name):
        with Image.open(ROOT / "app" / "assets" / "media" / ("%s.png" % name)) as im:
            im = im.convert("RGBA")
            vals = [sum(im.getpixel((x, y))[:3]) / 3.0
                    for y in range(im.height) for x in range(im.width)
                    if im.getpixel((x, y))[3] > 200]
        return sum(vals) / len(vals)

    normal = mean_brightness("play")
    assert mean_brightness("play_hover") > normal + 6
    assert mean_brightness("play_disabled") < normal - 25


def test_media_buttons_are_transparent_so_the_image_shows():
    rule = _rule("QPushButton#playBtn, QPushButton#stopBtn")
    assert re.search(r"background:\s*transparent", rule), rule
    assert re.search(r"border:\s*none", rule), rule


def test_theme_has_media_button_rules():
    assert "QPushButton#playBtn" in QSS
    assert "QPushButton#stopBtn" in QSS
    tail = QSS.split("QPushButton#stopBtn")[1][:200]
    assert "rgba(244, 63, 94" not in tail, "قرمز برای توقف استفاده نشود"


def test_media_button_art_can_be_regenerated():
    """ابزار ساخت تصویرها در مخزن باشد (بازتولید طرح بدون Qt)."""
    script = ROOT / "tools" / "make_media_buttons.py"
    text = script.read_text(encoding="utf-8")
    assert "def build(" in text
    assert "app" in text and "assets" in text


def test_old_small_icon_style_is_gone_from_the_player():
    text = _src("app/video_player.py")
    assert 'setObjectName("icon")\n        self.btn_play' not in text
    assert 'icons.icon("play", C.CYAN, 20)' not in text


# --------------------------------------------------------------- report page
def test_report_buttons_share_one_size():
    text = _src("app/pages/report_page.py")
    assert re.search(r"_BTN_H\s*=\s*\d+", text)
    assert re.search(r"_BTN_W\s*=\s*\d+", text)
    # هر سه دکمه در یک حلقه با اندازهٔ یکسان تنظیم می‌شوند
    block = text.split("for btn in (self.btn_pdf_color, self.btn_pdf_bw,")[1]
    block = block.split("row2.addLayout(btns")[0]
    for call in ("setFixedHeight(_BTN_H)", "setMinimumWidth(_BTN_W)",
                 "QSizePolicy.Expanding"):
        assert call in block, call
    # کشش برابر ⇒ عرض یکسان
    assert "btns.addWidget(btn, 1)" in block


def test_report_buttons_have_a_shared_font_rule():
    assert _rule('QPushButton[rp="pdf"]')
    assert 'btn.setProperty("rp", "pdf")' in _src("app/pages/report_page.py")


# ------------------------------------------------------------------- RTL use
def test_report_and_about_apply_rtl_without_waiting_for_show_events():
    assert "apply_rtl_tree(self.dyn)" in _src("app/pages/report_page.py")
    assert "self._apply_rtl()" in _src("app/about_dialog.py")


def test_log_box_stays_left_to_right():
    text = _src("app/pages/analyze_page.py")
    assert 'self.log.setProperty("keepAlign", True)' in text
    assert "self.log.setLayoutDirection(Qt.LeftToRight)" in text


# ---------------------------------------------------------------- icon colour
def test_svg_defines_color_for_currentcolor_glyphs():
    """رگرسیون: بدون ویژگی color، شکل‌های currentColor **مشکی** رسم می‌شدند."""
    text = _src("app/icons.py")
    assert 'f\'color="{color}" \'' in text
    # هر شکلی که currentColor دارد باید رنگش از همین ویژگی بیاید
    assert text.count("currentColor") >= 5


def test_media_glyphs_exist():
    text = _src("app/icons.py")
    for name in ("media_play", "media_pause", "media_stop"):
        assert '"%s"' % name in text, name
