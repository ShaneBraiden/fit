"""U5 Clustering: discover user personas from behaviour alone.

Features (z-scored): activity mix shares, sessions/week, average duration and
intensity. Partitioning (k-means, k-medoids), hierarchical (agglomerative) and
density-based (DBSCAN) methods are compared with internal measures (SSE,
silhouette, Davies-Bouldin) and external ones against the five planted personas.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from ..algorithms import preprocess as P
from ..algorithms.agglomerative import dendrogram, fcluster, linkage
from ..algorithms.cluster_eval import adjusted_rand_index, contingency, davies_bouldin, nmi, purity, silhouette, sse
from ..algorithms.dbscan import DBSCAN, k_distance
from ..algorithms.kmeans import KMeans
from ..algorithms.kmedoids import KMedoids
from ..algorithms.knn import kneighbors
from ..algorithms.pca import PCA
from ..data import store
from .common import ACTIVITY_SHARES, user_features

FEATURES = ACTIVITY_SHARES + ["sessions_per_week", "avg_duration", "avg_intensity"]
NAMES = {"share_run": "Runners", "share_cycle": "Cyclists", "share_walk": "Walkers", "share_swim": "Swimmers",
         "share_strength": "Lifters", "share_hiit": "HIIT crew", "share_yoga": "Yogis"}


def dataset(con):
    users = store.read("users", con)
    feats = user_features(users, store.read("workouts", con))
    gt = store.read("gt_users", con).set_index("user_id").persona
    feats["persona"] = gt.reindex(feats.user_id).to_numpy()
    X = feats[FEATURES].fillna(feats[FEATURES].median()).to_numpy(float)
    scaler = P.Standardizer().fit(X)
    return feats, scaler.transform(X), scaler


def name_clusters(feats: pd.DataFrame, labels: np.ndarray) -> dict[int, str]:
    """Name each cluster after its dominant activity (plus the runner-up when it is shared)."""
    out = {}
    for c in sorted(set(labels.tolist()) - {-1}):
        shares = feats.loc[labels == c, ACTIVITY_SHARES].mean()
        top = shares.sort_values(ascending=False)
        name = NAMES[top.index[0]]
        if top.iloc[1] > 0.25:
            name += " + " + NAMES[top.index[1]].lower()
        out[c] = name
    seen: dict[str, int] = {}
    for c, n in out.items():  # disambiguate repeated names by training volume
        seen[n] = seen.get(n, 0) + 1
    for n, cnt in seen.items():
        if cnt > 1:
            cs = [c for c in out if out[c] == n]
            vol = {c: feats.loc[labels == c, "sessions_per_week"].mean() for c in cs}
            for rank, c in enumerate(sorted(cs, key=lambda c: -vol[c])):
                out[c] = f"{n} ({'high' if rank == 0 else 'low'} volume)"
    return out


def cluster(Z: np.ndarray, algorithm: str, params: dict) -> dict:
    t = time.perf_counter()
    extra: dict = {}
    if algorithm == "kmeans":
        m = KMeans(int(params.get("k", 5)), n_init=int(params.get("n_init", 5)), seed=int(params.get("seed", 0))).fit(Z)
        labels = m.labels_
        extra = {"iterations": m.n_iter_, "inertia_history": m.history_}
    elif algorithm == "kmedoids":
        m = KMedoids(int(params.get("k", 5)), params.get("method", "pam")).fit(Z)
        labels = m.labels_
        extra = {"medoids": m.medoid_indices_.tolist(), "swaps": m.swaps_, "cost": m.cost_}
    elif algorithm == "agglomerative":
        Zl = linkage(Z, params.get("linkage", "ward"))
        labels = fcluster(Zl, int(params.get("k", 5)))
        extra = {"dendrogram": dendrogram(Zl, 30),
                 "merge_heights": Zl[-30:, 2].round(4).tolist()}
    elif algorithm == "dbscan":
        m = DBSCAN(float(params.get("eps", 1.2)), int(params.get("min_samples", 10))).fit(Z)
        labels = m.labels_
        extra = {"n_noise": int((labels == -1).sum()), "n_core": int(m.core_sample_mask_.sum())}
    else:
        raise ValueError(algorithm)
    extra["ms"] = round((time.perf_counter() - t) * 1000, 1)
    return {"labels": np.asarray(labels), **extra}


def describe(feats, Z, labels, proj) -> dict:
    names = name_clusters(feats, labels)
    s, _ = silhouette(Z, labels)
    truth = feats.persona.to_numpy()
    keep = labels != -1
    M, rows, cols = contingency(labels, truth)
    profiles = []
    for c in sorted(set(labels.tolist())):
        sub = feats[labels == c]
        profiles.append({"cluster": int(c), "name": names.get(c, "Noise"), "size": int(len(sub)),
                         **{f: float(sub[f].mean()) for f in FEATURES},
                         "age": float(sub.age.mean()), "vo2max": float(sub.vo2max.mean())})
    return {
        "n_clusters": int(len(set(labels.tolist()) - {-1})), "names": {int(k): v for k, v in names.items()},
        "sizes": {int(c): int((labels == c).sum()) for c in sorted(set(labels.tolist()))},
        "internal": {"sse": sse(Z, labels), "silhouette": s, "davies_bouldin": davies_bouldin(Z, labels)},
        "external": {"ari": adjusted_rand_index(truth[keep], labels[keep]), "nmi": nmi(truth[keep], labels[keep]),
                     "purity": purity(truth[keep], labels[keep])},
        "contingency": {"clusters": [int(r) for r in rows], "personas": [str(c) for c in cols], "counts": M.tolist()},
        "profiles": profiles,
        "points": [{"x": float(a), "y": float(b), "c": int(c), "user_id": int(u)}
                   for (a, b), c, u in zip(proj, labels, feats.user_id)],
    }


def run_algorithm(feats, Z, proj, algorithm: str, params: dict) -> dict:
    res = cluster(Z, algorithm, params)
    labels = res.pop("labels")
    return {"algorithm": algorithm, "params": params, **res, **describe(feats, Z, labels, proj)}, labels


def run(con) -> dict:
    feats, Z, scaler = dataset(con)
    pca = PCA(2).fit(Z)
    proj = pca.transform(Z)
    sweep = []
    for k in range(2, 11):
        m = KMeans(k, n_init=3, seed=0).fit(Z)
        sweep.append({"k": k, "sse": m.inertia_, "silhouette": silhouette(Z, m.labels_)[0],
                      "davies_bouldin": davies_bouldin(Z, m.labels_)})
    results = {}
    labels_by = {}
    for algo, params in (("kmeans", {"k": 5}), ("kmedoids", {"k": 5}), ("agglomerative", {"k": 5, "linkage": "ward"}),
                         ("dbscan", {"eps": 1.2, "min_samples": 10})):
        results[algo], labels_by[algo] = run_algorithm(feats, Z, proj, algo, params)
    km = KMeans(5, n_init=5, seed=0).fit(Z)
    names = name_clusters(feats, km.labels_)
    # Similar users: 5 nearest neighbours in the standardised behaviour space.
    nb_idx, nb_d = kneighbors(Z, Z, 5, exclude_self=True)
    model = {"scaler": scaler, "centres": km.cluster_centers_, "names": names, "features": FEATURES,
             "medians": feats[FEATURES].median().to_dict(), "Z": Z, "user_ids": feats.user_id.to_numpy()}
    personas = pd.DataFrame({"user_id": feats.user_id, "cluster": km.labels_,
                             "persona": [names[c] for c in km.labels_],
                             "similar": [[int(feats.user_id.iat[j]) for j in row] for row in nb_idx]})
    report = {
        "features": FEATURES, "n_users": int(len(feats)),
        "pca_variance": pca.explained_variance_ratio_.tolist(),
        "k_sweep": sweep,
        "k_distance": k_distance(Z, 9).round(4).tolist(),
        "results": results,
        "comparison": [{"algorithm": a, "n_clusters": r["n_clusters"], **r["internal"], **r["external"],
                        "ms": r["ms"]} for a, r in results.items()],
    }
    return report, model, personas
