"""k-means, k-medoids, agglomerative, DBSCAN and validity measures against sklearn/scipy."""
from itertools import combinations

import numpy as np
import pytest
from scipy.cluster.hierarchy import fcluster as sp_fcluster
from scipy.cluster.hierarchy import linkage as sp_linkage
from sklearn.cluster import DBSCAN as SkDBSCAN
from sklearn.cluster import KMeans as SkKMeans
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score

from fitmine.algorithms.agglomerative import cophenetic_matrix, dendrogram, fcluster, linkage
from fitmine.algorithms.cluster_eval import adjusted_rand_index, davies_bouldin, nmi, purity, silhouette
from fitmine.algorithms.dbscan import DBSCAN, k_distance
from fitmine.algorithms.kmeans import KMeans
from fitmine.algorithms.kmedoids import KMedoids, pam


def blobs(seed=0, n=240, d=2, spread=0.6):
    rng = np.random.default_rng(seed)
    centres = rng.uniform(-6, 6, (4, d))
    y = rng.integers(0, 4, n)
    return centres[y] + rng.normal(0, spread, (n, d)), y


def test_kmeans_matches_sklearn_from_same_init():
    X, _ = blobs()
    init = X[[0, 50, 100, 150]]
    ours = KMeans(4, init=init.copy()).fit(X)
    ref = SkKMeans(4, init=init.copy(), n_init=1, algorithm="lloyd", tol=0).fit(X)
    assert adjusted_rand_index(ref.labels_, ours.labels_) == pytest.approx(1.0)
    assert ours.inertia_ == pytest.approx(ref.inertia_, rel=1e-6)


def test_pam_finds_optimal_medoids_on_small_data():
    X, _ = blobs(1, n=24)
    D = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1))
    _, _, cost, _ = pam(D, 2)
    brute = min(D[:, list(c)].min(1).sum() for c in combinations(range(len(X)), 2))
    assert cost == pytest.approx(brute)


def test_clara_close_to_pam():
    X, y = blobs(2, n=600)
    a = KMedoids(4, "pam").fit(X)
    b = KMedoids(4, "clara", sample_size=150).fit(X)
    assert b.cost_ <= a.cost_ * 1.05


@pytest.mark.parametrize("method", ["single", "complete", "average", "ward"])
def test_linkage_matches_scipy(method):
    X, _ = blobs(3, n=80)
    Z = linkage(X, method)
    R = sp_linkage(X, method)
    np.testing.assert_allclose(np.sort(Z[:, 2]), np.sort(R[:, 2]), rtol=1e-8, atol=1e-8)
    assert adjusted_rand_index(sp_fcluster(R, 4, "maxclust"), fcluster(Z, 4)) == pytest.approx(1.0)


def test_dendrogram_and_cophenetic():
    X, _ = blobs(4, n=40)
    Z = linkage(X, "average")
    d = dendrogram(Z, p=10)
    assert len(d["leaves"]) == 10 and len(d["icoord"]) == 9
    assert sum(leaf["size"] for leaf in d["leaves"]) == 40
    C = cophenetic_matrix(Z)
    assert np.allclose(C, C.T)


@pytest.mark.parametrize("d,eps", [(2, 0.5), (5, 1.4)])
def test_dbscan_matches_sklearn(d, eps):
    X, _ = blobs(5, n=300, d=d)
    X = np.vstack([X, np.random.default_rng(0).uniform(-9, 9, (15, d))])
    ours = DBSCAN(eps, 5).fit(X)
    ref = SkDBSCAN(eps=eps, min_samples=5).fit(X)
    assert (ours.core_sample_mask_ == np.isin(np.arange(len(X)), ref.core_sample_indices_)).all()
    assert ((ours.labels_ == -1) == (ref.labels_ == -1)).all()
    assert adjusted_rand_index(ref.labels_, ours.labels_) == pytest.approx(1.0)


def test_dbscan_precomputed_and_kdistance():
    X, _ = blobs(6, n=120)
    D = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1))
    a = DBSCAN(0.6, 4, "precomputed").fit(D).labels_
    b = DBSCAN(0.6, 4).fit(X).labels_
    assert (a == b).all()
    kd = k_distance(X, 4)
    assert (np.diff(kd) <= 0).all()


def test_validity_measures_match_sklearn():
    X, y = blobs(7, n=200)
    labels = KMeans(4, seed=1).fit(X).labels_
    s, _ = silhouette(X, labels, sample=None)
    assert s == pytest.approx(silhouette_score(X, labels))
    assert davies_bouldin(X, labels) == pytest.approx(davies_bouldin_score(X, labels))
    assert adjusted_rand_index(y, labels) == pytest.approx(adjusted_rand_score(y, labels))
    assert 0 <= purity(y, labels) <= 1 and 0 <= nmi(y, labels) <= 1
