"""GPS track helpers: speed profiles, change-point segmentation of
the speed profile, and route similarity (discrete Hausdorff distance on arc-length
resampled tracks)."""
from __future__ import annotations

import numpy as np

from ..data import geo


def xy(lat, lon) -> np.ndarray:
    """Metres on the city's equirectangular plane. A track far from the city (a real user
    elsewhere) is rescaled east-west to its own latitude so its distances stay true."""
    x, y = geo.to_xy(lat, lon)
    lat_mid = float(np.mean(lat)) if np.size(lat) else geo.LAT0
    if abs(lat_mid - geo.LAT0) > 1:
        x = x * np.cos(np.radians(lat_mid)) / np.cos(np.radians(geo.LAT0))
    return np.column_stack([x, y])


def step_lengths(P: np.ndarray) -> np.ndarray:
    return np.hypot(*np.diff(P, axis=0).T)


def speed_profile(P: np.ndarray, dt: float) -> np.ndarray:
    """Speed (m/s) at each sample; the first sample copies the second."""
    v = step_lengths(P) / dt
    return np.r_[v[:1], v]


def resample(P: np.ndarray, m: int) -> np.ndarray:
    """m points equally spaced along the polyline's arc length."""
    cum = np.r_[0, np.cumsum(step_lengths(P))]
    if cum[-1] == 0:
        return np.repeat(P[:1], m, axis=0)
    s = np.linspace(0, cum[-1], m)
    return np.column_stack([np.interp(s, cum, P[:, 0]), np.interp(s, cum, P[:, 1])])


def hausdorff(A: np.ndarray, B: np.ndarray) -> float:
    D = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(-1))
    return float(max(D.min(1).max(), D.min(0).max()))


def hausdorff_matrix(tracks: np.ndarray, others: np.ndarray | None = None) -> np.ndarray:
    """tracks: (n, m, 2) resampled tracks -> (n, n_others) Hausdorff distances."""
    others = tracks if others is None else others
    n, m = len(tracks), tracks.shape[1]
    H = np.zeros((n, len(others)))
    chunk = max(1, 3_000_000 // (len(others) * m * m))
    bx, by = others[None, :, None, :, 0], others[None, :, None, :, 1]
    for s in range(0, n, chunk):
        A = tracks[s:s + chunk]
        D = np.hypot(A[:, None, :, None, 0] - bx, A[:, None, :, None, 1] - by)  # (c, n_others, m, m)
        H[s:s + chunk] = np.maximum(D.min(3).max(2), D.min(2).max(2))
    return H


def binary_segmentation(x: np.ndarray, penalty: float, min_size: int = 3, max_cps: int = 40) -> list[int]:
    """Change points of a piecewise-constant signal: repeatedly split the segment whose
    best split reduces the squared-error cost most, while the reduction beats penalty."""
    x = np.asarray(x, float)
    c1, c2 = np.r_[0, np.cumsum(x)], np.r_[0, np.cumsum(x * x)]

    def cost(a, b):
        n = b - a
        s = c1[b] - c1[a]
        return c2[b] - c2[a] - s * s / n

    def best_split(a, b):
        if b - a < 2 * min_size:
            return None
        ts = np.arange(a + min_size, b - min_size + 1)
        n1, n2 = ts - a, b - ts
        s1, s2 = c1[ts] - c1[a], c1[b] - c1[ts]
        q1, q2 = c2[ts] - c2[a], c2[b] - c2[ts]
        total = (q1 - s1 ** 2 / n1) + (q2 - s2 ** 2 / n2)
        i = int(total.argmin())
        return cost(a, b) - total[i], int(ts[i])

    cps: list[int] = []
    segs = [(0, len(x))]
    while len(cps) < max_cps:
        best = None
        for a, b in segs:
            r = best_split(a, b)
            if r and (best is None or r[0] > best[0]):
                best = (r[0], r[1], a, b)
        if best is None or best[0] <= penalty:
            break
        _, t, a, b = best
        cps.append(t)
        segs.remove((a, b))
        segs += [(a, t), (t, b)]
    return sorted(cps)


def noise_variance(x: np.ndarray) -> float:
    """Robust noise variance from first differences (MAD / 0.6745 / sqrt 2)."""
    d = np.diff(np.asarray(x, float))
    s = np.median(np.abs(d - np.median(d))) / 0.6745 / np.sqrt(2)
    return float(max(s * s, 1e-4))


def segment_track(lat, lon, dt: float, beta: float = 1.0, min_size: int = 2) -> dict:
    """Segment a run into phases from its speed profile.

    Change points come from binary segmentation with a BIC-style penalty
    beta * sigma^2 * log(n) (beta tuned on labelled runs); each segment is then labelled by its speed relative to
    the run's typical moving speed."""
    P = xy(lat, lon)
    v = speed_profile(P, dt)
    n = len(v)
    pen = beta * noise_variance(v) * np.log(n)
    cps = binary_segmentation(v, pen, min_size=min_size)
    bounds = [0] + cps + [n]
    segs = [(a, b, float(v[a:b].mean())) for a, b in zip(bounds[:-1], bounds[1:])]
    moving = v[v >= 0.8]
    ref = float(np.median(moving)) if len(moving) else float(np.median(v))
    labels = []
    for i, (a, b, m) in enumerate(segs):
        r = m / ref if ref > 0 else 0
        if m < 0.8:
            lab = "stop"
        elif r > 1.12:
            lab = "fast"
        elif r < 0.88:
            lab = "slow"
        else:
            lab = "steady"
        labels.append(lab)
    # Slow stretches at the very start / end are warm-up and cool-down; slow ones between
    # fast efforts are recoveries.
    i = 0
    while i < len(labels) and labels[i] == "slow":
        labels[i] = "warmup"
        i += 1
    j = len(labels) - 1
    while j >= 0 and labels[j] == "slow":
        labels[j] = "cooldown"
        j -= 1
    labels = ["recovery" if lab == "slow" else lab for lab in labels]
    n_fast = labels.count("fast")
    kind = "intervals" if n_fast >= 2 else ("tempo" if n_fast == 1 and segs[labels.index("fast")][1] -
                                             segs[labels.index("fast")][0] > n / 3 else "steady")
    return {
        "speed": v, "ref_speed": ref, "change_points": cps,
        "segments": [{"start": a, "end": b, "mean_speed": m, "phase": lab}
                     for (a, b, m), lab in zip(segs, labels)],
        "kind": kind,
    }


def boundary_f1(pred: list[int], truth: list[int], tol: int = 2) -> tuple[float, float, float]:
    """Precision/recall/F1 of change points, matching each true boundary at most once within tol."""
    truth = sorted(truth)
    used = set()
    tp = 0
    for p in sorted(pred):
        best = None
        for i, t in enumerate(truth):
            if i not in used and abs(p - t) <= tol and (best is None or abs(p - t) < abs(p - truth[best])):
                best = i
        if best is not None:
            used.add(best)
            tp += 1
    prec = tp / len(pred) if pred else (1.0 if not truth else 0.0)
    rec = tp / len(truth) if truth else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1
