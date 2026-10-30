#!/usr/bin/env python3
"""Render Horizon Studio's original pixel-art banner and mark.

    python scripts/render_branding.py           # write assets/branding/*
    python scripts/render_branding.py --check   # fail if committed files are stale

Every pixel is placed by this script (fixed seeds, no external images or fonts).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pixelart import BAYER, PALETTE as P, Canvas, Rng, png_scanlines  # noqa: E402

OUT = ROOT / "assets" / "branding"
BANNER_W, BANNER_H, BANNER_SCALE = 400, 120, 4


# -- scene pieces ------------------------------------------------------------

def sky(c: Canvas):
    bands = [(0, P["void"]), (22, P["night"]), (46, P["night2"]), (70, P["night3"]), (94, P["dusk"])]
    for index, (top, color) in enumerate(bands):
        bottom = bands[index + 1][0] if index + 1 < len(bands) else c.height
        c.rect(0, top, c.width, bottom - top, color)
        if index + 1 < len(bands):
            # Ordered-dither the seam so bands melt into each other.
            nxt = bands[index + 1][1]
            for step in range(4):
                c.dither_band(0, bottom - 4 + step, c.width, 1, nxt, 3 + step * 3)


def glow(c: Canvas, cx: int, cy: int, radius: int, color: str, strength: int, only: set[str] | None = None):
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            d2 = (x - cx) ** 2 + ((y - cy) * 1.6) ** 2
            if d2 > radius * radius:
                continue
            level = int(strength * (1 - (d2 ** 0.5) / radius))
            if BAYER[y % 4][x % 4] < level and (only is None or c.get(x, y) in only):
                c.set(x, y, color)


def stars(c: Canvas, rng: Rng, count: int, avoid: tuple[int, int, int, int]):
    ax, ay, aw, ah = avoid
    tones = [P["stone3"], P["stone3"], P["stone4"], P["muted"], P["cyan2"], P["gold2"]]
    placed = 0
    while placed < count:
        x, y = rng.below(c.width), rng.below(78)
        if ax <= x < ax + aw and ay <= y < ay + ah and rng.below(4):
            continue
        c.set(x, y, tones[rng.below(len(tones))])
        placed += 1
    for x, y, color in ((214, 9, P["gold2"]), (382, 14, P["cyan2"]), (176, 6, P["cyan3"]), (343, 70, P["gold3"])):
        c.set(x, y, P["ink"])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c.set(x + dx, y + dy, color)


def ridge(c: Canvas, rng: Rng, base: int, amplitude: int, color: str, crest: str | None = None):
    heights = [0.0] * (c.width + 1)
    step = 64
    for x in range(0, c.width + 1, step):
        heights[x] = rng.below(amplitude * 10) / 10
    while step > 1:
        half = step // 2
        for x in range(half, c.width + 1, step):
            left, right = heights[x - half], heights[min(x + half, c.width)]
            jitter = (rng.below(1000) / 1000 - 0.5) * amplitude * step / 64
            heights[x] = (left + right) / 2 + jitter
        step = half
    for x in range(c.width):
        top = base - int(heights[x])
        c.rect(x, top, 1, c.height - top, color)
        if crest and rng.below(3) == 0:
            c.set(x, top, crest)


def iso_cube(c: Canvas, x: int, y: int, size: int, top: str, left: str, right: str, edge: str | None = None):
    """Isometric cube whose top corner is at (x, y); ``size`` is the half width."""
    h = size // 2
    for row in range(size):  # top rhombus
        half = row if row <= h else size - row
        half = min(half * 2, size)
        c.rect(x - half, y + row, half * 2 + 1, 1, top)
    for col in range(size + 1):  # side faces
        span = size
        c.rect(x - size + col, y + h + col // 2, 1, span - col // 2 + (col // 2), left)
        c.rect(x + size - col, y + h + col // 2, 1, span - col // 2 + (col // 2), right)
    c.rect(x - size, y + h, 1, size, left)
    if edge:
        c.line(x - size, y + h, x, y + size, edge)
        c.line(x, y + size, x + size, y + h, edge)
        c.line(x, y + size, x, y + size * 2 - 1, edge)


VOXEL = 4

# Voxel materials: (light-side colour, dark-side colour, highlight, shadow).
MATERIALS = {
    "grass": (P["moss2"], P["moss1"], P["moss3"], P["moss0"]),
    "dirt": (P["dirt2"], P["dirt1"], P["gold0"], P["dirt0"]),
    "stone": (P["stone2"], P["stone1"], P["stone3"], P["stone0"]),
    "deep": (P["stone1"], P["stone0"], P["stone2"], P["void"]),
}


def voxel(c: Canvas, x: int, y: int, material: str, lit: bool, rng: Rng, ore: str | None = None):
    base_light, base_dark, high, shade = MATERIALS[material]
    base = base_light if lit else base_dark
    c.rect(x, y, VOXEL, VOXEL, base)
    c.rect(x, y, VOXEL, 1, high if lit else base_light)
    c.rect(x + VOXEL - 1, y + 1, 1, VOXEL - 1, shade)
    c.rect(x, y + VOXEL - 1, VOXEL - 1, 1, shade)
    if material == "grass":
        c.rect(x, y + 2, VOXEL - 1, 1, P["dirt2"] if lit else P["dirt1"])
        if rng.below(2):
            c.set(x + rng.below(3), y + 3, P["moss1"])
    elif ore:
        c.set(x + 1, y + 1, ore)
        c.set(x + 2, y + 2, ore)
    elif rng.below(4) == 0:
        c.set(x + 1 + rng.below(2), y + 1 + rng.below(2), shade)


def island(c: Canvas, rng: Rng, cx: int, top: int, columns: int, rows: int, ores: bool = True) -> int:
    """Floating voxel island; returns the y of its grass surface."""
    left = cx - columns * VOXEL // 2
    for col in range(columns):
        t = (col + 0.5) / columns * 2 - 1
        reach = max(1, int(rows * (1 - abs(t) ** 1.6)) + (rng.below(2) if abs(t) < 0.9 else 0))
        x = left + col * VOXEL
        lit = t < 0.25
        for row in range(reach):
            y = top + row * VOXEL
            material = "grass" if row == 0 else "dirt" if row < 2 else "stone" if row < rows - 2 else "deep"
            ore = None
            if ores and material in ("stone", "deep") and rng.below(9) == 0:
                ore = P["cyan2"] if rng.below(3) else P["gold2"]
            voxel(c, x, y, material, lit, rng, ore)
        bottom = top + reach * VOXEL
        if reach > 2 and rng.below(3) == 0:  # hanging roots
            for y in range(bottom, bottom + 2 + rng.below(6)):
                c.set(x + 1 + rng.below(2), y, P["moss0"] if rng.below(2) else P["dirt0"])
    return top


def hut(c: Canvas, x: int, ground: int):
    """Small stone-and-timber workshop with a lit window and smoking chimney."""
    wall_top = ground - 12
    c.rect(x, wall_top, 20, 12, P["stone2"])
    for row in range(wall_top + 2, ground, 3):
        c.rect(x, row, 20, 1, P["stone1"])
        offset = 0 if (row // 3) % 2 else 3
        for bx in range(x + offset, x + 20, 6):
            c.set(bx, row - 1, P["stone1"])
            c.set(bx, row - 2, P["stone1"])
    c.rect(x, wall_top, 1, 12, P["stone3"])
    c.rect(x + 19, wall_top, 1, 12, P["stone1"])
    c.rect(x + 3, wall_top + 3, 5, 4, P["gold1"])
    c.rect(x + 4, wall_top + 4, 3, 2, P["gold3"])
    c.rect(x + 5, wall_top + 3, 1, 4, P["gold0"])
    c.rect(x + 12, wall_top + 4, 5, 8, P["dirt0"])
    c.rect(x + 12, wall_top + 4, 5, 1, P["dirt2"])
    c.set(x + 15, wall_top + 8, P["gold2"])
    for row in range(10):  # roof
        half = row + 1
        c.rect(x + 10 - half, wall_top - 10 + row, half * 2, 1, P["dirt2"] if row % 2 else P["dirt1"])
        c.set(x + 10 - half, wall_top - 10 + row, P["gold1"])
        c.set(x + 9 + half, wall_top - 10 + row, P["dirt0"])
    c.rect(x - 1, wall_top - 1, 22, 1, P["dirt0"])
    c.rect(x + 14, wall_top - 13, 3, 6, P["stone3"])
    c.rect(x + 16, wall_top - 13, 1, 6, P["stone1"])
    for i, (sx, sy) in enumerate(((15, -16), (16, -19), (15, -22), (17, -25))):
        c.set(x + sx, wall_top + sy, P["stone3"] if i < 2 else P["stone2"])
    c.dither_band(x + 1, wall_top + 7, 6, 4, P["gold0"], 4)  # window light on the wall


def furnace(c: Canvas, x: int, ground: int):
    top = ground - 10
    c.rect(x, top, 11, 10, P["stone2"])
    c.rect(x, top, 11, 1, P["stone3"])
    c.rect(x + 10, top + 1, 1, 9, P["stone1"])
    c.rect(x + 3, top + 4, 5, 4, P["void"])
    c.rect(x + 3, top + 6, 5, 2, P["ember"])
    c.rect(x + 4, top + 5, 3, 2, P["ember2"])
    c.set(x + 5, top + 6, P["gold3"])
    c.rect(x + 1, top - 4, 3, 4, P["stone2"])
    c.set(x + 2, top - 6, P["ember2"])
    c.set(x + 1, top - 8, P["stone3"])


TREE = [
    "....lll....",
    "..llLLLll..",
    ".lLLLLLLml.",
    "lLLLLLLmmml",
    "lLLLLmmmmml",
    ".lLmmmmmdl.",
    "..ldmmmdl..",
    "....ddd....",
    ".....t.....",
    ".....t.....",
    "....tTt....",
]

ANVIL = [
    ".hhhhhhhhhh..",
    "hsssssssssshh",
    ".dssssssssd..",
    "...dsssd.....",
    "....ssd......",
    "...hsssd.....",
    "..dssssssd...",
]

PORTAL = [
    "..ooooooo..",
    ".oOvvvvvOo.",
    "oOvVcVVvvOo",
    "oOvVVcVcvOo",
    "oOvcVVVVvOo",
    "oOvVVVcVvOo",
    "oOvVcVVVvOo",
    "oOvVVVVcvOo",
    "oOvvVcVVvOo",
    "oOvvvvvvvOo",
    "ooooooooooo",
]


def inspector_panel(c: Canvas, x: int, y: int):
    w, h = 50, 41
    c.rect(x, y, w, h, P["night2"])
    c.frame(x, y, w, h, P["stone2"])
    c.rect(x + 1, y + 1, w - 2, 5, P["stone1"])
    for i, color in enumerate((P["red"], P["gold2"], P["moss3"])):
        c.rect(x + 3 + i * 4, y + 3, 2, 1, color)
    c.rect(x + 18, y + 3, 16, 1, P["stone3"])
    rows = [(P["muted"], 14, P["gold2"], 12), (P["muted"], 10, P["cyan2"], 18), (P["muted"], 16, P["moss3"], 8)]
    for i, (label, lw, value, vw) in enumerate(rows):
        ry = y + 10 + i * 7
        c.rect(x + 4, ry, lw, 1, P["stone3"])
        c.rect(x + 24, ry - 1, 22, 3, P["stone0"])
        c.rect(x + 25, ry, vw, 1, value)
    c.rect(x + 4, y + 32, 42, 5, P["stone0"])
    c.frame(x + 4, y + 32, 42, 5, P["stone2"])
    c.rect(x + 6, y + 34, 26, 1, P["cyan1"])
    c.rect(x + 31, y + 33, 3, 3, P["cyan3"])


def moon(c: Canvas, cx: int, cy: int, r: int):
    """Crescent moon lit from the upper left, matching the scene's light."""
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                continue
            if (x - cx - 4) ** 2 + (y - cy + 2) ** 2 <= (r - 1) ** 2:
                continue
            edge = (x - cx) ** 2 + (y - cy) ** 2 > (r - 1.5) ** 2
            c.set(x, y, P["stone4"] if edge else P["ink"] if x < cx - 3 else P["muted"])
    c.set(cx - 5, cy + 1, P["stone4"])
    c.set(cx - 3, cy + 5, P["stone4"])


