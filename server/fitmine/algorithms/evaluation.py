"""Classifier evaluation: confusion matrix, precision/recall/F1, ROC/AUC,
hold-out and stratified k-fold cross-validation."""
from __future__ import annotations

import numpy as np


def confusion_matrix(y_true, y_pred, labels) -> np.ndarray:
    idx = {c: i for i, c in enumerate(labels)}
    M = np.zeros((len(labels), len(labels)), dtype=int)
    for t, p in zip(y_true, y_pred):
        M[idx[t], idx[p]] += 1
    return M


def classification_report(y_true, y_pred, labels) -> dict:
    M = confusion_matrix(y_true, y_pred, labels)
    tp = np.diag(M).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        precision = np.nan_to_num(tp / M.sum(0))
        recall = np.nan_to_num(tp / M.sum(1))
        f1 = np.nan_to_num(2 * precision * recall / (precision + recall))
    support = M.sum(1)
    per = [{"class": str(c), "precision": float(p), "recall": float(r), "f1": float(f), "support": int(s)}
           for c, p, r, f, s in zip(labels, precision, recall, f1, support)]
    w = support / support.sum()
    return {
        "accuracy": float(tp.sum() / M.sum()),
        "macro": {"precision": float(precision.mean()), "recall": float(recall.mean()), "f1": float(f1.mean())},
        "weighted": {"precision": float((precision * w).sum()), "recall": float((recall * w).sum()),
                     "f1": float((f1 * w).sum())},
        "per_class": per, "confusion": M.tolist(), "labels": [str(c) for c in labels],
    }


def roc_curve(y_true_binary, scores):
    """ROC points (fpr, tpr) sweeping the threshold over every distinct score."""
    y = np.asarray(y_true_binary, bool)
    s = np.asarray(scores, float)
    order = np.argsort(-s, kind="stable")
    y, s = y[order], s[order]
    distinct = np.r_[np.where(np.diff(s))[0], len(s) - 1]
    tps = np.cumsum(y)[distinct]
    fps = np.cumsum(~y)[distinct]
    P, N = max(y.sum(), 1), max((~y).sum(), 1)
    return np.r_[0, fps / N], np.r_[0, tps / P]


def auc(x, y) -> float:
    return float(np.trapezoid(y, x))


def one_vs_rest_roc(y_true, proba, labels, max_points: int = 60) -> list[dict]:
    out = []
    for i, c in enumerate(labels):
        fpr, tpr = roc_curve(np.asarray(y_true) == c, proba[:, i])
        step = max(1, len(fpr) // max_points)
        keep = np.r_[np.arange(0, len(fpr), step), len(fpr) - 1]
        out.append({"class": str(c), "auc": auc(fpr, tpr),
                    "fpr": fpr[keep].round(4).tolist(), "tpr": tpr[keep].round(4).tolist()})
    return out


def stratified_kfold(y, k: int = 5, seed: int = 0) -> list[np.ndarray]:
    """Fold index arrays; each class is spread evenly over the folds."""
    y = np.asarray(y)
    rng = np.random.default_rng(seed)
    folds: list[list[int]] = [[] for _ in range(k)]
    offset = 0
    for c in sorted(set(y.tolist())):
        idx = np.where(y == c)[0]
        rng.shuffle(idx)
        for j, i in enumerate(idx):
            folds[(j + offset) % k].append(int(i))
        offset += len(idx)
    return [np.array(sorted(f)) for f in folds]


def holdout_split(n: int, test_fraction: float = 0.3, seed: int = 0):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    cut = int(round(n * (1 - test_fraction)))
    return np.sort(idx[:cut]), np.sort(idx[cut:])


def cross_validate(make_model, X, y, k: int = 5, seed: int = 0, fit_kwargs=None):
    """Out-of-fold predictions and probabilities for every row.

    make_model() -> fresh model with fit/predict_proba/classes_. X may be a DataFrame
    or an array; rows are selected positionally."""
    y = np.asarray(y)
    labels = np.array(sorted(set(y.tolist())))
    proba = np.zeros((len(y), len(labels)))
    fold_acc = []
    take = (lambda A, i: A.iloc[i]) if hasattr(X, "iloc") else (lambda A, i: A[i])
    for test in stratified_kfold(y, k, seed):
        train = np.setdiff1d(np.arange(len(y)), test)
        m = make_model()
        m.fit(take(X, train), y[train], **(fit_kwargs or {}))
        P = m.predict_proba(take(X, test))
        cols = [list(labels).index(c) for c in m.classes_]
        proba[np.ix_(test, cols)] = P
        fold_acc.append(float((labels[proba[test].argmax(1)] == y[test]).mean()))
    pred = labels[proba.argmax(1)]
    return pred, proba, labels, fold_acc
