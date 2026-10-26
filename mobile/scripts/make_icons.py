"""Draw the FitMine app icons (no image libraries needed): a pulse line whose peak
is a cluster of data points, white on the accent blue.

    python scripts/make_icons.py
"""
import struct
import zlib
from pathlib import Path

import numpy as np

BLUE = np.array([42, 120, 214])
WHITE = np.array([255, 255, 255])
OUT = Path(__file__).resolve().parent.parent / "assets"


def png(path: Path, rgba: np.ndarray) -> None:
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].astype(np.uint8).tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def mark_alpha(n: int, scale: float) -> np.ndarray:
    """Coverage (0..1) of the white mark on an n x n canvas; `scale` shrinks it toward the centre."""
    yy, xx = np.mgrid[0:n, 0:n].astype(float) + 0.5
    u, v = (xx / n - 0.5) / scale + 0.5, (yy / n - 0.5) / scale + 0.5
    pts = [(0.14, 0.56), (0.34, 0.56), (0.42, 0.40), (0.52, 0.72), (0.60, 0.30), (0.68, 0.56), (0.86, 0.56)]
    d = np.full((n, n), np.inf)
    for a, b in zip(pts[:-1], pts[1:]):
        d = np.minimum(d, seg_dist(u, v, a, b))
    line = np.clip((0.035 - d) * n * scale, 0, 1)
    dots = np.zeros((n, n))
    for cx, cy, r in [(0.60, 0.30, 0.055), (0.73, 0.22, 0.035), (0.50, 0.20, 0.03), (0.66, 0.13, 0.025)]:
        dots = np.maximum(dots, np.clip((r - np.hypot(u - cx, v - cy)) * n * scale, 0, 1))
    return np.maximum(line, dots)


def rounded_square(n: int, radius: float) -> np.ndarray:
    yy, xx = np.mgrid[0:n, 0:n].astype(float) + 0.5
    r = radius * n
    dx = np.maximum(np.maximum(r - xx, xx - (n - r)), 0)
    dy = np.maximum(np.maximum(r - yy, yy - (n - r)), 0)
    return np.clip(r - np.hypot(dx, dy) + 0.5, 0, 1)


def compose(n, bg_alpha, mark):
    rgb = BLUE[None, None, :] * (1 - mark[..., None]) + WHITE[None, None, :] * mark[..., None]
    a = np.maximum(bg_alpha, mark) * 255
    return np.dstack([rgb, a])


def main():
    OUT.mkdir(exist_ok=True)
    n = 1024
    png(OUT / "icon.png", compose(n, np.ones((n, n)), mark_alpha(n, 0.86)))
    # Adaptive icon: transparent foreground inside the 66% safe zone, blue background set in app.json.
    m = mark_alpha(n, 0.58)
    png(OUT / "adaptive-icon.png", np.dstack([np.full((n, n, 3), 255), m * 255]))
    png(OUT / "splash.png", np.dstack([np.full((n, n, 3), 255), mark_alpha(n, 0.45) * 255]))
    f = 64
    png(OUT / "favicon.png", compose(f, rounded_square(f, 0.22), mark_alpha(f, 0.9) * rounded_square(f, 0.22)))
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