def gizmo(c: Canvas, x: int, y: int):
    c.line(x, y, x, y - 15, P["moss3"])
    c.sprite(x - 2, y - 18, ["..#..", ".###.", "#####"], {"#": P["moss3"]})
    c.line(x, y, x + 15, y + 7, P["ember"])
    c.sprite(x + 14, y + 5, ["##.", "###", "##."], {"#": P["ember"]})
    c.line(x, y, x - 15, y + 7, P["cyan2"])
    c.sprite(x - 16, y + 5, [".##", "###", ".##"], {"#": P["cyan2"]})
    c.rect(x - 1, y - 1, 3, 3, P["ink"])


def selection_brackets(c: Canvas, x: int, y: int, w: int, h: int, color: str):
    for bx, by, dx, dy in ((x, y, 1, 1), (x + w - 1, y, -1, 1), (x, y + h - 1, 1, -1), (x + w - 1, y + h - 1, -1, -1)):
        c.rect(min(bx, bx + dx * 3), by, 4, 1, color)
        c.rect(bx, min(by, by + dy * 3), 1, 4, color)


def title_block(c: Canvas, x: int, y: int):
    for d, color in ((2, P["dirt0"]), (1, P["gold0"])):
        c.text(x + d, y + d, "HORIZON", color, scale=3)
    c.text(x, y, "HORIZON", P["gold2"], scale=3, highlight=P["gold3"])
    for d, color in ((2, P["void"]), (1, P["cyan0"])):
        c.text(x + d, y + 27 + d, "STUDIO", color, scale=3)
    c.text(x, y + 27, "STUDIO", P["cyan2"], scale=3, highlight=P["cyan3"])
    ay = y + 55
    c.rect(x, ay, 112, 1, P["stone2"])
    c.rect(x, ay, 40, 1, P["gold1"])
    c.rect(x + 40, ay, 30, 1, P["cyan1"])
    c.sprite(x + 110, ay - 2, ["..#..", ".#A#.", "#AAA#", ".#A#.", "..#.."], {"#": P["gold1"], "A": P["gold3"]})
    c.text(x, ay + 6, "BUILD WORLDS. CREATE SYSTEMS.", P["ink"])
    c.text(x, ay + 15, "SHAPE THE IMPOSSIBLE.", P["ink"])
    chip = "UNOFFICIAL · OPEN SOURCE · ALPHA"
    cw = Canvas.text_width(chip)
    c.rect(x, ay + 27, cw + 8, 11, P["night2"])
    c.frame(x, ay + 27, cw + 8, 11, P["stone2"])
    c.text(x + 4, ay + 29, chip, P["muted"])


