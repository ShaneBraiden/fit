"""Decision trees, Naive Bayes, kNN and evaluation utilities."""
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score
from sklearn.tree import DecisionTreeClassifier

from fitmine.algorithms.evaluation import (auc, classification_report, cross_validate, roc_curve,
                                           stratified_kfold)
from fitmine.algorithms.tree import DecisionTree

# Quinlan's Play Tennis data (H&K Table 8.1 uses the same structure).
TENNIS = pd.DataFrame([
    ("Sunny", "Hot", "High", "Weak", "No"), ("Sunny", "Hot", "High", "Strong", "No"),
    ("Overcast", "Hot", "High", "Weak", "Yes"), ("Rain", "Mild", "High", "Weak", "Yes"),
    ("Rain", "Cool", "Normal", "Weak", "Yes"), ("Rain", "Cool", "Normal", "Strong", "No"),
    ("Overcast", "Cool", "Normal", "Strong", "Yes"), ("Sunny", "Mild", "High", "Weak", "No"),
    ("Sunny", "Cool", "Normal", "Weak", "Yes"), ("Rain", "Mild", "Normal", "Weak", "Yes"),
    ("Sunny", "Mild", "Normal", "Strong", "Yes"), ("Overcast", "Mild", "High", "Strong", "Yes"),
    ("Overcast", "Hot", "Normal", "Weak", "Yes"), ("Rain", "Mild", "High", "Strong", "No"),
], columns=["Outlook", "Temperature", "Humidity", "Wind", "Play"])


def test_c45_play_tennis():
    X, y = TENNIS.drop(columns="Play"), TENNIS.Play
    t = DecisionTree(max_depth=6, min_samples_split=2).fit(X, y)
    assert t.root["feature"] == "Outlook"  # highest gain ratio, as in Quinlan's example
    assert (t.predict(X) == y.to_numpy()).mean() == 1.0
    assert t.rules()


def _blobs(seed=0, n=300):
    rng = np.random.default_rng(seed)
    centres = np.array([[0, 0, 0], [3, 1, 0], [0, 3, 2]])
    y = rng.integers(0, 3, n)
    X = centres[y] + rng.normal(0, 1.0, (n, 3))
    return pd.DataFrame(X, columns=["a", "b", "c"]), np.array(["p", "q", "r"])[y]


def test_roc_auc_matches_sklearn():
    rng = np.random.default_rng(0)
    y = rng.random(500) < 0.3
    s = y * 0.8 + rng.normal(0, 0.6, 500)
    fpr, tpr = roc_curve(y, s)
    assert auc(fpr, tpr) == pytest.approx(roc_auc_score(y, s))


def test_report_and_stratified_folds():
    y = np.array(["a"] * 30 + ["b"] * 10)
    folds = stratified_kfold(y, 5)
    assert sorted(np.concatenate(folds).tolist()) == list(range(40))
    assert all((y[f] == "b").sum() == 2 for f in folds)
    rep = classification_report(["a", "a", "b", "b"], ["a", "b", "b", "b"], ["a", "b"])
    assert rep["accuracy"] == 0.75
    assert rep["confusion"] == [[1, 1], [0, 2]]
    X, yy = _blobs(4)
    pred, proba, labels, folds_acc = cross_validate(lambda: DecisionTree(max_depth=4, min_samples_split=2), X, yy, k=5)
    assert len(folds_acc) == 5 and (pred == yy).mean() > 0.8


def test_c45_numeric_thresholds_close_to_sklearn_entropy_tree():
    X, y = _blobs()
    ours = DecisionTree(max_depth=3, min_samples_split=2, min_gain=0).fit(X, y)
    ref = DecisionTreeClassifier(criterion="entropy", max_depth=3, random_state=0).fit(X, y)
    assert (ours.predict(X) == ref.predict(X)).mean() > 0.9


def test_missing_values_follow_larger_branch():
    X, y = _blobs()
    t = DecisionTree(max_depth=3, min_samples_split=2).fit(X, y)
    row = X.iloc[[0]].copy()
    row[t.root["feature"]] = np.nan
    assert t.predict_proba(row).sum() == pytest.approx(1.0)
