"""Squared Euclidean distances between two sets of rows (k-means, DBSCAN)."""
from __future__ import annotations

import numpy as np


def pairwise_sq(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Squared Euclidean distances between rows of A and rows of B."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    d = (A ** 2).sum(1)[:, None] + (B ** 2).sum(1)[None, :] - 2 * A @ B.T
    return np.maximum(d, 0)