def banner() -> Canvas:
    c = Canvas(BANNER_W, BANNER_H)
    rng = Rng(20261030)
    sky(c)
    glow(c, 300, 66, 70, P["dusk2"], 9)
    stars(c, rng, 95, (12, 14, 190, 96))
    glow(c, 181, 22, 16, P["night3"], 6, only={P["void"], P["night"]})
    moon(c, 181, 22, 8)
    ridge(c, rng, 100, 18, P["night3"], P["dusk"])
    glow(c, 300, 92, 60, P["dusk"], 7, only={P["night3"]})
    ridge(c, rng, 112, 10, P["forest"], P["moss0"])
    c.rect(0, 117, c.width, 3, P["void"])
    c.dither_band(0, 114, c.width, 3, P["void"], 8)

    # Portal on its own rock, far right: worlds still to come.
    island(c, rng, 371, 98, 7, 3, ores=False)
    c.sprite(366, 87, PORTAL, {"o": P["stone1"], "O": P["stone3"], "v": P["violet1"], "V": P["violet0"], "c": P["violet2"]})
    glow(c, 371, 92, 13, P["violet1"], 5, only={P["night3"], P["dusk"], P["night2"], P["dusk2"]})

    # Main island: the workshop.
    ground = island(c, rng, 300, 82, 28, 6)
    for col in range(3):  # a raised mound for the tree
        voxel(c, 250 + col * VOXEL, ground - VOXEL, "grass", True, rng)
    c.sprite(247, ground - VOXEL - 11, TREE, {"l": P["moss1"], "L": P["moss2"], "m": P["moss1"], "d": P["moss0"],
                                              "t": P["dirt1"], "T": P["dirt2"]})
    hut(c, 264, ground)
    c.sprite(290, ground - 7, ANVIL, {"h": P["stone4"], "s": P["stone2"], "d": P["stone1"]})
    furnace(c, 320, ground)
    glow(c, 325, ground - 4, 9, P["gold0"], 4, only={P["night3"], P["dusk"], P["dusk2"], P["night2"]})
    # Light rising from the forged block to the edited block.
    for y in range(46, ground - 12):
        level = 2 + (y - 46) // 6
        for x in range(293, 305):
            if BAYER[y % 4][x % 4] < level:
                c.set(x, y, P["gold0"] if (x + y) % 3 else P["gold1"])
    iso_cube(c, 299, ground - 13, 5, P["gold3"], P["gold2"], P["gold1"])
    for sx, sy in ((291, ground - 15), (308, ground - 18), (303, ground - 23), (286, ground - 11), (312, ground - 12)):
        c.set(sx, sy, P["gold2"])

    # The block being edited, with transform gizmo, selection and its inspector.
    inspector_panel(c, 213, 16)
    c.line(263, 36, 281, 36, P["cyan1"], dash=2)
    iso_cube(c, 299, 22, 12, P["cyan2"], P["cyan1"], P["cyan0"], P["cyan3"])
    c.rect(296, 27, 7, 1, P["cyan3"])
    selection_brackets(c, 283, 18, 33, 32, P["gold2"])
    gizmo(c, 299, 34)

    title_block(c, 18, 16)
    c.rect(0, 0, c.width, 1, P["stone1"])
    c.rect(0, c.height - 1, c.width, 1, P["stone1"])
    return c


