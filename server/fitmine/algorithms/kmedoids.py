"""k-medoids: PAM (BUILD + SWAP, Kaufman & Rousseeuw) and CLARA for large data."""
from __future__ import annotations

import numpy as np

from .knn import pairwise_sq


def pam(D: np.ndarray, k: int, max_iter: int = 100):
    """D: full pairwise distance matrix. Returns (medoid indices, labels, total cost, swaps)."""
    n = len(D)
    # BUILD: greedily add the medoid that reduces total cost the most.
    medoids = [int(D.sum(1).argmin())]
    nearest = D[:, medoids[0]].copy()
    for _ in range(1, k):
        gain = np.maximum(nearest[:, None] - D, 0).sum(0)
        gain[medoids] = -1
        m = int(gain.argmax())
        medoids.append(m)
        nearest = np.minimum(nearest, D[:, m])
    swaps = 0
    for _ in range(max_iter):
        Dm = D[:, medoids]
        order = np.argsort(Dm, axis=1)
        d1 = Dm[np.arange(n), order[:, 0]]
        d2 = Dm[np.arange(n), order[:, 1]] if k > 1 else np.full(n, np.inf)
        best = (0.0, None, None)
        is_med = np.zeros(n, bool)
        is_med[medoids] = True
        for i in range(k):
            # Cost change of replacing medoid i by every candidate h at once (n x n_candidates).
            closest_is_i = order[:, 0] == i
            base = np.where(closest_is_i, d2, d1)[:, None]
            new_d = np.minimum(base, D)
            delta = (new_d.sum(0) - d1.sum())
            delta[is_med] = np.inf
            h = int(delta.argmin())
            if delta[h] < best[0] - 1e-12:
                best = (float(delta[h]), i, h)
        if best[1] is None:
            break
        medoids[best[1]] = best[2]
        swaps += 1
    labels = D[:, medoids].argmin(1)
    cost = float(D[np.arange(n), np.array(medoids)[labels]].sum())
    return np.array(medoids), labels, cost, swaps


class KMedoids:
    def __init__(self, k: int = 5, method: str = "pam", sample_size: int = 400, n_samples: int = 5, seed: int = 0):
        self.k, self.method, self.sample_size, self.n_samples, self.seed = k, method, sample_size, n_samples, seed

    def fit(self, X):
        X = np.asarray(X, float)
        if self.method == "pam" or len(X) <= self.sample_size:
            D = np.sqrt(pairwise_sq(X, X))
            med, labels, cost, swaps = pam(D, self.k)
        else:  # CLARA: PAM on several random samples, keep the medoids best on the full data
            rng = np.random.default_rng(self.seed)
            best = None
            for _ in range(self.n_samples):
                s = rng.choice(len(X), self.sample_size, replace=False)
                m_s, _, _, swaps = pam(np.sqrt(pairwise_sq(X[s], X[s])), self.k)
                med = s[m_s]
                Dfull = np.sqrt(pairwise_sq(X, X[med]))
                cost = float(Dfull.min(1).sum())
                if best is None or cost < best[2]:
                    best = (med, Dfull.argmin(1), cost, swaps)
            med, labels, cost, swaps = best
        self.medoid_indices_, self.labels_, self.cost_, self.swaps_ = med, labels, cost, swaps
        self.cluster_centers_ = X[med]
        return self

    def predict(self, X):
        return pairwise_sq(np.asarray(X, float), self.cluster_centers_).argmin(1)
