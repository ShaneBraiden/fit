"""Naive Bayes for mixed data: Gaussian likelihoods for numeric attributes,
Laplace-smoothed frequency estimates for categorical ones."""
from __future__ import annotations

import numpy as np
import pandas as pd


class NaiveBayes:
    def __init__(self, alpha: float = 1.0, var_smoothing: float = 1e-9):
        self.alpha = alpha
        self.var_smoothing = var_smoothing

    def fit(self, X: pd.DataFrame, y):
        y = np.asarray(y)
        self.classes_ = np.array(sorted(pd.unique(y)))
        self.numeric = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
        self.categorical = [c for c in X.columns if c not in self.numeric]
        self.log_prior_ = np.log(np.array([(y == c).mean() for c in self.classes_]))
        if self.numeric:
            Xn = X[self.numeric].to_numpy(dtype=float)
            eps = self.var_smoothing * np.nanvar(Xn, axis=0).max()
            self.theta_ = np.array([np.nanmean(Xn[y == c], 0) for c in self.classes_])
            self.var_ = np.array([np.nanvar(Xn[y == c], 0) for c in self.classes_]) + eps
        self.cat_ = {}
        for col in self.categorical:
            vals = sorted(X[col].astype(str).unique())
            table = {}
            for c in self.classes_:
                v = X.loc[y == c, col].astype(str)
                denom = len(v) + self.alpha * len(vals)
                table[c] = {val: np.log(((v == val).sum() + self.alpha) / denom) for val in vals}
                table[c]["__unseen__"] = np.log(self.alpha / denom)
            self.cat_[col] = table
        return self

    def _joint_log_likelihood(self, X: pd.DataFrame) -> np.ndarray:
        jll = np.tile(self.log_prior_, (len(X), 1))
        if self.numeric:
            Xn = X[self.numeric].to_numpy(dtype=float)
            for i in range(len(self.classes_)):
                ll = -0.5 * (np.log(2 * np.pi * self.var_[i]) + (Xn - self.theta_[i]) ** 2 / self.var_[i])
                jll[:, i] += np.nansum(ll, axis=1)  # a missing attribute simply drops out
        for col, table in self.cat_.items():
            vals = X[col].astype(str).to_numpy()
            for i, c in enumerate(self.classes_):
                t = table[c]
                jll[:, i] += np.array([t.get(v, t["__unseen__"]) for v in vals])
        return jll

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        jll = self._joint_log_likelihood(X)
        jll -= jll.max(1, keepdims=True)
        p = np.exp(jll)
        return p / p.sum(1, keepdims=True)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.classes_[self._joint_log_likelihood(X).argmax(1)]

    def explain(self, row: pd.DataFrame) -> list[dict]:
        """Per-class log-prior and per-attribute log-likelihood terms for one row."""
        out = []
        for i, c in enumerate(self.classes_):
            terms = {"log_prior": float(self.log_prior_[i])}
            for j, col in enumerate(self.numeric):
                v = float(row[col].iat[0])
                if not np.isnan(v):
                    terms[col] = float(-0.5 * (np.log(2 * np.pi * self.var_[i, j])
                                               + (v - self.theta_[i, j]) ** 2 / self.var_[i, j]))
            for col, table in self.cat_.items():
                v = str(row[col].iat[0])
                terms[col] = float(table[c].get(v, table[c]["__unseen__"]))
            out.append({"class": str(c), "terms": terms, "total": sum(terms.values())})
        return out
