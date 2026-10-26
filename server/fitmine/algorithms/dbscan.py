"""DBSCAN (Ester et al. 1996): density-based clustering with noise.

A point is *core* if at least min_samples points (itself included) lie within
eps. Clusters grow from core points through density-reachability; points
reachable from no core point are noise (label -1).

Neighbourhood queries use a uniform grid of cell size eps for 2-D/3-D data
(so millions of GPS points stay tractable), chunked brute force otherwise, or
a precomputed distance matrix.
"""
from __future__ import annotations

from collections import defaultdict, deque
from itertools import product

import numpy as np

from .knn import pairwise_sq


def _grid_neighbors(X: np.ndarray, eps: float) -> list[np.ndarray]:
    cells = np.floor(X / eps).astype(np.int64)
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for i, c in enumerate(map(tuple, cells)):
        buckets[c].append(i)
    buckets = {c: np.array(v) for c, v in buckets.items()}
    offsets = list(product((-1, 0, 1), repeat=X.shape[1]))
    eps2 = eps * eps
    out: list[np.ndarray] = [None] * len(X)  # type: ignore[list-item]
    for c, members in buckets.items():
        cand = np.concatenate([buckets[t] for o in offsets
                               if (t := tuple(a + b for a, b in zip(c, o))) in buckets])
        Xc = X[cand]
        step = max(1, 2_000_000 // max(len(cand), 1))  # bound memory in dense cells
        for s in range(0, len(members), step):
            chunk = members[s:s + step]
            d2 = ((X[chunk][:, None, :] - Xc[None, :, :]) ** 2).sum(-1)
            for row, i in enumerate(chunk):
                out[i] = cand[d2[row] <= eps2]
    return out


def _brute_neighbors(X: np.ndarray, eps: float, chunk: int = 1000) -> list[np.ndarray]:
    out = []
    for s in range(0, len(X), chunk):
        D = pairwise_sq(X[s:s + chunk], X)
        out += [np.where(r <= eps * eps)[0] for r in D]
    return out


def region_queries(X, eps: float, metric: str = "euclidean") -> list[np.ndarray]:
    if metric == "precomputed":
        D = np.asarray(X)
        return [np.where(r <= eps)[0] for r in D]
    X = np.asarray(X, float)
    return _grid_neighbors(X, eps) if X.shape[1] <= 3 else _brute_neighbors(X, eps)


class DBSCAN:
    def __init__(self, eps: float = 0.5, min_samples: int = 5, metric: str = "euclidean"):
        self.eps, self.min_samples, self.metric = eps, min_samples, metric

    def fit(self, X):
        neigh = region_queries(X, self.eps, self.metric)
        n = len(neigh)
        core = np.array([len(nb) >= self.min_samples for nb in neigh])
        labels = np.full(n, -1)
        cluster = 0
        for i in range(n):
            if labels[i] != -1 or not core[i]:
                continue
            labels[i] = cluster
            queue = deque([i])
            while queue:
                p = queue.popleft()
                nb = neigh[p]
                new = nb[labels[nb] == -1]
                labels[new] = cluster
                # Only core points expand the cluster; border points just join it.
                queue.extend(new[core[new]].tolist())
            cluster += 1
        self.labels_ = labels
        self.core_sample_mask_ = core
        self.n_clusters_ = cluster
        return self


def k_distance(X, k: int, sample: int | None = 3000, seed: int = 0) -> np.ndarray:
    """Sorted distance of every point to its k-th nearest neighbour (the elbow plot used to pick eps)."""
    X = np.asarray(X, float)
    if sample and len(X) > sample:
        X = X[np.random.default_rng(seed).choice(len(X), sample, replace=False)]
    from .knn import kneighbors
    _, d = kneighbors(X, X, k, exclude_self=True)
    return np.sort(d[:, -1])[::-1]
