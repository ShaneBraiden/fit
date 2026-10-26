"""Cross-check every from-scratch algorithm the app uses against a library
implementation on the project's own data. Each row reports the agreement
measure, pass/fail and both runtimes."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import association_rules as mx_rules
from mlxtend.frequent_patterns import fpgrowth as mx_fpgrowth
from scipy.spatial.distance import directed_hausdorff
from scipy.stats import spearmanr
from sklearn.cluster import DBSCAN as SkDBSCAN
from sklearn.cluster import KMeans as SkKMeans
from sklearn.ensemble import IsolationForest as SkIF
from sklearn.impute import KNNImputer
from sklearn.metrics import adjusted_rand_score, roc_auc_score, silhouette_score
from sklearn.tree import DecisionTreeClassifier

from ..algorithms import preprocess as P
from ..algorithms import trajectory as T
from ..algorithms.cluster_eval import adjusted_rand_index, silhouette
from ..algorithms.dbscan import DBSCAN
from ..algorithms.fpgrowth import fpgrowth
from ..algorithms.gsp import contains, gsp
from ..algorithms.iforest import IsolationForest
from ..algorithms.kmeans import KMeans
from ..algorithms.rules import generate_rules
from ..algorithms.tree import DecisionTree
from ..data import store
from .common import user_features


def _t(fn):
    t = time.perf_counter()
    out = fn()
    return out, round((time.perf_counter() - t) * 1000, 1)


def run(con) -> dict:
    rows = []

    def add(feature, algo, ref, metric, value, ok, ours_ms, ref_ms, note=""):
        rows.append({"feature": feature, "algorithm": algo, "reference": ref, "metric": metric,
                     "value": float(value), "pass": bool(ok), "ours_ms": ours_ms, "ref_ms": ref_ms, "note": note})

    users = store.read("users", con)
    w = store.read("workouts", con)
    feats = user_features(users, w)
    num = ["age", "bmi", "resting_hr", "vo2max", "sessions_per_week", "minutes_per_week", "avg_intensity",
           "share_run", "share_strength", "share_hiit", "share_yoga", "share_walk", "share_cycle"]
    X = feats[num].fillna(feats[num].median()).to_numpy(float)
    Z = P.Standardizer().fit_transform(X)
    level = users.set_index("user_id").assessed_level.reindex(feats.user_id).to_numpy()
    lab = pd.notna(level)

    sub = w[["avg_hr", "max_hr", "duration_min", "calories"]].to_numpy(float)[:3000]
    mine, a = _t(lambda: P.knn_impute(sub, 5))
    ref, b = _t(lambda: KNNImputer(n_neighbors=5).fit_transform(sub))
    d = float(np.nanmax(np.abs(mine - ref)))
    add("Data cleaning", "kNN imputation", "sklearn KNNImputer", "max |diff|", d, d < 1e-6, a, b)

    ex = store.read("exercises", con)
    tx = ex[ex.workout_id.isin(w.workout_id)].groupby("workout_id").exercise.apply(sorted).tolist()
    items = sorted({i for t in tx for i in t})
    onehot = pd.DataFrame(np.array([[i in set(t) for i in items] for t in tx]), columns=items)
    (mine, _), a = _t(lambda: fpgrowth(tx, 0.02))
    ref, b = _t(lambda: mx_fpgrowth(onehot, min_support=0.02, use_colnames=True))
    refd = {frozenset(r.itemsets): r.support for r in ref.itertuples()}
    same = set(mine) == set(refd)
    diff = max(abs(mine[k] - refd[k]) for k in refd) if same else 1.0
    add("Suggestions", "FP-Growth", "mlxtend fpgrowth", "itemsets equal / max support diff", diff,
        same and diff < 1e-12, a, b, f"{len(mine)} itemsets")
    sets, _ = fpgrowth(tx, 0.02)
    mr, a = _t(lambda: generate_rules(sets, 0.6))
    rr, b = _t(lambda: mx_rules(mx_fpgrowth(onehot, min_support=0.02, use_colnames=True), metric="confidence",
                                min_threshold=0.6))
    md = {(frozenset(r["antecedent"]), frozenset(r["consequent"])): r["lift"] for r in mr}
    diff = max(abs(md.get((frozenset(r.antecedents), frozenset(r.consequents)), -1) - r.lift) for r in rr.itertuples())
    add("Suggestions", "Rule generation", "mlxtend association_rules", "max |lift diff|", diff,
        len(md) == len(rr) and diff < 1e-9, a, b, f"{len(md)} rules")

    Xl, yl = X[lab], level[lab]
    tr, te = np.arange(len(yl)) % 4 != 0, np.arange(len(yl)) % 4 == 0
    df = pd.DataFrame(Xl, columns=num)
    t_ours, a = _t(lambda: DecisionTree(5, 2, 0).fit(df[tr], yl[tr]))
    t_ref, b = _t(lambda: DecisionTreeClassifier(criterion="entropy", max_depth=5, random_state=0).fit(Xl[tr], yl[tr]))
    acc_o = float((t_ours.predict(df[te]) == yl[te]).mean())
    acc_r = float((t_ref.predict(Xl[te]) == yl[te]).mean())
    add("Fitness level", "C4.5 tree", "sklearn tree (entropy)", "test accuracy difference", acc_o - acc_r, abs(acc_o - acc_r) < 0.08,
        a, b, f"ours {acc_o:.3f} vs sklearn {acc_r:.3f} (gain ratio vs info gain)")

    init = Z[[0, 100, 200, 300, 400]]
    km_o, a = _t(lambda: KMeans(5, init=init.copy()).fit(Z))
    km_r, b = _t(lambda: SkKMeans(5, init=init.copy(), n_init=1, algorithm="lloyd", tol=0).fit(Z))
    ari = adjusted_rand_index(km_r.labels_, km_o.labels_)
    add("Personas", "k-means", "sklearn KMeans (same init)", "ARI", ari, ari > 0.999, a, b,
        f"inertia {km_o.inertia_:.2f} vs {km_r.inertia_:.2f}")
    labels = km_o.labels_
    (s, _), a = _t(lambda: silhouette(Z, labels, sample=None))
    sr, b = _t(lambda: silhouette_score(Z, labels))
    add("Personas", "Silhouette", "sklearn silhouette_score", "|diff|", abs(s - sr), abs(s - sr) < 1e-9, a, b)
    gt = store.read("gt_users", con).set_index("user_id").persona.reindex(feats.user_id).to_numpy()
    ar, a = _t(lambda: adjusted_rand_index(gt, labels))
    arr, b = _t(lambda: adjusted_rand_score(gt, labels))
    add("Personas", "Adjusted Rand index", "sklearn adjusted_rand_score", "|diff|", abs(ar - arr), abs(ar - arr) < 1e-12, a, b)

    F = store.read("workout_features", con)
    runs = F[F.activity == "Run"]
    cols = ["hr_max", "hr_mean", "hr_std", "hr_zero_frac", "hr_flat_frac", "calorie_ratio", "speed_avg", "speed_p95",
            "step_max_m", "hr_per_speed"]
    Xr = P.Standardizer().fit_transform(runs[cols].fillna(0).to_numpy(float))
    truth = store.read("gt_workouts", con).set_index("workout_id").fault_type.reindex(runs.workout_id).notna()
    io, a = _t(lambda: IsolationForest(100, 256, seed=0).fit(Xr).score(Xr))
    ir, b = _t(lambda: -SkIF(n_estimators=100, random_state=0).fit(Xr).score_samples(Xr))
    rho = spearmanr(io, ir).statistic
    auc_o, auc_r = roc_auc_score(truth, io), roc_auc_score(truth, ir)
    add("Data checks", "Isolation Forest", "sklearn IsolationForest", "Spearman rank correlation", rho, rho > 0.85, a, b,
        f"AUC vs planted faults: ours {auc_o:.3f}, sklearn {auc_r:.3f}")

    from .routines_routes import gps_tracks, week_sequences
    seqs, _ = week_sequences(con)
    small = seqs[:400]
    (pats, _), a = _t(lambda: gsp(small, 0.05, max_gap=4, max_len=3))
    sdb = [[(t, frozenset(i)) for t, i in s] for s in small]
    toks = sorted({i for s in small for _, it in s for i in it})

    def every_pattern(p=(), k=0):
        """All patterns of up to 3 items over the tokens (elements are sorted itemsets)."""
        if k == 3:
            return
        for x in toks:
            q = p + ((x,),)
            yield q
            yield from every_pattern(q, k + 1)
            if p and x > p[-1][-1]:
                q2 = p[:-1] + (p[-1] + (x,),)
                yield q2
                yield from every_pattern(q2, k + 1)

    def brute():
        need = 0.05 * len(sdb)
        return {p for p in set(every_pattern()) if sum(contains(s, p, 4) for s in sdb) >= need}
    ref, b = _t(brute)
    ok = set(pats) == ref
    add("Routines", "GSP", "brute-force enumeration (400 user-weeks)", "same frequent patterns", float(ok), ok, a, b,
        f"{len(pats)} patterns")
    gw, streams = gps_tracks(con)
    ids = gw.workout_id.to_numpy()[:60]
    tracks = np.stack([T.resample(T.xy(streams[i]["lat"], streams[i]["lon"]), 20) for i in ids])
    H, a = _t(lambda: T.hausdorff_matrix(tracks))

    def sp_h():
        return np.array([[max(directed_hausdorff(p, q)[0], directed_hausdorff(q, p)[0]) for q in tracks]
                         for p in tracks])
    Hr, b = _t(sp_h)
    d = float(np.abs(H - Hr).max())
    add("Routes", "Hausdorff distance", "scipy directed_hausdorff", "max |diff| (m)", d, d < 1e-6, a, b)
    db_o, a = _t(lambda: DBSCAN(150.0, 3, "precomputed").fit(H))
    db_r, b = _t(lambda: SkDBSCAN(eps=150.0, min_samples=3, metric="precomputed").fit(Hr))
    ari = adjusted_rand_index(db_r.labels_, db_o.labels_)
    add("Routes", "DBSCAN (precomputed Hausdorff)", "sklearn DBSCAN", "ARI (noise included)", ari, ari > 0.999, a, b)

    return {"rows": rows, "passed": sum(r["pass"] for r in rows), "total": len(rows)}
