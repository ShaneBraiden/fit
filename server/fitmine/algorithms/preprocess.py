"""U1 data preprocessing, from scratch: cleaning, smoothing, normalisation,
discretisation and correlation analysis (Han & Kamber ch. 3)."""
from __future__ import annotations

import math

import numpy as np
from scipy import stats as _st


# ----------------------------------------------------------------------------- missing values

def impute_constant(x: np.ndarray, value: float) -> np.ndarray:
    x = np.asarray(x, dtype=float).copy()
    x[np.isnan(x)] = value
    return x


def impute_mean(x):
    return impute_constant(x, np.nanmean(x))


def impute_median(x):
    return impute_constant(x, np.nanmedian(x))


def impute_group_mean(x, groups):
    """Fill with the mean of the same class (e.g. same activity), the 'attribute mean
    for all samples belonging to the same class' strategy."""
    x = np.asarray(x, dtype=float).copy()
    groups = np.asarray(groups)
    for g in np.unique(groups):
        m = groups == g
        if np.isnan(x[m]).any():
            fill = np.nanmean(x[m]) if (~np.isnan(x[m])).any() else np.nanmean(x)
            x[m & np.isnan(x)] = fill
    return x


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


# ----------------------------------------------------------------------------- binning / smoothing

def equal_width_edges(x, k: int) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    lo, hi = np.nanmin(x), np.nanmax(x)
    return np.linspace(lo, hi, k + 1)


def equal_depth_edges(x, k: int) -> np.ndarray:
    """Equal-frequency bin edges (quantiles)."""
    x = np.sort(np.asarray(x, dtype=float)[~np.isnan(x)])
    return np.unique(np.quantile(x, np.linspace(0, 1, k + 1)))


def assign_bins(x, edges) -> np.ndarray:
    """Bin index 0..len(edges)-2 for each value; the last bin is closed on the right."""
    idx = np.searchsorted(edges, x, side="right") - 1
    return np.clip(idx, 0, len(edges) - 2)


def smooth_by_bins(sorted_values, n_bins: int, method: str = "means"):
    """Textbook smoothing: partition sorted data into equal-depth bins, then replace each
    value by its bin mean, median or nearest bin boundary."""
    v = np.asarray(sorted_values, dtype=float)
    bins = np.array_split(v, n_bins)
    out = []
    for b in bins:
        if method == "means":
            out.append(np.full(len(b), b.mean()))
        elif method == "medians":
            out.append(np.full(len(b), np.median(b)))
        elif method == "boundaries":
            lo, hi = b.min(), b.max()
            out.append(np.where(b - lo <= hi - b, lo, hi))
        else:
            raise ValueError(method)
    return [b.tolist() for b in bins], [o.tolist() for o in out]


def moving_median(x, w: int = 5) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    h = w // 2
    pad = np.pad(x, h, mode="edge")
    return np.array([np.median(pad[i:i + w]) for i in range(len(x))])


# ----------------------------------------------------------------------------- normalisation

def min_max(x, new_min: float = 0.0, new_max: float = 1.0):
    x = np.asarray(x, dtype=float)
    lo, hi = np.nanmin(x), np.nanmax(x)
    if hi == lo:
        return np.full_like(x, new_min)
    return (x - lo) / (hi - lo) * (new_max - new_min) + new_min


def z_score(x, ddof: int = 0):
    x = np.asarray(x, dtype=float)
    sd = np.nanstd(x, ddof=ddof)
    return (x - np.nanmean(x)) / (sd if sd > 0 else 1.0)


def decimal_scaling(x):
    """v' = v / 10^j with j the smallest integer such that max |v'| < 1."""
    x = np.asarray(x, dtype=float)
    m = np.nanmax(np.abs(x))
    j = 0 if m < 1 else int(math.floor(math.log10(m))) + 1
    return x / 10 ** j, j


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


# ----------------------------------------------------------------------------- discretisation

def entropy(labels) -> float:
    _, c = np.unique(labels, return_counts=True)
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def _row_entropy(counts: np.ndarray) -> np.ndarray:
    tot = counts.sum(-1, keepdims=True)
    p = np.divide(counts, tot, out=np.zeros_like(counts, dtype=float), where=tot > 0)
    logp = np.log2(p, out=np.zeros_like(p), where=p > 0)
    return -(p * logp).sum(-1)


def entropy_discretize(x, y, max_bins: int = 8) -> list[float]:
    """Supervised discretisation: recursive binary splits on the boundary with the
    highest information gain, stopped by Fayyad & Irani's MDL criterion."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y)
    ok = ~np.isnan(x)
    order = np.argsort(x[ok], kind="stable")
    xs = x[ok][order]
    _, yi = np.unique(y[ok][order], return_inverse=True)
    cum = np.vstack([np.zeros(yi.max() + 1), np.cumsum(np.eye(yi.max() + 1)[yi], axis=0)])
    cuts: list[float] = []

    def split(lo: int, hi: int):
        n = hi - lo
        if len(cuts) >= max_bins - 1 or n < 4:
            return
        total = cum[hi] - cum[lo]
        left = cum[lo + 1:hi] - cum[lo]          # class counts of xs[lo:i] for i = lo+1 .. hi-1
        right = total - left
        nl = np.arange(1, n)
        e = (nl * _row_entropy(left) + (n - nl) * _row_entropy(right)) / n
        e[xs[lo + 1:hi] == xs[lo:hi - 1]] = np.inf  # only cut between distinct values
        if not np.isfinite(e).any():
            return
        j = int(np.argmin(e))
        i = lo + 1 + j
        base = float(_row_entropy(total))
        gain = base - e[j]
        k, k1, k2 = (int((c > 0).sum()) for c in (total, left[j], right[j]))
        delta = math.log2(3 ** k - 2) - (k * base - k1 * float(_row_entropy(left[j]))
                                         - k2 * float(_row_entropy(right[j])))
        if gain <= (math.log2(n - 1) + delta) / n:
            return
        cuts.append(float((xs[i - 1] + xs[i]) / 2))
        split(lo, i)
        split(i, hi)

    split(0, len(xs))
    return sorted(cuts)


# ----------------------------------------------------------------------------- correlation

def pearson(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    xm, ym = x - x.mean(), y - y.mean()
    den = math.sqrt((xm ** 2).sum() * (ym ** 2).sum())
    return float((xm * ym).sum() / den) if den else 0.0


def correlation_matrix(X) -> np.ndarray:
    X = np.asarray(X, float)
    m = X.shape[1]
    R = np.eye(m)
    for i in range(m):
        for j in range(i + 1, m):
            R[i, j] = R[j, i] = pearson(X[:, i], X[:, j])
    return R


def chi_square(table) -> dict:
    """Pearson chi-square test of independence on an r x c contingency table."""
    O = np.asarray(table, dtype=float)
    E = O.sum(1, keepdims=True) * O.sum(0, keepdims=True) / O.sum()
    stat = float(((O - E) ** 2 / E).sum())
    dof = (O.shape[0] - 1) * (O.shape[1] - 1)
    return {"chi2": stat, "dof": dof, "p_value": float(_st.chi2.sf(stat, dof)), "expected": E.tolist()}
