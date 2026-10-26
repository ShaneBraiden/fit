"""U1 preprocessing primitives and PCA."""
import numpy as np
import pytest
from scipy.stats import chi2_contingency
from sklearn.decomposition import PCA as SkPCA
from sklearn.impute import KNNImputer
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from fitmine.algorithms import preprocess as P
from fitmine.algorithms.pca import PCA


def test_smoothing_by_bins_textbook():
    # H&K section 3.2.2: sorted prices 4, 8, 15, 21, 21, 24, 25, 28, 34 in 3 equal-depth bins.
    price = [4, 8, 15, 21, 21, 24, 25, 28, 34]
    _, means = P.smooth_by_bins(price, 3, "means")
    assert means == [[9, 9, 9], [22, 22, 22], [29, 29, 29]]
    _, bounds = P.smooth_by_bins(price, 3, "boundaries")
    assert bounds == [[4, 4, 15], [21, 21, 24], [25, 25, 34]]


def test_normalisation_textbook_and_sklearn():
    # H&K example: income 73,600 with min 12,000 and max 98,000 -> 0.716
    x = np.array([12000, 73600, 98000.0])
    assert P.min_max(x)[1] == pytest.approx(0.716, abs=1e-3)
    # z-score with mean 54,000 and sd 16,000 -> 1.225 (checked via sklearn on random data)
    r = np.random.default_rng(0).normal(10, 3, (100, 1))
    np.testing.assert_allclose(P.z_score(r[:, 0]), StandardScaler().fit_transform(r)[:, 0])
    np.testing.assert_allclose(P.min_max(r[:, 0]), MinMaxScaler().fit_transform(r)[:, 0])
    scaled, j = P.decimal_scaling(np.array([-986, 917]))
    assert j == 3 and scaled.tolist() == [-0.986, 0.917]


def test_knn_impute_matches_sklearn():
    rng = np.random.default_rng(1)
    X = rng.normal(0, 1, (120, 4))
    X[:, 3] = X[:, 0] * 2 + rng.normal(0, 0.1, 120)
    X[rng.random(X.shape) < 0.08] = np.nan
    np.testing.assert_allclose(P.knn_impute(X, 5), KNNImputer(n_neighbors=5).fit_transform(X), atol=1e-9)


def test_chi_square_textbook():
    # H&K Example 3.1: gender x preferred reading, chi2 = 507.93
    r = P.chi_square([[250, 200], [50, 1000]])
    assert r["chi2"] == pytest.approx(507.93, abs=0.01)
    ref = chi2_contingency([[250, 200], [50, 1000]], correction=False)
    assert r["chi2"] == pytest.approx(ref[0]) and r["p_value"] == pytest.approx(ref[1])


def test_pearson_and_corr_matrix():
    rng = np.random.default_rng(2)
    X = rng.normal(0, 1, (200, 3))
    X[:, 1] += X[:, 0]
    np.testing.assert_allclose(P.correlation_matrix(X), np.corrcoef(X.T), atol=1e-12)


def test_discretisation():
    x = np.r_[np.linspace(0, 1, 50), np.linspace(2, 3, 50)]
    y = np.r_[np.zeros(50), np.ones(50)]
    cuts = P.entropy_discretize(x, y)
    assert len(cuts) == 1 and 1 < cuts[0] < 2
    assert len(P.equal_width_edges(x, 4)) == 5
    edges = P.equal_depth_edges(x, 4)
    counts = np.bincount(P.assign_bins(x, edges))
    assert counts.max() - counts.min() <= 1


def test_pca_matches_sklearn():
    rng = np.random.default_rng(3)
    X = rng.normal(0, 1, (300, 5)) @ rng.normal(0, 1, (5, 5))
    ours = PCA(3).fit(X)
    ref = SkPCA(3).fit(X)
    np.testing.assert_allclose(ours.explained_variance_ratio_, ref.explained_variance_ratio_, rtol=1e-8)
    np.testing.assert_allclose(np.abs(ours.transform(X)), np.abs(ref.transform(X)), atol=1e-8)
