"""k-nearest-neighbour classification and neighbour search (Euclidean)."""
from __future__ import annotations

import numpy as np


def pairwise_sq(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Squared Euclidean distances between rows of A and rows of B."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    d = (A ** 2).sum(1)[:, None] + (B ** 2).sum(1)[None, :] - 2 * A @ B.T
    return np.maximum(d, 0)


def kneighbors(X: np.ndarray, Q: np.ndarray, k: int, exclude_self: bool = False, chunk: int = 1000):
    """Indices and distances of the k nearest rows of X for every row of Q, nearest first."""
    X, Q = np.asarray(X, float), np.asarray(Q, float)
    kk = k + 1 if exclude_self else k
    idx_out = np.empty((len(Q), k), dtype=int)
    dist_out = np.empty((len(Q), k))
    for s in range(0, len(Q), chunk):
        D = pairwise_sq(Q[s:s + chunk], X)
        if exclude_self:
            D[np.arange(len(D)), np.arange(s, s + len(D))] = np.inf
        part = np.argpartition(D, kk - 1, axis=1)[:, :kk]
        pd_ = np.take_along_axis(D, part, 1)
        order = np.lexsort((part, pd_), axis=1)  # by distance, then index for ties
        part = np.take_along_axis(part, order, 1)[:, :k]
        idx_out[s:s + chunk] = part
        dist_out[s:s + chunk] = np.sqrt(np.take_along_axis(D, part, 1))
    return idx_out, dist_out


class KNNClassifier:
    def __init__(self, k: int = 5, weights: str = "uniform"):
        self.k = k
        self.weights = weights

    def fit(self, X, y):
        self.X_ = np.asarray(X, float)
        y = np.asarray(y)
        self.classes_ = np.array(sorted(set(y.tolist())))
        self.y_ = np.searchsorted(self.classes_, y)
        return self

    def predict_proba(self, X) -> np.ndarray:
        idx, dist = kneighbors(self.X_, X, min(self.k, len(self.X_)))
        if self.weights == "distance":
            with np.errstate(divide="ignore"):
                w = 1 / dist
            exact = np.isinf(w)
            w = np.where(exact.any(1, keepdims=True), exact.astype(float), w)
        else:
            w = np.ones_like(dist)
        P = np.zeros((len(idx), len(self.classes_)))
        for c in range(len(self.classes_)):
            P[:, c] = (w * (self.y_[idx] == c)).sum(1)
        return P / P.sum(1, keepdims=True)

    def predict(self, X) -> np.ndarray:
        return self.classes_[self.predict_proba(X).argmax(1)]
