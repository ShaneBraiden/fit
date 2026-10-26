"""Principal component analysis via eigen-decomposition of the covariance matrix."""
from __future__ import annotations

import numpy as np


class PCA:
    def __init__(self, n_components: int | None = None):
        self.n_components = n_components

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        self.mean_ = X.mean(0)
        Xc = X - self.mean_
        cov = Xc.T @ Xc / (len(X) - 1)
        vals, vecs = np.linalg.eigh(cov)  # symmetric -> real, ascending
        order = np.argsort(vals)[::-1]
        vals, vecs = np.clip(vals[order], 0, None), vecs[:, order]
        # Deterministic sign: largest |loading| of each component is positive.
        signs = np.sign(vecs[np.abs(vecs).argmax(0), range(vecs.shape[1])])
        vecs = vecs * np.where(signs == 0, 1, signs)
        k = self.n_components or X.shape[1]
        self.components_ = vecs[:, :k].T
        self.explained_variance_ = vals[:k]
        self.explained_variance_ratio_ = vals[:k] / vals.sum()
        return self

    def transform(self, X):
        return (np.asarray(X, dtype=float) - self.mean_) @ self.components_.T

    def fit_transform(self, X):
        return self.fit(X).transform(X)
