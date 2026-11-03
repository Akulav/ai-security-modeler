"""Draws icon.ico: the app's shield-and-check on its dark tile. Standard library only.

Run from anywhere: python launcher/assets/make_icon.py
"""
import struct
import zlib
from pathlib import Path

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
SAMPLES = 4  # Per axis, for smooth edges.
TILE = (11, 17, 28)
ACCENT = (52, 211, 153)
CHECK = (11, 17, 28)


def cubic(p0, p1, p2, p3, steps=24):
    for i in range(steps + 1):
        t = i / steps
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        yield (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def shield() -> list[tuple[float, float]]:
    """The right half in a 24-unit box, mirrored for the left."""
    right = [
        *cubic((12, 2.2), (14, 4), (16.8, 5.1), (19.2, 5.1)),
        (20, 5.9),
        (20, 13),
        *cubic((20, 13), (20, 17.6), (16.8, 20.4), (12, 22)),
    ]
    left = [(24 - x, y) for x, y in reversed(right)]
    return right + left[1:-1]


def inside(polygon, x, y) -> bool:
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def near_segment(x, y, a, b, width) -> bool:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2 <= (width / 2) ** 2


def in_tile(x, y, radius=5.0) -> bool:
    # A rounded square filling the 24-unit box.
    cx, cy = min(max(x, radius), 24 - radius), min(max(y, radius), 24 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def render(size: int) -> bytes:
    outline = shield()
    # Small sizes get a bolder check, or it disappears.
    check_width = 2.6 if size <= 24 else 2.1
    check = [((8.6, 12.4), (11, 14.8)), ((11, 14.8), (15.6, 10.2))]
    rows = bytearray()
    for py in range(size):
        rows.append(0)  # PNG filter: none.
        for px in range(size):
            totals = [0, 0, 0, 0]
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (px + (sx + 0.5) / SAMPLES) * 24 / size
                    y = (py + (sy + 0.5) / SAMPLES) * 24 / size
                    if not in_tile(x, y):
                        continue
                    colour = TILE
                    if inside(outline, x, y):
                        colour = CHECK if any(near_segment(x, y, a, b, check_width) for a, b in check) else ACCENT
                    for i in range(3):
                        totals[i] += colour[i]
                    totals[3] += 1
            n = SAMPLES * SAMPLES
            covered = totals[3]
            rows.extend(
                [totals[0] // covered, totals[1] // covered, totals[2] // covered, 255 * covered // n]
                if covered else [0, 0, 0, 0]
            )
    return png(size, bytes(rows))


def png(size: int, raw: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def ico(images: list[tuple[int, bytes]]) -> bytes:
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, data in images:
        side = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(data for _, data in images)


if __name__ == "__main__":
    here = Path(__file__).parent
    images = [(size, render(size)) for size in SIZES]
    (here / "icon.ico").write_bytes(ico(images))
    (here / "icon.png").write_bytes(dict(images)[256])
    print("Wrote", here / "icon.ico")
