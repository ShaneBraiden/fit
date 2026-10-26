"""Missing-value handling and scaling, from scratch: kNN imputation (the method the
cleaning step uses), mean imputation (the baseline it is compared against) and a
stored z-score scaler."""
from __future__ import annotations

import numpy as np


# ----------------------------------------------------------------------------- missing values

def impute_constant(x: np.ndarray, value: float) -> np.ndarray:
    x = np.asarray(x, dtype=float).copy()
    x[np.isnan(x)] = value
    return x


def impute_mean(x):
    return impute_constant(x, np.nanmean(x))


def nan_euclidean(a: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Distance from row a to every row of B using only coordinates present in both,
    scaled up by n_features / n_present (same definition sklearn's KNNImputer uses)."""
    diff = B - a
    present = ~np.isnan(diff)
    n_present = present.sum(1)
    sq = np.where(present, diff, 0.0) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.sqrt(sq.sum(1) * B.shape[1] / n_present)
    d[n_present == 0] = np.nan
    return d


def knn_impute(X: np.ndarray, k: int = 5) -> np.ndarray:
    """Replace each missing cell with the mean of that column over the k nearest rows
    (nan-euclidean distance) that have the column observed."""
    X = np.asarray(X, dtype=float)
    out = X.copy()
    for j in range(X.shape[1]):
        miss = np.where(np.isnan(X[:, j]))[0]
        donors = np.where(~np.isnan(X[:, j]))[0]
        if len(miss) == 0 or len(donors) == 0:
            continue
        D = X[donors]
        for i in miss:
            d = nan_euclidean(X[i], D)
            ok = ~np.isnan(d)
            if not ok.any():
                out[i, j] = X[donors, j].mean()
                continue
            idx = np.where(ok)[0]
            kk = min(k, len(idx))
            nearest = idx[np.argsort(d[idx], kind="stable")[:kk]]
            out[i, j] = X[donors[nearest], j].mean()
    return out


# ----------------------------------------------------------------------------- scaling

class Standardizer:
    """Column-wise z-score with stored mean/std so new rows can be transformed."""

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        self.mean_ = np.nanmean(X, 0)
        sd = np.nanstd(X, 0)
        self.std_ = np.where(sd > 0, sd, 1.0)
        return self

    def transform(self, X):
        return (np.asarray(X, dtype=float) - self.mean_) / self.std_

    def fit_transform(self, X):
        return self.fit(X).transform(X)
