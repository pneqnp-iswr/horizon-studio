"""Render the desktop shell icons and splash images from the original pixel-art mark.

The mark and wordmark come from ``scripts/render_branding.py`` (run that first). Tauri needs RGBA PNGs and a Windows .ico at compile time, so
the outputs are committed; run this after changing the mark. Requires Pillow.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pixelart import hex_rgb  # noqa: E402
from render_branding import mark  # noqa: E402

OUT = ROOT / "desktop" / "icons"
SPLASH = ROOT / "desktop" / "splash"
WORDMARK = ROOT / "assets" / "branding" / "horizon-studio-wordmark.svg"
PNG_SIZES = {"32x32.png": 32, "64x64.png": 64, "128x128.png": 128, "128x128@2x.png": 256, "icon.png": 512}
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def base_image() -> Image.Image:
    canvas = mark()
    image = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
    for y in range(canvas.height):
        for x in range(canvas.width):
            color = canvas.get(x, y)
            if color is not None:
                image.putpixel((x, y), (*hex_rgb(color), 255))
    return image


def main() -> int:
    image = base_image()
    SPLASH.mkdir(parents=True, exist_ok=True)
    image.resize((128, 128), Image.NEAREST).save(SPLASH / "mark.png", optimize=True)
    # The splash is bundled separately from assets/, so it carries a byte-identical copy.
    (SPLASH / "wordmark.svg").write_bytes(WORDMARK.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in PNG_SIZES.items():
        image.resize((size, size), Image.NEAREST).save(OUT / name, optimize=True)
    largest = image.resize((256, 256), Image.NEAREST)
    largest.save(OUT / "icon.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print("wrote", ", ".join(sorted([*PNG_SIZES, "icon.ico"])), "to", OUT.relative_to(ROOT),
          "and the splash mark and wordmark")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
