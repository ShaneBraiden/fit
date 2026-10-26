"""Training personas: group users by how they train, from behaviour alone.

Features (z-scored): activity mix shares, sessions/week, average duration and
intensity. k-means with k-means++ seeding; k = 5 is chosen from the SSE elbow
and the silhouette peak. Clusters are named after their dominant activity and
checked against the five planted personas (ARI, purity). A new user is assigned
to the nearest cluster centre.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..algorithms import preprocess as P
from ..algorithms.cluster_eval import adjusted_rand_index, contingency, nmi, purity, silhouette, sse
from ..algorithms.kmeans import KMeans
from ..data import store
from .common import ACTIVITY_SHARES, user_features

FEATURES = ACTIVITY_SHARES + ["sessions_per_week", "avg_duration", "avg_intensity"]
K = 5
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
    for c in sorted(set(labels.tolist())):
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


def run(con) -> tuple[dict, dict, pd.DataFrame]:
    feats, Z, scaler = dataset(con)
    sweep = []
    for k in range(2, 11):
        m = KMeans(k, n_init=3, seed=0).fit(Z)
        sweep.append({"k": k, "sse": m.inertia_, "silhouette": silhouette(Z, m.labels_)[0]})
    km = KMeans(K, n_init=5, seed=0).fit(Z)
    labels = km.labels_
    names = name_clusters(feats, labels)
    truth = feats.persona.to_numpy()
    M, rows, cols = contingency(labels, truth)
    profiles = []
    for c in sorted(set(labels.tolist())):
        sub = feats[labels == c]
        profiles.append({"cluster": int(c), "name": names[c], "size": int(len(sub)),
                         **{f: float(sub[f].mean()) for f in FEATURES},
                         "age": float(sub.age.mean()), "vo2max": float(sub.vo2max.mean())})
    model = {"scaler": scaler, "centres": km.cluster_centers_, "names": names, "features": FEATURES,
             "medians": feats[FEATURES].median().to_dict()}
    personas = pd.DataFrame({"user_id": feats.user_id, "cluster": labels, "persona": [names[c] for c in labels]})
    report = {
        "features": FEATURES, "n_users": int(len(feats)), "k": K, "k_sweep": sweep,
        "iterations": km.n_iter_, "inertia_history": km.history_,
        "names": {int(k): v for k, v in names.items()},
        "internal": {"sse": sse(Z, labels), "silhouette": silhouette(Z, labels)[0]},
        "external": {"ari": adjusted_rand_index(truth, labels), "nmi": nmi(truth, labels),
                     "purity": purity(truth, labels)},
        "contingency": {"clusters": [int(r) for r in rows], "personas": [str(c) for c in cols], "counts": M.tolist()},
        "profiles": profiles,
    }
    return report, model, personas
