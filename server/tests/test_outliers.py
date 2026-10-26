"""LOF, Isolation Forest and the statistical tests."""
import numpy as np
from sklearn.ensemble import IsolationForest as SkIF
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import LocalOutlierFactor

from fitmine.algorithms.iforest import IsolationForest
from fitmine.algorithms.lof import fit_reference, lof, lof_novelty
from fitmine.algorithms.outliers import grubbs, iqr_fences, robust_z_scores, zscore_scores


def data(seed=0):
    rng = np.random.default_rng(seed)
    inl = rng.normal(0, 1, (500, 3))
    out = rng.uniform(4, 8, (25, 3)) * rng.choice([-1, 1], (25, 3))
    X = np.vstack([inl, out])
    y = np.r_[np.zeros(500), np.ones(25)]
    return X, y


def test_lof_matches_sklearn():
    X, _ = data()
    ref = LocalOutlierFactor(n_neighbors=20).fit(X)
    np.testing.assert_allclose(lof(X, 20), -ref.negative_outlier_factor_, rtol=1e-6)


def test_lof_novelty_matches_sklearn():
    X, _ = data(1)
    Q = np.random.default_rng(2).normal(0, 2, (40, 3))
    ref = LocalOutlierFactor(n_neighbors=20, novelty=True).fit(X)
    model = fit_reference(X, 20)
    ours = lof_novelty(model["X"], model["lrd"], model["k_dist"], Q, 20)
    np.testing.assert_allclose(ours, -ref.score_samples(Q), rtol=1e-6)


def test_isolation_forest_separates_and_agrees_with_sklearn():
    X, y = data(3)
    ours = IsolationForest(200, 256, seed=0).fit(X).score(X)
    ref = -SkIF(n_estimators=200, random_state=0).fit(X).score_samples(X)
    assert roc_auc_score(y, ours) > 0.95
    assert np.corrcoef(ours, ref)[0, 1] > 0.9


def test_statistical_tests():
    x = np.r_[np.random.default_rng(4).normal(50, 5, 200), [120, 130, -20]]
    assert set(grubbs(x)) >= {200, 201, 202}
    lo, hi = iqr_fences(x)
    assert 30 < lo < 45 and 55 < hi < 70  # Q1/Q3 of N(50, 5) +- 1.5 IQR
    assert {200, 201, 202} <= set(np.where((x < lo) | (x > hi))[0].tolist())
    assert zscore_scores(x)[201] > 3 and robust_z_scores(x)[201] > 3.5


def test_grubbs_single_gross_error():
    # A tight sample with one gross error: only that reading is rejected.
    x = np.array([199.31, 199.53, 200.19, 200.82, 201.92, 201.95, 202.18, 245.57])
    assert grubbs(x) == [7]
