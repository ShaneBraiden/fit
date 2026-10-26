"""Isolation Forest (Liu, Ting & Zhou 2008).

Anomalies are few and different, so random axis-parallel splits isolate them in
fewer steps. Each tree is grown on a subsample of psi points to depth
ceil(log2 psi); the score is s(x) = 2^(-E[h(x)] / c(psi)), close to 1 for anomalies.
"""
from __future__ import annotations

import math

import numpy as np

EULER = 0.5772156649


def c_factor(n) -> np.ndarray:
    """Average path length of an unsuccessful BST search over n points."""
    n = np.asarray(n, float)
    out = np.zeros_like(n)
    big = n > 2
    out[big] = 2 * (np.log(n[big] - 1) + EULER) - 2 * (n[big] - 1) / n[big]
    out[n == 2] = 1.0
    return out


class _Tree:
    """Array-backed isolation tree."""

    def __init__(self, X: np.ndarray, limit: int, rng):
        self.feat, self.thr, self.left, self.right, self.size, self.depth = [], [], [], [], [], []
        self._build(X, 0, limit, rng)
        self.feat, self.thr = np.array(self.feat), np.array(self.thr)
        self.left, self.right = np.array(self.left), np.array(self.right)
        self.size, self.depth = np.array(self.size), np.array(self.depth)

    def _new(self, depth, size):
        for lst, v in ((self.feat, -1), (self.thr, 0.0), (self.left, -1), (self.right, -1), (self.size, size),
                       (self.depth, depth)):
            lst.append(v)
        return len(self.feat) - 1

    def _build(self, X, depth, limit, rng):
        node = self._new(depth, len(X))
        if depth >= limit or len(X) <= 1:
            return node
        spread = X.max(0) - X.min(0)
        candidates = np.where(spread > 0)[0]
        if len(candidates) == 0:
            return node
        f = int(rng.choice(candidates))
        t = float(rng.uniform(X[:, f].min(), X[:, f].max()))
        mask = X[:, f] < t
        self.feat[node], self.thr[node] = f, t
        self.left[node] = self._build(X[mask], depth + 1, limit, rng)
        self.right[node] = self._build(X[~mask], depth + 1, limit, rng)
        return node

    def path_length(self, X: np.ndarray) -> np.ndarray:
        node = np.zeros(len(X), dtype=int)
        while True:
            internal = self.feat[node] >= 0
            if not internal.any():
                break
            i = np.where(internal)[0]
            go_left = X[i, self.feat[node[i]]] < self.thr[node[i]]
            node[i] = np.where(go_left, self.left[node[i]], self.right[node[i]])
        return self.depth[node] + c_factor(self.size[node])


class IsolationForest:
    def __init__(self, n_trees: int = 100, sample_size: int = 256, seed: int = 0):
        self.n_trees, self.sample_size, self.seed = n_trees, sample_size, seed

    def fit(self, X):
        X = np.asarray(X, float)
        rng = np.random.default_rng(self.seed)
        self.psi_ = min(self.sample_size, len(X))
        limit = math.ceil(math.log2(max(self.psi_, 2)))
        self.trees_ = [_Tree(X[rng.choice(len(X), self.psi_, replace=False)], limit, rng)
                       for _ in range(self.n_trees)]
        return self

    def score(self, X) -> np.ndarray:
        X = np.asarray(X, float)
        h = np.mean([t.path_length(X) for t in self.trees_], axis=0)
        return 2 ** (-h / c_factor(np.array([self.psi_]))[0])
