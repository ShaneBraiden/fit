"""U4 Classification: predict a user's fitness level from profile and behaviour.

Labels come from fitness assessments (about 75% of users; noisy). The other
users are the ones the app needs a prediction for, and the hidden true level
lets us check those predictions too.

Each model is a small wrapper so its preprocessing is learned inside fit():
  ID3          equal-frequency discretisation (Low/Mid/High) of numeric attributes
  C4.5 / CART  raw attributes (missing values routed to the larger branch)
  Naive Bayes  Gaussian numeric + Laplace categorical
  kNN          median imputation + z-score, gender as 0/1
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .. import config as C
from ..algorithms import preprocess as P
from ..algorithms.evaluation import classification_report, cross_validate, one_vs_rest_roc
from ..algorithms.knn import KNNClassifier
from ..algorithms.naive_bayes import NaiveBayes
from ..algorithms.tree import DecisionTree
from ..data import store
from .common import user_features

NUMERIC = ["age", "bmi", "resting_hr", "vo2max", "sessions_per_week", "minutes_per_week", "avg_intensity",
           "run_pace", "longest_km", "share_run", "share_strength", "share_hiit", "share_yoga", "share_walk"]
CATEGORICAL = ["gender"]
FEATURES = NUMERIC + CATEGORICAL
MODELS = {"id3": "ID3 (info gain)", "c45": "C4.5 (gain ratio)", "cart": "CART (Gini)", "nb": "Naive Bayes",
          "knn": "k-NN"}


class TreeModel:
    def __init__(self, algorithm="c45", max_depth=6, min_samples_split=10, prune=False, seed=0):
        self.algorithm, self.max_depth, self.min_samples_split, self.prune, self.seed = \
            algorithm, max_depth, min_samples_split, prune, seed

    def _prep(self, X):
        if self.algorithm != "id3":
            return X[FEATURES]
        out = X[CATEGORICAL].astype(str).copy()
        for c in NUMERIC:
            b = P.assign_bins(X[c].fillna(self.medians_[c]).to_numpy(float), self.edges_[c])
            out[c] = np.array(["Low", "Mid", "High"])[np.minimum(b, 2)]
        return out

    def fit(self, X, y):
        y = np.asarray(y)
        if self.algorithm == "id3":
            self.medians_ = X[NUMERIC].median()
            self.edges_ = {c: P.equal_depth_edges(X[c].fillna(self.medians_[c]).to_numpy(float), 3) for c in NUMERIC}
        Xp = self._prep(X)
        self.tree = DecisionTree(self.algorithm, self.max_depth, self.min_samples_split)
        if self.prune:
            rng = np.random.default_rng(self.seed)
            val = rng.random(len(y)) < 0.25
            self.tree.fit(Xp[~val], y[~val])
            self.pruned_ = self.tree.prune(Xp[val], y[val])
        else:
            self.tree.fit(Xp, y)
        self.classes_ = self.tree.classes_
        return self

    def predict_proba(self, X):
        return self.tree.predict_proba(self._prep(X))

    def predict(self, X):
        return self.classes_[self.predict_proba(X).argmax(1)]


class NBModel:
    def fit(self, X, y):
        self.nb = NaiveBayes().fit(X[FEATURES], y)
        self.classes_ = self.nb.classes_
        return self

    def predict_proba(self, X):
        return self.nb.predict_proba(X[FEATURES])

    def predict(self, X):
        return self.nb.predict(X[FEATURES])


class KNNModel:
    def __init__(self, k=7, weights="distance"):
        self.k, self.weights = k, weights

    def _matrix(self, X):
        M = X[NUMERIC].fillna(self.medians_).to_numpy(float)
        g = (X["gender"] == "M").to_numpy(float)[:, None]
        return np.hstack([self.scaler.transform(M), g])

    def fit(self, X, y):
        self.medians_ = X[NUMERIC].median()
        self.scaler = P.Standardizer().fit(X[NUMERIC].fillna(self.medians_).to_numpy(float))
        self.knn = KNNClassifier(self.k, self.weights).fit(self._matrix(X), y)
        self.classes_ = self.knn.classes_
        return self

    def predict_proba(self, X):
        return self.knn.predict_proba(self._matrix(X))

    def predict(self, X):
        return self.classes_[self.predict_proba(X).argmax(1)]


def make_model(name: str, params: dict | None = None):
    p = params or {}
    if name in ("id3", "c45", "cart"):
        return TreeModel(name, int(p.get("max_depth", 6)), int(p.get("min_samples_split", 10)),
                         bool(p.get("prune", False)))
    if name == "nb":
        return NBModel()
    if name == "knn":
        return KNNModel(int(p.get("k", 7)), p.get("weights", "distance"))
    raise ValueError(name)


def dataset(con):
    users = store.read("users", con)
    w = store.read("workouts", con)
    feats = user_features(users, w)
    feats = feats.merge(users[["user_id", "assessed_level"]], on="user_id")
    gt = store.read("gt_users", con).set_index("user_id").level
    feats["true_level"] = gt.reindex(feats.user_id).to_numpy()
    return feats


def evaluate(feats: pd.DataFrame, name: str, params: dict | None = None, folds: int = 5) -> dict:
    lab = feats.dropna(subset=["assessed_level"]).reset_index(drop=True)
    y = lab.assessed_level.to_numpy()
    t = time.perf_counter()
    pred, proba, labels, fold_acc = cross_validate(lambda: make_model(name, params), lab, y, k=folds)
    ms = (time.perf_counter() - t) * 1000
    order = [lv for lv in C.LEVELS if lv in labels]
    rep = classification_report(y, pred, order)
    perm = [list(labels).index(lv) for lv in order]
    return {"model": name, "label": MODELS[name], "params": params or {}, "folds": folds,
            "fold_accuracy": fold_acc, "ms": round(ms, 1), **rep,
            "roc": one_vs_rest_roc(y, proba[:, perm], order)}


def fit_final(feats: pd.DataFrame, name: str, params: dict | None = None):
    lab = feats.dropna(subset=["assessed_level"])
    return make_model(name, params).fit(lab, lab.assessed_level.to_numpy())


def hidden_truth(feats: pd.DataFrame, model) -> dict:
    """Accuracy on the users without an assessment, against their hidden true level."""
    un = feats[feats.assessed_level.isna()]
    pred = model.predict(un)
    rep = classification_report(un.true_level.to_numpy(), pred, C.LEVELS)
    return {"n": int(len(un)), "accuracy": rep["accuracy"], "macro_f1": rep["macro"]["f1"],
            "confusion": rep["confusion"], "labels": rep["labels"]}


def tree_view(feats: pd.DataFrame, params: dict | None = None, algorithm: str = "c45") -> dict:
    m = fit_final(feats, algorithm, {"max_depth": 4, "min_samples_split": 20, **(params or {})})
    t = m.tree
    return {"algorithm": algorithm, "tree": t.to_dict(), "rules": t.rules()[:15], "stats": t.stats(),
            "importance": sorted(({"feature": k, "importance": v} for k, v in t.feature_importances_.items()),
                                 key=lambda d: -d["importance"])}


def run(con) -> dict:
    feats = dataset(con)
    comparison = [evaluate(feats, m) for m in MODELS]
    best = max(comparison, key=lambda r: r["macro"]["f1"])
    final = fit_final(feats, best["model"])
    lab = feats.dropna(subset=["assessed_level"]).reset_index(drop=True)
    y = lab.assessed_level.to_numpy()
    k_sweep = []
    for k in range(1, 26, 2):
        pred, _, _, _ = cross_validate(lambda: KNNModel(k, "distance"), lab, y, k=5)
        k_sweep.append({"k": k, "accuracy": float((pred == y).mean())})
    depth = []
    for d in range(1, 11):
        pred, _, _, _ = cross_validate(lambda: TreeModel("c45", d, 10), lab, y, k=5)
        train_acc = float((TreeModel("c45", d, 10).fit(lab, y).predict(lab) == y).mean())
        depth.append({"depth": d, "cv_accuracy": float((pred == y).mean()), "train_accuracy": train_acc})
    return {
        "n_users": int(len(feats)), "n_labelled": int(len(lab)),
        "class_counts": lab.assessed_level.value_counts().reindex(C.LEVELS).fillna(0).astype(int).to_dict(),
        "features": FEATURES,
        "comparison": [{k: r[k] for k in ("model", "label", "accuracy", "macro", "weighted", "ms", "fold_accuracy")}
                       for r in comparison],
        "details": {r["model"]: r for r in comparison},
        "best_model": best["model"],
        "hidden_truth": hidden_truth(feats, final),
        "k_sweep": k_sweep, "depth_sweep": depth,
        "tree": tree_view(feats),
    }, final, feats
