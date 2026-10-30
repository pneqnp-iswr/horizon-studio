"""Deterministic pixel-art toolkit for Horizon Studio branding and roadmap images.

Standard library only. Pictures are drawn on a logical pixel grid and written
as SVG (one path per colour, pixels merged into rectangles, crisp edges) or as
an RGB PNG scaled with nearest-neighbour sampling. The same input always gives
the same SVG text and the same PNG pixels. All glyphs and palettes here are
original to this project.
"""
from __future__ import annotations

import struct
import zlib

# Palette: see docs/branding/DESIGN_SYSTEM.md.
PALETTE = {
    "void": "#06080c", "night": "#0a0e15", "night2": "#0e141d", "night3": "#131b27", "dusk": "#1a2433",
    "dusk2": "#222e40",
    "stone0": "#1d232c", "stone1": "#2b333e", "stone2": "#3e4755", "stone3": "#5a6472", "stone4": "#7f8999",
    "forest": "#122319", "moss0": "#1c3826", "moss1": "#2c5a36", "moss2": "#467f43", "moss3": "#79b257",
    "dirt0": "#2e2119", "dirt1": "#4a3424", "dirt2": "#6b4a30",
    "gold0": "#7a4e12", "gold1": "#c48a24", "gold2": "#f0bd4a", "gold3": "#fff0b5",
    "cyan0": "#0c4a5a", "cyan1": "#1f9fbd", "cyan2": "#58dcef", "cyan3": "#d2fbff",
    "violet0": "#2d1f4d", "violet1": "#5d3f99", "violet2": "#9a78e0",
    "ember": "#e0662c", "ember2": "#ff9a4d", "red": "#d94a4a",
    "ink": "#e8edf4", "muted": "#9aa6b6", "faint": "#5f6b7b",
}

# Original 5x7 capitals, digits and punctuation ('#' = ink). Widths vary per glyph.
_GLYPHS = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#",
    "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.",
    "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####",
    "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.####",
    "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": "###|.#.|.#.|.#.|.#.|.#.|###",
    "J": "..###|...#.|...#.|...#.|...#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#",
    "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#",
    "N": "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
    "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#",
    "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.",
    "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.",
    "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..",
    "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.",
    "1": ".#.|##.|.#.|.#.|.#.|.#.|###",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####",
    "3": "####.|....#|....#|.###.|....#|....#|####.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.",
    "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": "..##.|.#...|#....|####.|#...#|#...#|.###.",
    "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.",
    "9": ".###.|#...#|#...#|.####|....#|...#.|.##..",
    " ": "..|..|..|..|..|..|..",
    ".": ".|.|.|.|.|.|#",
    ",": "..|..|..|..|..|.#|#.",
    ":": ".|.|#|.|.|#|.",
    "-": "...|...|...|###|...|...|...",
    "/": "....#|...#.|...#.|..#..|.#...|.#...|#....",
    "&": ".##..|#..#.|#.#..|.#...|#.#.#|#..#.|.##.#",
    "'": "#|#|.|.|.|.|.",
    "!": "#|#|#|#|#|.|#",
    "?": ".###.|#...#|....#|...#.|..#..|.....|..#..",
    "+": ".....|..#..|..#..|#####|..#..|..#..|.....",
    "%": "##..#|##..#|...#.|..#..|.#...|#..##|#..##",
    "(": ".#|#.|#.|#.|#.|#.|.#",
    ")": "#.|.#|.#|.#|.#|.#|#.",
    "#": ".#.#.|.#.#.|#####|.#.#.|#####|.#.#.|.#.#.",
    ">": "#...|.#..|..#.|...#|..#.|.#..|#...",
    "<": "...#|..#.|.#..|#...|.#..|..#.|...#",
    "=": "....|....|####|....|####|....|....",
    "|": "#|#|#|#|#|#|#",
    "·": ".|.|.|#|.|.|.",
}
FONT = {char: [row for row in rows.split("|")] for char, rows in _GLYPHS.items()}
GLYPH_HEIGHT = 7


def hex_rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


class Rng:
    """xorshift32: fixed sequence on every Python version and platform."""

    def __init__(self, seed: int):
        self.state = (seed & 0xFFFFFFFF) or 0x9E3779B9

    def next(self) -> int:
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x
        return x

    def below(self, n: int) -> int:
        return self.next() % n


# 4x4 ordered-dither thresholds (0..15).
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


