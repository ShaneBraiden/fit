"""Local Outlier Factor (Breunig et al. 2000).

  k-distance(p)        distance to p's k-th nearest neighbour
  reach-dist(p, o)     max(k-distance(o), d(p, o))
  lrd(p)               1 / mean reach-dist(p, o) over o in N_k(p)
  LOF(p)               mean lrd(o) / lrd(p) over o in N_k(p)   (~1 inlier, >1 outlier)
"""
from __future__ import annotations

import numpy as np

from .knn import kneighbors


def lof(X, k: int = 20) -> np.ndarray:
    X = np.asarray(X, float)
    k = min(k, len(X) - 1)
    idx, dist = kneighbors(X, X, k, exclude_self=True)
    k_dist = dist[:, -1]
    reach = np.maximum(dist, k_dist[idx])
    lrd = 1.0 / (reach.mean(1) + 1e-10)
    return lrd[idx].mean(1) / lrd


def lof_novelty(X_train, lrd_train, k_dist_train, Q, k: int = 20) -> np.ndarray:
    """LOF of new points against a fitted reference set (used to score app uploads)."""
    idx, dist = kneighbors(X_train, Q, k)
    reach = np.maximum(dist, k_dist_train[idx])
    lrd_q = 1.0 / (reach.mean(1) + 1e-10)
    return lrd_train[idx].mean(1) / lrd_q


def fit_reference(X, k: int = 20):
    X = np.asarray(X, float)
    idx, dist = kneighbors(X, X, k, exclude_self=True)
    k_dist = dist[:, -1]
    reach = np.maximum(dist, k_dist[idx])
    lrd = 1.0 / (reach.mean(1) + 1e-10)
    return {"X": X, "lrd": lrd, "k_dist": k_dist, "k": k, "scores": lrd[idx].mean(1) / lrd}
