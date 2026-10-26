"""Fitness level: predict a user's level (Beginner .. Elite) from profile and behaviour.

Labels come from fitness assessments (about 75% of users; noisy). The model is a
C4.5 decision tree on the raw attributes (numeric thresholds chosen by gain
ratio, missing values routed to the larger branch), evaluated with stratified
5-fold cross-validation against a majority-class baseline. The users without an
assessment are the ones the app needs a prediction for; their hidden true level
checks those predictions too.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from ..algorithms.evaluation import classification_report, cross_validate, one_vs_rest_roc
from ..algorithms.tree import DecisionTree
from ..data import store
from .common import user_features

NUMERIC = ["age", "bmi", "resting_hr", "vo2max", "sessions_per_week", "minutes_per_week", "avg_intensity",
           "run_pace", "longest_km", "share_run", "share_strength", "share_hiit", "share_yoga", "share_walk"]
CATEGORICAL = ["gender"]
FEATURES = NUMERIC + CATEGORICAL
MAX_DEPTH = 6
MIN_SAMPLES_SPLIT = 10


class LevelModel:
    """C4.5 on the feature columns of a user-feature frame."""

    def __init__(self, max_depth=MAX_DEPTH, min_samples_split=MIN_SAMPLES_SPLIT):
        self.max_depth, self.min_samples_split = max_depth, min_samples_split

    def fit(self, X, y):
        self.tree = DecisionTree(self.max_depth, self.min_samples_split).fit(X[FEATURES], np.asarray(y))
        self.classes_ = self.tree.classes_
        return self

    def predict_proba(self, X):
        return self.tree.predict_proba(X[FEATURES])

    def predict(self, X):
        return self.classes_[self.predict_proba(X).argmax(1)]


def dataset(con):
    users = store.read("users", con)
    w = store.read("workouts", con)
    feats = user_features(users, w)
    feats = feats.merge(users[["user_id", "assessed_level"]], on="user_id")
    gt = store.read("gt_users", con).set_index("user_id").level
    feats["true_level"] = gt.reindex(feats.user_id).to_numpy()
    return feats


def hidden_truth(feats: pd.DataFrame, model) -> dict:
    """Accuracy on the users without an assessment, against their hidden true level."""
    un = feats[feats.assessed_level.isna()]
    pred = model.predict(un)
    rep = classification_report(un.true_level.to_numpy(), pred, C.LEVELS)
    return {"n": int(len(un)), "accuracy": rep["accuracy"], "macro_f1": rep["macro"]["f1"],
            "confusion": rep["confusion"], "labels": rep["labels"]}


def run(con) -> tuple[dict, LevelModel, pd.DataFrame]:
    feats = dataset(con)
    lab = feats.dropna(subset=["assessed_level"]).reset_index(drop=True)
    y = lab.assessed_level.to_numpy()
    pred, proba, labels, fold_acc = cross_validate(LevelModel, lab, y, k=5)
    order = [lv for lv in C.LEVELS if lv in labels]
    cv = classification_report(y, pred, order)
    perm = [list(labels).index(lv) for lv in order]
    majority = pd.Series(y).value_counts()
    final = LevelModel().fit(lab, y)
    depth = []
    for d in range(1, 11):
        p, _, _, _ = cross_validate(lambda: LevelModel(d), lab, y, k=5)
        depth.append({"depth": d, "cv_accuracy": float((p == y).mean()),
                      "train_accuracy": float((LevelModel(d).fit(lab, y).predict(lab) == y).mean())})
    view = LevelModel(4, 20).fit(lab, y).tree
    t = final.tree
    return {
        "n_users": int(len(feats)), "n_labelled": int(len(lab)),
        "class_counts": lab.assessed_level.value_counts().reindex(C.LEVELS).fillna(0).astype(int).to_dict(),
        "features": FEATURES, "params": {"max_depth": MAX_DEPTH, "min_samples_split": MIN_SAMPLES_SPLIT},
        "cv": {**cv, "folds": 5, "fold_accuracy": fold_acc, "roc": one_vs_rest_roc(y, proba[:, perm], order)},
        "baseline": {"rule": f"always predict {majority.index[0]}", "accuracy": float(majority.iloc[0] / len(y))},
        "hidden_truth": hidden_truth(feats, final),
        "depth_sweep": depth,
        "tree": {"tree": view.to_dict(), "rules": view.rules()[:15], "stats": t.stats(),
                 "importance": sorted(({"feature": k, "importance": v} for k, v in t.feature_importances_.items()),
                                      key=lambda d: -d["importance"])},
    }, final, feats
