"""Write the home-screen icon, project_tracker/static/apple-touch-icon.png.

The icon is a white checkmark on the app's accent blue. It is drawn here with the
standard library only (no image library): each pixel is the average of a 4x4 grid
of samples, which smooths the checkmark's edges, and the pixels are written as an
8-bit RGB PNG with ``zlib`` and ``struct``. The square has no transparency and no
rounded corners because iOS applies its own rounded mask to home-screen icons.

The output is deterministic, so rerunning the script reproduces the committed file
byte for byte (a test checks this). Run from the repository root:

    .venv/bin/python scripts/make_icon.py
"""

import math
import struct
import zlib
from itertools import pairwise
from pathlib import Path

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "project_tracker"
    / "static"
    / "apple-touch-icon.png"
)

# 180x180 is the iPhone touch icon size in Apple's Safari Web Content Guide.
SIZE = 180
SUPERSAMPLE = 4

BACKGROUND = (0x0A, 0x5F, 0xD0)  # Accent blue, the same as --accent in style.css.
FOREGROUND = (0xFF, 0xFF, 0xFF)

# The checkmark as a polyline in icon pixels, stroked with round caps and joins.
CHECKMARK = ((50.0, 94.0), (78.0, 122.0), (132.0, 62.0))
STROKE_WIDTH = 20.0

Point = tuple[float, float]


def _distance_to_segment(p: Point, a: Point, b: Point) -> float:
    """Return the distance from point ``p`` to the line segment ``a``-``b``."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _coverage(x: int, y: int) -> float:
    """Return the fraction (0 to 1) of pixel ``x``, ``y`` covered by the checkmark."""
    half = STROKE_WIDTH / 2
    segments = list(pairwise(CHECKMARK))
    hits = 0
    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            p = (x + (sx + 0.5) / SUPERSAMPLE, y + (sy + 0.5) / SUPERSAMPLE)
            if any(_distance_to_segment(p, a, b) <= half for a, b in segments):
                hits += 1
    return hits / SUPERSAMPLE**2


def render_pixels() -> list[bytes]:
    """Return the icon as rows of packed 8-bit RGB pixels."""
    rows: list[bytes] = []
    for y in range(SIZE):
        row = bytearray()
        for x in range(SIZE):
            c = _coverage(x, y)
            row.extend(
                round(bg + (fg - bg) * c)
                for bg, fg in zip(BACKGROUND, FOREGROUND, strict=True)
            )
        rows.append(bytes(row))
    return rows


def _chunk(kind: bytes, data: bytes) -> bytes:
    """Return a PNG chunk: length, type, data, then the CRC of type and data."""
    crc = zlib.crc32(kind + data)
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def encode_png(rows: list[bytes]) -> bytes:
    """Encode rows of 8-bit RGB pixels as a non-interlaced PNG."""
    height, width = len(rows), len(rows[0]) // 3
    # Width, height, bit depth 8, colour type 2 (truecolour), compression 0,
    # filter method 0, interlace 0.
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # Each scanline starts with its filter type; 0 means unfiltered.
    raw = b"".join(b"\x00" + row for row in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def render_png() -> bytes:
    """Return the complete icon PNG."""
    return encode_png(render_pixels())


def main() -> None:
    """Write the icon file."""
    OUTPUT.write_bytes(render_png())
    print(f"Wrote {OUTPUT.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