def mark() -> Canvas:
    """32x32 app mark: a block rising over the horizon."""
    c = Canvas(32, 32, P["night"])
    for y in range(32):
        c.dither_band(0, y, 32, 1, P["night3"], 16 - y // 2)
    for radius, color in ((13, P["gold1"]), (11, P["gold2"])):  # rising sun behind the block
        for y in range(19 - radius, 20):
            for x in range(16 - radius, 17 + radius):
                if (x - 16) ** 2 + (y - 19) ** 2 <= radius * radius:
                    c.set(x, y, color)
    c.rect(0, 20, 32, 12, P["moss0"])
    c.rect(0, 20, 32, 1, P["moss3"])
    c.rect(0, 21, 32, 1, P["moss2"])
    c.dither_band(0, 24, 32, 8, P["forest"], 8)
    iso_cube(c, 16, 8, 8, P["cyan2"], P["cyan1"], P["cyan0"], P["cyan3"])
    c.frame(0, 0, 32, 32, P["stone2"])
    return c


# -- output -------------------------------------------------------------------

def wordmark() -> Canvas:
    """One-line pixel wordmark for the editor and the desktop splash: HORIZON in gold, STUDIO in cyan."""
    gap = 4
    c = Canvas(Canvas.text_width("HORIZON") + gap + Canvas.text_width("STUDIO") + 1, 8)
    c.text(0, 0, "HORIZON", P["gold2"], shadow=P["dirt0"], highlight=P["gold3"])
    c.text(Canvas.text_width("HORIZON") + gap, 0, "STUDIO", P["cyan2"], shadow=P["void"], highlight=P["cyan3"])
    return c


def outputs() -> dict[str, tuple[Canvas, int, str, str]]:
    return {
        "horizon-studio-banner": (banner(), BANNER_SCALE, "Horizon Studio",
                                  "Original pixel-art banner: a floating voxel workshop where a glowing block is forged "
                                  "and a selected cube floats with transform handles beside an inspector panel. "
                                  "Tagline: Build worlds. Create systems. Shape the impossible. Unofficial, open source, alpha."),
        "horizon-studio-mark": (mark(), 8, "Horizon Studio mark",
                                "Pixel-art mark: a cyan block rising in front of a golden sun on a green horizon."),
        "horizon-studio-wordmark": (wordmark(), 4, "Horizon Studio",
                                    "Pixel wordmark: HORIZON in gold, STUDIO in cyan."),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Fail if committed images differ from a fresh render")
    args = parser.parse_args(argv)
    stale = []
    for name, (canvas, scale, title, desc) in outputs().items():
        svg = canvas.to_svg(scale, title, desc)
        svg_path, png_path = OUT / f"{name}.svg", OUT / f"{name}.png"
        if args.check:
            if not svg_path.is_file() or svg_path.read_text(encoding="utf-8") != svg:
                stale.append(svg_path)
            if not png_path.is_file() or png_scanlines(png_path.read_bytes())[2] != canvas.png_scanlines(scale):
                stale.append(png_path)
            continue
        OUT.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(svg, encoding="utf-8", newline="\n")
        png_path.write_bytes(canvas.to_png(scale))
        print(f"wrote {svg_path.relative_to(ROOT)} ({len(svg)} bytes) and {png_path.name}")
    if stale:
        print("Stale branding images (run python scripts/render_branding.py):", *stale, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
