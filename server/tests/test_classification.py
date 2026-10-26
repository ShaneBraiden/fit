"""Decision trees, Naive Bayes, kNN and evaluation utilities."""
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier

from fitmine.algorithms.evaluation import (auc, classification_report, cross_validate, roc_curve,
                                           stratified_kfold)
from fitmine.algorithms.knn import KNNClassifier
from fitmine.algorithms.naive_bayes import NaiveBayes
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


def test_id3_play_tennis():
    X, y = TENNIS.drop(columns="Play"), TENNIS.Play
    t = DecisionTree("id3", max_depth=5, min_samples_split=2).fit(X, y)
    assert t.root["feature"] == "Outlook"
    assert t.root["gain"] == pytest.approx(0.2467, abs=1e-3)  # Gain(Outlook) = 0.246
    children = dict(t.root["children"])
    assert children["= Overcast"]["leaf"]
    assert children["= Sunny"]["feature"] == "Humidity"
    assert children["= Rain"]["feature"] == "Wind"
    assert (t.predict(X) == y.to_numpy()).all()


def test_c45_and_cart_run_on_tennis():
    X, y = TENNIS.drop(columns="Play"), TENNIS.Play
    for algo in ("c45", "cart"):
        t = DecisionTree(algo, max_depth=6, min_samples_split=2).fit(X, y)
        assert (t.predict(X) == y.to_numpy()).mean() == 1.0
        assert t.rules()


def _blobs(seed=0, n=300):
    rng = np.random.default_rng(seed)
    centres = np.array([[0, 0, 0], [3, 1, 0], [0, 3, 2]])
    y = rng.integers(0, 3, n)
    X = centres[y] + rng.normal(0, 1.0, (n, 3))
    return pd.DataFrame(X, columns=["a", "b", "c"]), np.array(["p", "q", "r"])[y]


def test_cart_matches_sklearn_gini_tree():
    X, y = _blobs()
    ours = DecisionTree("cart", max_depth=3, min_samples_split=2, min_gain=0).fit(X, y)
    ref = DecisionTreeClassifier(criterion="gini", max_depth=3, random_state=0).fit(X, y)
    assert ours.root["feature"] == X.columns[ref.tree_.feature[0]]
    assert ours.root["threshold"] == pytest.approx(ref.tree_.threshold[0], abs=1e-6)
    assert (ours.predict(X) == ref.predict(X)).mean() > 0.97


def test_reduced_error_pruning_never_hurts_validation():
    X, y = _blobs(1, 400)
    t = DecisionTree("c45", max_depth=10, min_samples_split=2).fit(X.iloc[:250], y[:250])
    before = (t.predict(X.iloc[250:]) == y[250:]).mean()
    t.prune(X.iloc[250:], y[250:])
    after = (t.predict(X.iloc[250:]) == y[250:]).mean()
    assert after >= before


def test_gaussian_nb_matches_sklearn():
    X, y = _blobs(2)
    ours = NaiveBayes().fit(X, y)
    ref = GaussianNB().fit(X, y)
    assert (ours.predict(X) == ref.predict(X)).all()
    np.testing.assert_allclose(ours.predict_proba(X), ref.predict_proba(X), atol=1e-6)


def test_categorical_nb_laplace():
    X, y = TENNIS.drop(columns="Play"), TENNIS.Play
    nb = NaiveBayes(alpha=1).fit(X, y)
    # P(Outlook=Overcast | No) with Laplace: (0 + 1) / (5 + 3)
    assert np.exp(nb.cat_["Outlook"]["No"]["Overcast"]) == pytest.approx(1 / 8)
    q = pd.DataFrame([("Sunny", "Cool", "High", "Strong")], columns=X.columns)
    assert nb.predict(q)[0] == "No"  # the classic textbook query


@pytest.mark.parametrize("weights", ["uniform", "distance"])
def test_knn_matches_sklearn(weights):
    X, y = _blobs(3)
    Xn = X.to_numpy()
    ours = KNNClassifier(7, weights).fit(Xn[:200], y[:200])
    ref = KNeighborsClassifier(7, weights=weights, algorithm="brute").fit(Xn[:200], y[:200])
    assert (ours.predict(Xn[200:]) == ref.predict(Xn[200:])).mean() >= 0.99


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
    pred, proba, labels, folds_acc = cross_validate(lambda: NaiveBayes(), X, yy, k=5)
    assert len(folds_acc) == 5 and (pred == yy).mean() > 0.8
