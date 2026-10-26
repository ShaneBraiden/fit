"""Cross-check every from-scratch algorithm against a library implementation on
the project's own data. Each row reports the agreement measure, pass/fail and
both runtimes."""
from __future__ import annotations

import time
from itertools import combinations

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori as mx_apriori
from mlxtend.frequent_patterns import association_rules as mx_rules
from mlxtend.frequent_patterns import fpgrowth as mx_fpgrowth
from scipy.cluster.hierarchy import fcluster as sp_fcluster
from scipy.cluster.hierarchy import linkage as sp_linkage
from scipy.spatial.distance import directed_hausdorff
from scipy.stats import chi2_contingency, spearmanr
from sklearn.cluster import DBSCAN as SkDBSCAN
from sklearn.cluster import KMeans as SkKMeans
from sklearn.decomposition import PCA as SkPCA
from sklearn.ensemble import IsolationForest as SkIF
from sklearn.impute import KNNImputer
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, roc_auc_score, silhouette_score
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier, LocalOutlierFactor
from sklearn.tree import DecisionTreeClassifier

from ..algorithms import preprocess as P
from ..algorithms import trajectory as T
from ..algorithms.agglomerative import fcluster, linkage
from ..algorithms.apriori import apriori
from ..algorithms.cluster_eval import adjusted_rand_index, davies_bouldin, silhouette
from ..algorithms.dbscan import DBSCAN
from ..algorithms.fpgrowth import fpgrowth
from ..algorithms.gsp import contains, gsp
from ..algorithms.iforest import IsolationForest
from ..algorithms.kmeans import KMeans
from ..algorithms.kmedoids import pam
from ..algorithms.knn import KNNClassifier
from ..algorithms.lof import lof
from ..algorithms.naive_bayes import NaiveBayes
from ..algorithms.pca import PCA
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

    def add(unit, algo, ref, metric, value, ok, ours_ms, ref_ms, note=""):
        rows.append({"unit": unit, "algorithm": algo, "reference": ref, "metric": metric,
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

    # ---- U1
    sub = w[["avg_hr", "max_hr", "duration_min", "calories"]].to_numpy(float)[:3000]
    mine, a = _t(lambda: P.knn_impute(sub, 5))
    ref, b = _t(lambda: KNNImputer(n_neighbors=5).fit_transform(sub))
    d = float(np.nanmax(np.abs(mine - ref)))
    add("U1", "kNN imputation", "sklearn KNNImputer", "max |diff|", d, d < 1e-6, a, b)
    mine, a = _t(lambda: PCA().fit(Z).explained_variance_ratio_)
    ref, b = _t(lambda: SkPCA().fit(Z).explained_variance_ratio_)
    d = float(np.abs(mine - ref).max())
    add("U1", "PCA", "sklearn PCA", "max |EVR diff|", d, d < 1e-9, a, b)
    R, a = _t(lambda: P.correlation_matrix(X))
    Rr, b = _t(lambda: np.corrcoef(X.T))
    d = float(np.abs(R - Rr).max())
    add("U1", "Pearson correlation", "numpy corrcoef", "max |diff|", d, d < 1e-9, a, b)
    tab = pd.crosstab(users.gender, users.age_group).to_numpy()
    mine, a = _t(lambda: P.chi_square(tab)["chi2"])
    ref, b = _t(lambda: chi2_contingency(tab, correction=False)[0])
    add("U1", "Chi-square test", "scipy chi2_contingency", "|chi2 diff|", abs(mine - ref), abs(mine - ref) < 1e-9, a, b)

    # ---- U3
    ex = store.read("exercises", con)
    tx = ex[ex.workout_id.isin(w.workout_id)].groupby("workout_id").exercise.apply(sorted).tolist()
    items = sorted({i for t in tx for i in t})
    onehot = pd.DataFrame(np.array([[i in set(t) for i in items] for t in tx]), columns=items)
    for name, ours, theirs in (("Apriori", apriori, mx_apriori), ("FP-Growth", fpgrowth, mx_fpgrowth)):
        (mine, _), a = _t(lambda: ours(tx, 0.02))
        ref, b = _t(lambda: theirs(onehot, min_support=0.02, use_colnames=True))
        refd = {frozenset(r.itemsets): r.support for r in ref.itertuples()}
        same = set(mine) == set(refd)
        diff = max(abs(mine[k] - refd[k]) for k in refd) if same else 1.0
        add("U3", name, f"mlxtend {theirs.__name__}", "itemsets equal / max support diff", diff, same and diff < 1e-12,
            a, b, f"{len(mine)} itemsets")
    sets, _ = fpgrowth(tx, 0.02)
    mr, a = _t(lambda: generate_rules(sets, 0.6))
    rr, b = _t(lambda: mx_rules(mx_fpgrowth(onehot, min_support=0.02, use_colnames=True), metric="confidence",
                                min_threshold=0.6))
    md = {(frozenset(r["antecedent"]), frozenset(r["consequent"])): r["lift"] for r in mr}
    diff = max(abs(md.get((frozenset(r.antecedents), frozenset(r.consequents)), -1) - r.lift) for r in rr.itertuples())
    add("U3", "Rule generation", "mlxtend association_rules", "max |lift diff|", diff,
        len(md) == len(rr) and diff < 1e-9, a, b, f"{len(md)} rules")

    # ---- U4
    Xl, yl = X[lab], level[lab]
    tr, te = np.arange(len(yl)) % 4 != 0, np.arange(len(yl)) % 4 == 0
    df = pd.DataFrame(Xl, columns=num)
    t_ours, a = _t(lambda: DecisionTree("cart", 5, 2, 0).fit(df[tr], yl[tr]))
    t_ref, b = _t(lambda: DecisionTreeClassifier(criterion="gini", max_depth=5, random_state=0).fit(Xl[tr], yl[tr]))
    agree = float((t_ours.predict(df[te]) == t_ref.predict(Xl[te])).mean())
    add("U4", "CART tree", "sklearn DecisionTreeClassifier (gini)", "test prediction agreement", agree, agree > 0.9,
        a, b, f"root: {t_ours.root['feature']} vs {num[t_ref.tree_.feature[0]]}")
    t_ours, a = _t(lambda: DecisionTree("c45", 5, 2, 0).fit(df[tr], yl[tr]))
    t_ref, b = _t(lambda: DecisionTreeClassifier(criterion="entropy", max_depth=5, random_state=0).fit(Xl[tr], yl[tr]))
    acc_o = float((t_ours.predict(df[te]) == yl[te]).mean())
    acc_r = float((t_ref.predict(Xl[te]) == yl[te]).mean())
    add("U4", "C4.5 tree", "sklearn tree (entropy)", "test accuracy difference", acc_o - acc_r, abs(acc_o - acc_r) < 0.08,
        a, b, f"ours {acc_o:.3f} vs sklearn {acc_r:.3f} (gain ratio vs info gain)")
    nb_o, a = _t(lambda: NaiveBayes().fit(df[tr], yl[tr]))
    nb_r, b = _t(lambda: GaussianNB().fit(Xl[tr], yl[tr]))
    d = float(np.abs(nb_o.predict_proba(df[te]) - nb_r.predict_proba(Xl[te])).max())
    add("U4", "Gaussian Naive Bayes", "sklearn GaussianNB", "max |probability diff|", d, d < 1e-6, a, b)
    Zl = Z[lab]
    k_o, a = _t(lambda: KNNClassifier(7, "distance").fit(Zl[tr], yl[tr]))
    k_r, b = _t(lambda: KNeighborsClassifier(7, weights="distance", algorithm="brute").fit(Zl[tr], yl[tr]))
    agree = float((k_o.predict(Zl[te]) == k_r.predict(Zl[te])).mean())
    add("U4", "k-NN", "sklearn KNeighborsClassifier", "prediction agreement", agree, agree > 0.99, a, b)

    # ---- U5
    init = Z[[0, 100, 200, 300, 400]]
    km_o, a = _t(lambda: KMeans(5, init=init.copy()).fit(Z))
    km_r, b = _t(lambda: SkKMeans(5, init=init.copy(), n_init=1, algorithm="lloyd", tol=0).fit(Z))
    ari = adjusted_rand_index(km_r.labels_, km_o.labels_)
    add("U5", "k-means", "sklearn KMeans (same init)", "ARI", ari, ari > 0.999, a, b,
        f"inertia {km_o.inertia_:.2f} vs {km_r.inertia_:.2f}")
    small = Z[:40]
    D = np.sqrt(((small[:, None] - small[None]) ** 2).sum(-1))
    (med, _, cost, _), a = _t(lambda: pam(D, 3))

    def brute():
        best = min(D[:, list(c)].min(1).sum() for c in combinations(range(len(small)), 3))
        # PAM's guarantee: no single medoid/non-medoid swap lowers the cost (a local optimum).
        swaps = [D[:, [h if m == i else m for m in med]].min(1).sum() for i in med for h in range(len(small))
                 if h not in med]
        return best, min(swaps)
    (best, best_swap), b = _t(brute)
    add("U5", "k-medoids (PAM)", "exhaustive search, 40 users k=3", "cost / global optimum", cost / best,
        best_swap >= cost - 1e-9 and cost / best < 1.05, a, b,
        "local optimum: no improving swap" if best_swap >= cost - 1e-9 else "an improving swap exists")
    for method in ("average", "ward"):
        Zo, a = _t(lambda: linkage(Z, method))
        Zr, b = _t(lambda: sp_linkage(Z, method))
        d = float(np.abs(np.sort(Zo[:, 2]) - np.sort(Zr[:, 2])).max())
        ari = adjusted_rand_index(sp_fcluster(Zr, 5, "maxclust"), fcluster(Zo, 5))
        add("U5", f"Agglomerative ({method})", "scipy linkage", "max |merge height diff|", d, d < 1e-6, a, b,
            f"ARI at k=5: {ari:.3f}")
    db_o, a = _t(lambda: DBSCAN(1.2, 10).fit(Z))
    db_r, b = _t(lambda: SkDBSCAN(eps=1.2, min_samples=10).fit(Z))
    ari = adjusted_rand_index(db_r.labels_, db_o.labels_)
    add("U5", "DBSCAN", "sklearn DBSCAN", "ARI (noise included)", ari, ari > 0.999, a, b)
    labels = km_o.labels_
    (s, _), a = _t(lambda: silhouette(Z, labels, sample=None))
    sr, b = _t(lambda: silhouette_score(Z, labels))
    add("U5", "Silhouette", "sklearn silhouette_score", "|diff|", abs(s - sr), abs(s - sr) < 1e-9, a, b)
    dbi, a = _t(lambda: davies_bouldin(Z, labels))
    dbr, b = _t(lambda: davies_bouldin_score(Z, labels))
    add("U5", "Davies-Bouldin", "sklearn davies_bouldin_score", "|diff|", abs(dbi - dbr), abs(dbi - dbr) < 1e-9, a, b)
    gt = store.read("gt_users", con).set_index("user_id").persona.reindex(feats.user_id).to_numpy()
    ar, a = _t(lambda: adjusted_rand_index(gt, labels))
    arr, b = _t(lambda: adjusted_rand_score(gt, labels))
    add("U5", "Adjusted Rand index", "sklearn adjusted_rand_score", "|diff|", abs(ar - arr), abs(ar - arr) < 1e-12, a, b)

    # ---- U6
    F = store.read("workout_features", con)
    runs = F[F.activity == "Run"]
    cols = ["hr_max", "hr_mean", "hr_std", "hr_zero_frac", "hr_flat_frac", "calorie_ratio", "speed_avg", "speed_p95",
            "step_max_m", "hr_per_speed"]
    Xr = P.Standardizer().fit_transform(runs[cols].fillna(0).to_numpy(float))
    lo, a = _t(lambda: lof(Xr, 20))
    lr, b = _t(lambda: -LocalOutlierFactor(n_neighbors=20).fit(Xr).negative_outlier_factor_)
    d = float(np.abs(lo - lr).max())
    add("U6", "Local Outlier Factor", "sklearn LocalOutlierFactor", "max |LOF diff|", d, d < 1e-6, a, b)
    truth = store.read("gt_workouts", con).set_index("workout_id").fault_type.reindex(runs.workout_id).notna()
    io, a = _t(lambda: IsolationForest(100, 256, seed=0).fit(Xr).score(Xr))
    ir, b = _t(lambda: -SkIF(n_estimators=100, random_state=0).fit(Xr).score_samples(Xr))
    rho = spearmanr(io, ir).statistic
    auc_o, auc_r = roc_auc_score(truth, io), roc_auc_score(truth, ir)
    add("U6", "Isolation Forest", "sklearn IsolationForest", "Spearman rank correlation", rho, rho > 0.85, a, b,
        f"AUC vs planted faults: ours {auc_o:.3f}, sklearn {auc_r:.3f}")

    # ---- U7
    from .u7_sequences_trajectories import gps_tracks, week_sequences
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
    add("U7", "GSP", "brute-force enumeration (400 user-weeks)", "same frequent patterns", float(ok), ok, a, b,
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
    add("U7", "Hausdorff distance", "scipy directed_hausdorff", "max |diff| (m)", d, d < 1e-6, a, b)

    return {"rows": rows, "passed": sum(r["pass"] for r in rows), "total": len(rows)}
