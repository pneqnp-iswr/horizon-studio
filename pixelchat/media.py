"""Bounded GIF/PNG inspection without decoding or executing uploaded media."""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

MAX_BYTES = 512 * 1024
MAX_SIDE = 256
MAX_FRAMES = 64
MAX_DECODED_PIXELS = 4_194_304


class MediaError(ValueError):
    """An upload violates the PixelChat v1 media contract."""


@dataclass(frozen=True)
class Media:
    digest: str
    mime: str
    width: int
    height: int
    frames: int
    size: int

    def public(self) -> dict:
        return {
            "sha256": self.digest, "mime": self.mime,
            "width": self.width, "height": self.height,
            "frames": self.frames, "bytes": self.size,
        }


def _dimensions(width: int, height: int, frames: int = 1) -> None:
    if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
        raise MediaError("Image dimensions exceed the 256x256 limit")
    if frames > MAX_FRAMES or width * height * frames > MAX_DECODED_PIXELS:
        raise MediaError("Animated image exceeds the decoded pixel/frame budget")


def _png(data: bytes) -> tuple[int, int, int]:
    if len(data) < 45 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise MediaError("Invalid PNG signature")
    chunk_len, = struct.unpack_from(">I", data, 8)
    if chunk_len != 13 or data[12:16] != b"IHDR":
        raise MediaError("PNG must begin with a standard IHDR chunk")
    width, height = struct.unpack_from(">II", data, 16)
    _dimensions(width, height)
    # Image data must have a final IEND; reject truncated/extra data and APNG.
    pos = 8
    seen_idat = False
    while pos < len(data):
        if len(data) - pos < 12:
            raise MediaError("Truncated PNG chunk")
        n, = struct.unpack_from(">I", data, pos)
        if n > len(data) - pos - 12:
            raise MediaError("Truncated PNG payload")
        typ = data[pos + 4:pos + 8]
        if typ == b"acTL":
            raise MediaError("APNG is not supported by PixelChat v1")
        if typ == b"IDAT":
            seen_idat = True
        if typ == b"IEND":
            if n != 0 or pos + 12 != len(data) or not seen_idat:
                raise MediaError("Invalid final PNG chunk")
            return width, height, 1
        pos += 12 + n
    raise MediaError("Missing PNG IEND")


def _gif(data: bytes) -> tuple[int, int, int]:
    if len(data) < 20 or data[:6] not in (b"GIF87a", b"GIF89a"):
        raise MediaError("Invalid GIF signature")
    width, height = struct.unpack_from("<HH", data, 6)
    _dimensions(width, height)
    packed = data[10]
    pos = 13 + (3 * (1 << ((packed & 7) + 1)) if packed & 0x80 else 0)
    if pos > len(data):
        raise MediaError("Truncated GIF global palette")
    frames = 0

    def skip_blocks(at: int) -> int:
        while True:
            if at >= len(data):
                raise MediaError("Truncated GIF block list")
            size = data[at]
            at += 1
            if size == 0:
                return at
            if at + size > len(data):
                raise MediaError("Truncated GIF data sub-block")
            at += size

    while pos < len(data):
        token = data[pos]
        pos += 1
        if token == 0x3B:  # trailer
            if frames == 0 or pos != len(data):
                raise MediaError("GIF must have frames and exactly one trailer")
            return width, height, frames
        if token == 0x21:  # extension
            if pos >= len(data):
                raise MediaError("Truncated GIF extension")
            ext = data[pos]
            pos += 1
            if ext == 0xF9:  # graphics control extension is exactly 4 bytes
                if pos + 6 > len(data) or data[pos] != 4 or data[pos + 5] != 0:
                    raise MediaError("Invalid GIF graphics control extension")
                pos += 6
            else:
                pos = skip_blocks(pos)
        elif token == 0x2C:  # image descriptor
            if pos + 9 > len(data):
                raise MediaError("Truncated GIF image descriptor")
            left, top, fw, fh = struct.unpack_from("<HHHH", data, pos)
            flags = data[pos + 8]
            if not fw or not fh or left + fw > width or top + fh > height:
                raise MediaError("GIF frame exceeds the logical screen")
            pos += 9
            if flags & 0x80:
                pos += 3 * (1 << ((flags & 7) + 1))
            if pos >= len(data) or not (2 <= data[pos] <= 8):
                raise MediaError("Invalid GIF LZW code size or palette")
            pos = skip_blocks(pos + 1)
            frames += 1
            _dimensions(width, height, frames)
        else:
            raise MediaError("Unknown GIF block marker")
    raise MediaError("Missing GIF trailer")


def inspect_media(data: bytes) -> Media:
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise MediaError("Upload is empty or exceeds 512 KiB")
    if data.startswith((b"GIF87a", b"GIF89a")):
        width, height, frames = _gif(data)
        mime = "image/gif"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height, frames = _png(data)
        mime = "image/png"
    else:
        raise MediaError("Only GIF and PNG are supported in v1")
    return Media(hashlib.sha256(data).hexdigest(), mime, width, height, frames, len(data))
