"""U1 preprocessing primitives and PCA."""
import numpy as np
from sklearn.impute import KNNImputer
from sklearn.preprocessing import StandardScaler

from fitmine.algorithms import preprocess as P


def test_knn_impute_matches_sklearn():
    rng = np.random.default_rng(1)
    X = rng.normal(0, 1, (120, 4))
    X[:, 3] = X[:, 0] * 2 + rng.normal(0, 0.1, 120)
    X[rng.random(X.shape) < 0.08] = np.nan
    np.testing.assert_allclose(P.knn_impute(X, 5), KNNImputer(n_neighbors=5).fit_transform(X), atol=1e-9)


def test_standardizer_matches_sklearn():
    X = np.random.default_rng(1).normal(5, 3, (50, 4))
    np.testing.assert_allclose(P.Standardizer().fit_transform(X), StandardScaler().fit_transform(X))


def test_mean_baseline_fills_with_mean():
    x = np.array([1.0, np.nan, 3.0])
    assert P.impute_mean(x).tolist() == [1.0, 2.0, 3.0]
