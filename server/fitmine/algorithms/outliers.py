"""Univariate outlier tests: IQR fences (workout data checks) and the modified
z-score (profile consistency checks)."""
from __future__ import annotations

import numpy as np


def robust_z_scores(x) -> np.ndarray:
    """Modified z-score 0.6745 (x - median) / MAD (Iglewicz & Hoaglin); robust to the outliers themselves."""
    x = np.asarray(x, float)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med))
    return np.abs(0.6745 * (x - med) / (mad if mad > 0 else 1e-9))


def iqr_fences(x, k: float = 1.5) -> tuple[float, float]:
    q1, q3 = np.nanpercentile(x, [25, 75])
    return float(q1 - k * (q3 - q1)), float(q3 + k * (q3 - q1))
