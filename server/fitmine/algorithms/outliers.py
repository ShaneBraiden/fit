"""Statistical outlier tests on one attribute: z-score, modified z-score (MAD), IQR fences, Grubbs."""
from __future__ import annotations

import numpy as np
from scipy import stats as _st


def zscore_scores(x) -> np.ndarray:
    x = np.asarray(x, float)
    sd = np.nanstd(x)
    return np.abs(x - np.nanmean(x)) / (sd if sd > 0 else 1)


def robust_z_scores(x) -> np.ndarray:
    """Modified z-score 0.6745 (x - median) / MAD (Iglewicz & Hoaglin); robust to the outliers themselves."""
    x = np.asarray(x, float)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med))
    return np.abs(0.6745 * (x - med) / (mad if mad > 0 else 1e-9))


def iqr_fences(x, k: float = 1.5) -> tuple[float, float]:
    q1, q3 = np.nanpercentile(x, [25, 75])
    return float(q1 - k * (q3 - q1)), float(q3 + k * (q3 - q1))


def iqr_flags(x, k: float = 1.5) -> np.ndarray:
    lo, hi = iqr_fences(x, k)
    x = np.asarray(x, float)
    return (x < lo) | (x > hi)


def grubbs(x, alpha: float = 0.05, max_outliers: int = 50) -> list[int]:
    """Iterated two-sided Grubbs test; returns indices of detected outliers (assumes normal data)."""
    x = np.asarray(x, float)
    idx = np.where(~np.isnan(x))[0]
    out = []
    for _ in range(max_outliers):
        v = x[idx]
        n = len(v)
        if n < 3:
            break
        sd = v.std(ddof=1)
        if sd == 0:
            break
        j = int(np.abs(v - v.mean()).argmax())
        G = abs(v[j] - v.mean()) / sd
        t = _st.t.ppf(1 - alpha / (2 * n), n - 2)
        crit = (n - 1) / np.sqrt(n) * np.sqrt(t ** 2 / (n - 2 + t ** 2))
        if G <= crit:
            break
        out.append(int(idx[j]))
        idx = np.delete(idx, j)
    return out
