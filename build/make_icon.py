"""Generate the BoseCtl application icon.

Produces ``build/icon.ico`` (multi-resolution, 16-256 px) plus
``build/icon.png`` for docs and the About page. Supersampling at 1024 px
and downsampling with LANCZOS gives clean antialiased edges at small sizes,
which a hand-placed pixel glyph cannot.

Requires Pillow (``pip install pillow``, or ``.[dev]``). Run from the repo
root::

    python build/make_icon.py
"""

from __future__ import annotations

import os
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - build-time dependency
    sys.exit("Pillow is required: pip install pillow")

SUPER = 1024
SIZES = (16, 24, 32, 48, 64, 128, 256)

# Brand ramp: a slightly deeper blue at the bottom reads as a lit surface
# instead of a flat swatch at 16 px.
TOP = (58, 122, 245)
BOTTOM = (27, 74, 196)
GLYPH = (255, 255, 255)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def _gradient(size, top, bottom):
    """A vertical linear gradient, one row at a time."""
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        t = y / max(1, size - 1)
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (size, y)], fill=row)
    return image


def _rounded_mask(size, radius):
    """Antialiased rounded-square alpha mask, drawn at 4x then reduced."""
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size * scale - 1, size * scale - 1],
        radius=radius * scale, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def _draw_glyph(image):
    """Draw a white headphone: a headband arc plus two ear cups."""
    draw = ImageDraw.Draw(image)
    s = image.size[0]

    def px(value):
        return int(round(value / 1024 * s))

    # Headband. Pillow angles run clockwise from 3 o'clock, so 180->360 is
    # the top half of the circle.
    band_box = [px(248), px(268), px(776), px(796)]
    draw.arc(band_box, start=180, end=360, fill=GLYPH, width=px(84))
    # Round off the two open ends of the arc so the band does not look cut.
    for cx in (px(248), px(776)):
        r = px(42)
        draw.ellipse([cx - r, px(532) - r, cx + r, px(532) + r], fill=GLYPH)

    # Ear cups.
    for cx in (px(248), px(776)):
        w, h, r = px(148), px(250), px(52)
        draw.rounded_rectangle(
            [cx - w // 2, px(506), cx + w // 2, px(506) + h],
            radius=r, fill=GLYPH)
    return image


def build_icon():
    """Return a 1024 px RGBA master image."""
    base = _gradient(SUPER, TOP, BOTTOM).convert("RGBA")
    base.putalpha(_rounded_mask(SUPER, radius=224))
    _draw_glyph(base)
    return base


def main():
    master = build_icon()

    png_path = os.path.join(OUT_DIR, "icon.png")
    master.resize((256, 256), Image.LANCZOS).save(png_path, optimize=True)
    print("wrote", png_path)

    ico_path = os.path.join(OUT_DIR, "icon.ico")
    # Pillow's ICO writer resizes the *source* image once per requested size,
    # so `sizes` alone is the whole mechanism. Passing appending frames as
    # well (the GIF/TIFF idiom) makes it emit a single 16 px image, which
    # looks fine until Windows scales it up in the taskbar.
    master.save(ico_path, format="ICO",
                sizes=[(size, size) for size in SIZES])
    print("wrote %s (%s)" % (ico_path, ", ".join("%dpx" % s for s in SIZES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