class Canvas:
    def __init__(self, width: int, height: int, fill: str | None = None):
        if width < 1 or height < 1:
            raise ValueError("Canvas needs a positive size")
        self.width, self.height = width, height
        self.px: list[list[str | None]] = [[fill] * width for _ in range(height)]

    # -- drawing -----------------------------------------------------------
    def set(self, x: int, y: int, color: str | None):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.px[y][x] = color

    def get(self, x: int, y: int) -> str | None:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.px[y][x]
        return None

    def rect(self, x: int, y: int, w: int, h: int, color: str):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, color)

    def frame(self, x: int, y: int, w: int, h: int, color: str):
        self.rect(x, y, w, 1, color)
        self.rect(x, y + h - 1, w, 1, color)
        self.rect(x, y, 1, h, color)
        self.rect(x + w - 1, y, 1, h, color)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: str, dash: int = 0):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err, step = dx + dy, 0
        while True:
            if not dash or (step // dash) % 2 == 0:
                self.set(x0, y0, color)
            if x0 == x1 and y0 == y1:
                return
            step += 1
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def sprite(self, x: int, y: int, rows: list[str], colors: dict[str, str]):
        """Stamp rows of characters; characters missing from ``colors`` are transparent."""
        for dy, row in enumerate(rows):
            for dx, char in enumerate(row):
                if char in colors:
                    self.set(x + dx, y + dy, colors[char])

    def dither_band(self, x: int, y: int, w: int, h: int, color: str, level: int):
        """Cover ``level``/16 of the area with ``color`` using the Bayer pattern."""
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if BAYER[yy % 4][xx % 4] < level:
                    self.set(xx, yy, color)

    def recolor(self, x: int, y: int, w: int, h: int, mapping: dict[str, str]):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                current = self.get(xx, yy)
                if current in mapping:
                    self.set(xx, yy, mapping[current])

    # -- text --------------------------------------------------------------
    @staticmethod
    def text_width(text: str, scale: int = 1, spacing: int = 1) -> int:
        widths = [len(FONT[ch][0]) for ch in text.upper()]
        return (sum(widths) + spacing * max(len(widths) - 1, 0)) * scale

    def text(self, x: int, y: int, text: str, color: str, scale: int = 1, spacing: int = 1,
             shadow: str | None = None, highlight: str | None = None) -> int:
        """Draw text; ``highlight`` recolours each glyph's top row, ``shadow`` drops one pixel."""
        if shadow:
            self.text(x + scale, y + scale, text, shadow, scale, spacing)
        cursor = x
        for ch in text.upper():
            if ch not in FONT:
                raise ValueError(f"No pixel glyph for {ch!r}")
            glyph = FONT[ch]
            for gy, row in enumerate(glyph):
                ink = highlight if (highlight and gy == 0) else color
                for gx, cell in enumerate(row):
                    if cell == "#":
                        self.rect(cursor + gx * scale, y + gy * scale, scale, scale, ink)
            cursor += (len(glyph[0]) + spacing) * scale
        return cursor - x - spacing * scale

    # -- output ------------------------------------------------------------
    def rectangles(self) -> dict[str, list[tuple[int, int, int, int]]]:
        """Pixels grouped by colour into rectangles (rows of equal runs merged)."""
        found: dict[str, list[tuple[int, int, int, int]]] = {}
        open_runs: dict[tuple[int, int, str], list[int]] = {}
        for y in range(self.height + 1):
            runs = []
            if y < self.height:
                row, x = self.px[y], 0
                while x < self.width:
                    color = row[x]
                    end = x + 1
                    while end < self.width and row[end] == color:
                        end += 1
                    if color is not None:
                        runs.append((x, end - x, color))
                    x = end
            still_open = {}
            for run in runs:
                rect = open_runs.pop(run, None)
                if rect is None:
                    rect = [run[0], y, run[1], 0]
                rect[3] += 1
                still_open[run] = rect
            for (_, _, color), rect in open_runs.items():
                found.setdefault(color, []).append(tuple(rect))
            open_runs = still_open
        return {color: sorted(rects, key=lambda r: (r[1], r[0])) for color, rects in sorted(found.items())}

    def to_svg(self, scale: int, title: str, description: str) -> str:
        def esc(value: str) -> str:
            return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width * scale}" height="{self.height * scale}" '
            f'viewBox="0 0 {self.width} {self.height}" shape-rendering="crispEdges" role="img" '
            f'aria-labelledby="title desc">',
            f'<title id="title">{esc(title)}</title>',
            f'<desc id="desc">{esc(description)}</desc>',
        ]
        for color, rects in self.rectangles().items():
            path = "".join(f"M{x} {y}h{w}v{h}h-{w}z" for x, y, w, h in rects)
            parts.append(f'<path fill="{color}" d="{path}"/>')
        parts.append("</svg>")
        return "\n".join(parts) + "\n"

    def png_scanlines(self, scale: int, background: str = "#000000") -> bytes:
        rows = []
        for y in range(self.height):
            line = bytearray(b"\x00")
            for x in range(self.width):
                line += bytes(hex_rgb(self.px[y][x] or background)) * scale
            rows.extend([bytes(line)] * scale)
        return b"".join(rows)

    def to_png(self, scale: int, background: str = "#000000") -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        header = struct.pack(">IIBBBBB", self.width * scale, self.height * scale, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                + chunk(b"IDAT", zlib.compress(self.png_scanlines(scale, background), 9)) + chunk(b"IEND", b""))


def png_scanlines(data: bytes) -> tuple[int, int, bytes]:
    """Width, height and raw scanlines of a PNG written by :meth:`Canvas.to_png`."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Not a PNG file")
    offset, width, height, idat = 8, 0, 0, b""
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
        elif kind == b"IDAT":
            idat += body
        offset += 12 + length
    return width, height, zlib.decompress(idat)
