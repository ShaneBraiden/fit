"""Cluster validity: SSE, silhouette, Davies-Bouldin (internal) and purity,
adjusted Rand index, NMI (external, against known classes)."""
from __future__ import annotations

import math

import numpy as np

from .distance import pairwise_sq


def sse(X, labels) -> float:
    X = np.asarray(X, float)
    return float(sum(((X[labels == c] - X[labels == c].mean(0)) ** 2).sum() for c in np.unique(labels) if c != -1))


def silhouette(X, labels, sample: int | None = 2000, seed: int = 0) -> tuple[float, np.ndarray]:
    """Mean silhouette s(i) = (b - a) / max(a, b); noise (-1) is excluded."""
    X = np.asarray(X, float)
    labels = np.asarray(labels)
    keep = labels != -1
    X, labels = X[keep], labels[keep]
    if sample and len(X) > sample:
        idx = np.random.default_rng(seed).choice(len(X), sample, replace=False)
        X, labels = X[idx], labels[idx]
    ks = np.unique(labels)
    if len(ks) < 2:
        return 0.0, np.zeros(len(X))
    D = np.sqrt(pairwise_sq(X, X))
    s = np.zeros(len(X))
    sums = np.stack([D[:, labels == c].sum(1) for c in ks], 1)
    counts = np.array([(labels == c).sum() for c in ks])
    own = np.searchsorted(ks, labels)
    n_own = counts[own] - 1
    a = np.where(n_own > 0, sums[np.arange(len(X)), own] / np.maximum(n_own, 1), 0)
    mean_other = sums / counts
    mean_other[np.arange(len(X)), own] = np.inf
    b = mean_other.min(1)
    s = np.where(n_own > 0, (b - a) / np.maximum(a, b), 0)
    return float(s.mean()), s


def davies_bouldin(X, labels) -> float:
    X = np.asarray(X, float)
    ks = [c for c in np.unique(labels) if c != -1]
    if len(ks) < 2:
        return 0.0
    cent = np.array([X[labels == c].mean(0) for c in ks])
    scat = np.array([np.sqrt(((X[labels == c] - cent[i]) ** 2).sum(1)).mean() for i, c in enumerate(ks)])
    M = np.sqrt(pairwise_sq(cent, cent))
    R = (scat[:, None] + scat[None, :]) / np.where(M > 0, M, np.inf)
    np.fill_diagonal(R, -np.inf)
    return float(R.max(1).mean())


def contingency(a, b):
    ua, ia = np.unique(a, return_inverse=True)
    ub, ib = np.unique(b, return_inverse=True)
    M = np.zeros((len(ua), len(ub)), dtype=np.int64)
    np.add.at(M, (ia, ib), 1)
    return M, ua, ub


def purity(truth, labels) -> float:
    M, _, _ = contingency(labels, truth)
    return float(M.max(1).sum() / M.sum())


def adjusted_rand_index(truth, labels) -> float:
    M, _, _ = contingency(truth, labels)
    comb = lambda x: x * (x - 1) / 2  # noqa: E731
    sum_ij = comb(M).sum()
    a, b = comb(M.sum(1)).sum(), comb(M.sum(0)).sum()
    expected = a * b / comb(M.sum())
    max_index = (a + b) / 2
    return float((sum_ij - expected) / (max_index - expected)) if max_index != expected else 1.0


def nmi(truth, labels) -> float:
    M, _, _ = contingency(truth, labels)
    n = M.sum()
    P = M / n
    pi, pj = P.sum(1), P.sum(0)
    nz = P > 0
    mi = (P[nz] * np.log(P[nz] / np.outer(pi, pj)[nz])).sum()
    h = lambda p: -(p[p > 0] * np.log(p[p > 0])).sum()  # noqa: E731
    denom = math.sqrt(h(pi) * h(pj))
    return float(mi / denom) if denom > 0 else 1.0
