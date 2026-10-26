"""k-means (Lloyd's algorithm) with k-means++ seeding."""
from __future__ import annotations

import numpy as np

from .distance import pairwise_sq


def kmeans_pp(X: np.ndarray, k: int, rng) -> np.ndarray:
    """k-means++: each next centre is drawn with probability proportional to D(x)^2."""
    centres = [X[rng.integers(len(X))]]
    d2 = pairwise_sq(X, centres[0][None])[:, 0]
    for _ in range(1, k):
        p = d2 / d2.sum() if d2.sum() > 0 else np.full(len(X), 1 / len(X))
        c = X[rng.choice(len(X), p=p)]
        centres.append(c)
        d2 = np.minimum(d2, pairwise_sq(X, c[None])[:, 0])
    return np.array(centres)


class KMeans:
    def __init__(self, k: int = 5, init="k-means++", n_init: int = 5, max_iter: int = 300, tol: float = 1e-6,
                 seed: int = 0):
        self.k, self.init, self.n_init, self.max_iter, self.tol, self.seed = k, init, n_init, max_iter, tol, seed

    def _run(self, X, centres):
        history = []
        for it in range(1, self.max_iter + 1):
            D = pairwise_sq(X, centres)
            labels = D.argmin(1)
            inertia = float(D[np.arange(len(X)), labels].sum())
            history.append(inertia)
            new = centres.copy()
            for j in range(self.k):
                members = X[labels == j]
                if len(members):
                    new[j] = members.mean(0)
                else:  # empty cluster: move it to the point farthest from its centre
                    new[j] = X[D[np.arange(len(X)), labels].argmax()]
            shift = float(((new - centres) ** 2).sum())
            centres = new
            if shift <= self.tol:
                break
        D = pairwise_sq(X, centres)
        labels = D.argmin(1)
        return labels, centres, float(D[np.arange(len(X)), labels].sum()), it, history

    def fit(self, X):
        X = np.asarray(X, float)
        rng = np.random.default_rng(self.seed)
        best = None
        if isinstance(self.init, np.ndarray):
            runs = [np.array(self.init, float)]
        else:
            runs = [kmeans_pp(X, self.k, rng) if self.init == "k-means++" else X[rng.choice(len(X), self.k, replace=False)]
                    for _ in range(self.n_init)]
        for c0 in runs:
            res = self._run(X, c0.copy())
            if best is None or res[2] < best[2]:
                best = res
        self.labels_, self.cluster_centers_, self.inertia_, self.n_iter_, self.history_ = best
        return self

    def predict(self, X):
        return pairwise_sq(np.asarray(X, float), self.cluster_centers_).argmin(1)
