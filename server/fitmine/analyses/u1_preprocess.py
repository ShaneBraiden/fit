"""U1 Data preprocessing: profile the raw app data, clean it, write the clean tables.

Cleaning steps, each scored against the planted ground truth where possible:
  1. activity label normalisation (synonyms, case)          -> mapping table
  2. unit harmonisation (lb -> kg, mi -> km)
  3. re-sync duplicate removal                              -> precision / recall
  4. session type from free-text titles                     -> accuracy
  5. missing value imputation, method chosen by RMSE against the true hidden values
Then the textbook transformations on the clean data: smoothing by bins,
normalisation, discretisation, correlation / chi-square, PCA and sampling.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .. import config as C
from ..algorithms import preprocess as P
from ..algorithms.pca import PCA
from ..data import store
from .common import ACTIVITY_SHARES, histogram, user_features

SYNONYMS = {
    "run": "Run", "running": "Run", "jog": "Run",
    "cycle": "Cycle", "cycling": "Cycle", "bike": "Cycle",
    "walk": "Walk", "walking": "Walk",
    "swim": "Swim", "swimming": "Swim",
    "strength": "Strength", "weights": "Strength", "strength training": "Strength",
    "hiit": "HIIT", "circuit": "HIIT",
    "yoga": "Yoga", "yoga flow": "Yoga",
}
TITLE_RULES = [
    (r"push|chest", "Push"), (r"pull|back", "Pull"), (r"leg|lower body", "Legs"),
    (r"interval|speed work|track", "IntervalRun"), (r"tempo|threshold", "TempoRun"), (r"long|lsd", "LongRun"),
    (r"hiit|tabata|bootcamp", "HIIT"), (r"yoga|vinyasa", "Yoga"), (r"walk", "Walk"),
    (r"ride|cycl", "Cycle"), (r"swim|pool", "Swim"), (r"run", "EasyRun"),
]
ACTIVITY_DEFAULT_SESSION = {"Run": "EasyRun", "Strength": "Push", "HIIT": "HIIT", "Yoga": "Yoga", "Walk": "Walk",
                            "Cycle": "Cycle", "Swim": "Swim"}
AGE_GROUPS = [(18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 54, "45-54"), (55, 200, "55+")]


def normalise_activity(label: str) -> str | None:
    return SYNONYMS.get(str(label).strip().lower())


def session_from_title(title: str, activity: str) -> str:
    t = str(title).lower()
    for pat, tok in TITLE_RULES:
        if re.search(pat, t):
            return tok
    return ACTIVITY_DEFAULT_SESSION.get(activity, activity)


def age_group(age) -> str:
    return next(lab for lo, hi, lab in AGE_GROUPS if lo <= age <= hi)


def quality(df: pd.DataFrame) -> list[dict]:
    out = []
    for c in df.columns:
        s = df[c]
        out.append({"column": c, "dtype": str(s.dtype), "missing": int(s.isna().sum()),
                    "missing_pct": round(100 * float(s.isna().mean()), 2), "distinct": int(s.nunique()),
                    "example": None if s.dropna().empty else str(s.dropna().iloc[0])})
    return out


def find_resync_duplicates(w: pd.DataFrame, max_gap_s: int = 120) -> dict[int, int]:
    """duplicate workout_id -> kept workout_id: same user and activity, starts within
    max_gap_s seconds, same duration and distance."""
    w = w.sort_values(["user_id", "activity", "start_time", "workout_id"])
    dup = {}
    prev = None
    for r in w.itertuples():
        if prev is not None and r.user_id == prev.user_id and r.activity == prev.activity \
                and (r.start_time - prev.start_time).total_seconds() <= max_gap_s \
                and abs(r.duration_min - prev.duration_min) < 0.5 \
                and ((pd.isna(r.distance_km) and pd.isna(prev.distance_km))
                     or abs((r.distance_km or 0) - (prev.distance_km or 0)) < 0.01):
            dup[int(r.workout_id)] = int(prev.workout_id)
            continue  # keep comparing against the original
        prev = r
    return dup


def _rmse(pred, truth):
    return float(np.sqrt(np.mean((np.asarray(pred) - np.asarray(truth)) ** 2)))


def _knn_by_group(df: pd.DataFrame, target: str, numeric: list[str], group: str, k: int = 5) -> np.ndarray:
    """kNN imputation inside each group (e.g. activity) on z-scored attributes."""
    out = df[target].to_numpy(float).copy()
    for _, g in df.groupby(group):
        cols = [c for c in numeric if g[c].notna().any()]  # e.g. distance is empty for gym sessions
        X = g[[target] + cols].to_numpy(float)
        if np.isnan(X[:, 0]).all():
            continue
        mu, sd = np.nanmean(X, 0), np.nanstd(X, 0)
        sd = np.where(sd > 0, sd, 1)
        Z = (X - mu) / sd
        filled = P.knn_impute(Z, k)[:, 0] * sd[0] + mu[0]
        out[df.index.get_indexer(g.index)] = np.where(np.isnan(X[:, 0]), filled, X[:, 0])
    return out


def _impute_report(df: pd.DataFrame, col: str, truth: pd.Series, methods: dict) -> tuple[dict, str, np.ndarray]:
    miss = df[col].isna().to_numpy()
    ids = df.index[miss]
    rows = []
    results = {}
    for name, fn in methods.items():
        filled = fn()
        results[name] = filled
        t = truth.reindex(ids).to_numpy(float)
        ok = ~np.isnan(t)
        rows.append({"method": name, "rmse": _rmse(filled[miss][ok], t[ok]),
                     "mae": float(np.mean(np.abs(filled[miss][ok] - t[ok])))})
    best = min(rows, key=lambda r: r["rmse"])["method"]
    return {"column": col, "n_missing": int(miss.sum()), "methods": rows, "chosen": best}, best, results[best]


def run(con) -> dict:
    users = store.read("users_raw", con)
    w = store.read("workouts_raw", con)
    gt_values = store.read("gt_values", con)
    gt_w = store.read("gt_workouts", con).set_index("workout_id")
    report: dict = {"raw": {"users": len(users), "workouts": len(w)},
                    "profile": {"users": quality(users), "workouts": quality(w)}}

    # 1. activity labels
    w["activity_raw"] = w["activity"]
    w["activity"] = w["activity_raw"].map(normalise_activity)
    mapping = w.groupby(["activity_raw", "activity"]).size().reset_index(name="count")
    report["labels"] = {"mapping": mapping.sort_values(["activity", "count"], ascending=[True, False])
                        .to_dict("records"),
                        "variants": int(mapping.activity_raw.nunique()), "canonical": int(mapping.activity.nunique()),
                        "unmapped": int(w.activity.isna().sum())}

    # 2. units
    mi = w.distance_unit == "mi"
    w["distance_km"] = np.where(mi, w.distance * 1.609344, w.distance)
    lb = users.weight_unit == "lb"
    users["weight_kg"] = np.where(lb, users.weight / 2.20462, users.weight)
    report["units"] = {"distance_mi_to_km": int(mi.sum()), "weight_lb_to_kg": int(lb.sum())}

    # 3. duplicates
    w["start_time"] = pd.to_datetime(w["start_time"])
    dups = find_resync_duplicates(w)
    truth = set(gt_w.index[gt_w.duplicate_of.notna()])
    found = set(dups)
    tp = len(found & truth)
    report["duplicates"] = {"found": len(found), "true": len(truth), "true_positive": tp,
                            "precision": tp / len(found) if found else 1.0,
                            "recall": tp / len(truth) if truth else 1.0,
                            "examples": [{"duplicate": d, "kept": k} for d, k in list(dups.items())[:5]]}
    w = w[~w.workout_id.isin(found)].reset_index(drop=True)

    # 4. session types from titles
    w["session_type"] = [session_from_title(t, a) for t, a in zip(w.title, w.activity)]
    acc = float((w.session_type.to_numpy() == gt_w.session_type.reindex(w.workout_id).to_numpy()).mean())
    report["sessions"] = {"accuracy": acc, "rules": [{"pattern": p, "session": s} for p, s in TITLE_RULES],
                          "counts": w.session_type.value_counts().to_dict()}

    # 5. missing values
    w = w.set_index("workout_id", drop=False)
    gv = gt_values.set_index(["table", "column", "row_id"]).true_value.sort_index()
    t_hr = gv.xs(("workouts", "avg_hr"))
    t_cal = gv.xs(("workouts", "calories"))
    t_wt = gv.xs(("users", "weight_kg"))
    imput = []
    w_hr = w.avg_hr.to_numpy(float)
    rep, best, filled = _impute_report(w, "avg_hr", t_hr, {
        "mean": lambda: P.impute_mean(w_hr),
        "median": lambda: P.impute_median(w_hr),
        "class mean (activity)": lambda: P.impute_group_mean(w_hr, w.activity),
        "kNN k=5 (within activity)": lambda: _knn_by_group(w, "avg_hr", ["max_hr", "duration_min", "distance_km"],
                                                           "activity"),
    })
    imput.append(rep)
    w["avg_hr_imputed"] = w.avg_hr.isna()
    w["avg_hr"] = np.round(filled, 1)

    users = users.set_index("user_id", drop=False)
    wt = users.weight_kg.to_numpy(float)
    users["gender_m"] = (users.gender == "M").astype(float)
    rep, best, filled = _impute_report(users, "weight_kg", t_wt, {
        "mean": lambda: P.impute_mean(wt),
        "median": lambda: P.impute_median(wt),
        "class mean (gender)": lambda: P.impute_group_mean(wt, users.gender),
        "kNN k=5": lambda: _knn_by_group(users.assign(all=1), "weight_kg",
                                         ["height_cm", "gender_m", "vo2max", "resting_hr"], "all"),
    })
    imput.append(rep)
    users["weight_imputed"] = users.weight_kg.isna()
    users["weight_kg"] = np.round(filled, 1)
    users["bmi"] = (users.weight_kg / (users.height_cm / 100) ** 2).round(1)

    w["speed_kmh"] = w.distance_km / (w.duration_min / 60)
    kg = users.weight_kg.reindex(w.user_id).to_numpy()
    met = np.where(w.activity == "Run", w.speed_kmh, w.activity.map(C.MET).fillna(5.0))
    met_formula = met * kg * w.duration_min.to_numpy() / 60
    cal = w.calories.to_numpy(float)
    w["kg"] = kg
    rep, best, filled = _impute_report(w, "calories", t_cal, {
        "mean": lambda: P.impute_mean(cal),
        "median": lambda: P.impute_median(cal),
        "class mean (activity)": lambda: P.impute_group_mean(cal, w.activity),
        "MET formula (domain)": lambda: np.where(np.isnan(cal), met_formula, cal),
        "kNN k=5 (within activity)": lambda: _knn_by_group(w, "calories", ["duration_min", "distance_km", "kg",
                                                                           "avg_hr"], "activity"),
    })
    imput.append(rep)
    w["calories_imputed"] = w.calories.isna()
    w["calories"] = np.round(filled, 1)
    report["imputation"] = imput

    # clean tables
    w["pace_min_km"] = np.where(w.activity.isin(["Run", "Walk"]) & (w.distance_km > 0),
                                w.duration_min / w.distance_km, np.nan)
    w["has_gps"] = w.activity.isin(list(C.GPS_ACTIVITIES))
    w["source"] = "import"
    clean_w = w[["workout_id", "user_id", "activity", "session_type", "title", "start_time", "duration_min",
                 "distance_km", "avg_hr", "max_hr", "calories", "speed_kmh", "pace_min_km", "has_gps",
                 "avg_hr_imputed", "calories_imputed", "source"]].reset_index(drop=True)
    clean_w["start_time"] = clean_w.start_time.dt.strftime("%Y-%m-%d %H:%M:%S")
    clean_u = users[["user_id", "name", "gender", "age", "height_cm", "weight_kg", "bmi", "device", "resting_hr",
                     "vo2max", "assessed_level", "home_zone", "signup_date", "weight_imputed"]].reset_index(drop=True)
    clean_u["age_group"] = clean_u.age.map(age_group)
    store.write(clean_w, "workouts", con)
    store.write(clean_u, "users", con)
    report["clean"] = {"users": len(clean_u), "workouts": len(clean_w)}

    report.update(_transformations(clean_u, clean_w.assign(start_time=pd.to_datetime(clean_w.start_time)), con))
    return report


def _transformations(users: pd.DataFrame, w: pd.DataFrame, con) -> dict:
    out: dict = {}
    # Smoothing: textbook equal-depth bins on a small sorted sample, and a noisy HR stream.
    sample = np.sort(w[w.activity == "Run"].calories.dropna().sample(12, random_state=3).round(0).to_numpy())
    bins, means = P.smooth_by_bins(sample, 3, "means")
    _, medians = P.smooth_by_bins(sample, 3, "medians")
    _, bounds = P.smooth_by_bins(sample, 3, "boundaries")
    run_id = int(w[(w.activity == "Run") & (w.session_type == "IntervalRun")].workout_id.iloc[0])
    hr = store.load_stream(con, run_id)["hr"]
    out["smoothing"] = {"sample": sample.tolist(), "bins": bins, "by_means": means, "by_medians": medians,
                        "by_boundaries": bounds, "stream_workout": run_id, "hr_raw": hr.tolist(),
                        "hr_moving_median": P.moving_median(hr, 5).tolist()}

    # Normalisation of calories
    cal = w.calories.to_numpy(float)
    ds, j = P.decimal_scaling(cal)
    variants = {"raw": cal, "min-max [0,1]": P.min_max(cal), "z-score": P.z_score(cal), f"decimal scaling (j={j})": ds}
    out["normalisation"] = {"attribute": "calories", "variants": [
        {"name": k, "min": float(np.nanmin(v)), "max": float(np.nanmax(v)), "mean": float(np.nanmean(v)),
         "std": float(np.nanstd(v)), "hist": histogram(v, 24)} for k, v in variants.items()]}

    # Discretisation of age, judged by class entropy against assessed level
    lab = users.dropna(subset=["assessed_level"])
    age, lvl = lab.age.to_numpy(float), lab.assessed_level.to_numpy()

    def partition(edges):
        b = P.assign_bins(age, edges)
        ent = sum((b == i).sum() / len(b) * P.entropy(lvl[b == i]) for i in np.unique(b))
        return {"edges": [round(float(e), 2) for e in edges], "counts": np.bincount(b, minlength=len(edges) - 1)
                .tolist(), "class_entropy": float(ent)}
    cuts = P.entropy_discretize(age, lvl, max_bins=5)
    out["discretisation"] = {"attribute": "age", "class": "assessed_level", "base_entropy": P.entropy(lvl),
                             "methods": {"equal-width (5)": partition(P.equal_width_edges(age, 5)),
                                         "equal-frequency (5)": partition(P.equal_depth_edges(age, 5)),
                                         "entropy-based (MDL)": partition(np.r_[age.min(), cuts, age.max()])}}

    # Correlation and chi-square on user-level features
    feats = user_features(users, w)
    cols = ["age", "bmi", "resting_hr", "vo2max", "sessions_per_week", "minutes_per_week", "avg_intensity",
            "run_pace", "longest_km", "share_run", "share_strength", "share_hiit", "share_yoga", "share_walk"]
    R = P.correlation_matrix(feats[cols].to_numpy(float))
    fav = feats[ACTIVITY_SHARES].to_numpy().argmax(1)
    fav_names = np.array([c.replace("share_", "").title() for c in ACTIVITY_SHARES])[fav]
    tab1 = pd.crosstab(feats.gender, fav_names)
    tab2 = pd.crosstab(users.set_index("user_id").age_group.reindex(feats.user_id).to_numpy(),
                       users.set_index("user_id").assessed_level.reindex(feats.user_id).fillna("Unassessed").to_numpy())
    tab2 = tab2.drop(columns="Unassessed", errors="ignore")
    chi = []
    for name, t in (("gender x favourite activity", tab1), ("age group x assessed level", tab2)):
        r = P.chi_square(t.to_numpy())
        chi.append({"test": name, "rows": t.index.tolist(), "cols": t.columns.tolist(), "observed": t.to_numpy()
                    .tolist(), **r})
    out["correlation"] = {"columns": cols, "matrix": R.round(4).tolist(), "chi_square": chi}

    # PCA on standardised user features
    pca_cols = [c for c in cols if c != "run_pace"] + ["share_cycle", "share_swim"]
    Z = P.Standardizer().fit_transform(feats[pca_cols].fillna(feats[pca_cols].median()).to_numpy(float))
    pca = PCA().fit(Z)
    proj = pca.transform(Z)[:, :2]
    levels = users.set_index("user_id").assessed_level.reindex(feats.user_id).fillna("Unassessed").to_numpy()
    out["pca"] = {"columns": pca_cols, "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
                  "loadings": pca.components_[:2].round(4).tolist(),
                  "points": [{"x": float(a), "y": float(b), "level": str(lv), "user_id": int(u)}
                             for (a, b), lv, u in zip(proj, levels, feats.user_id)]}

    # Sampling (numerosity reduction): SRSWOR vs stratified by activity
    rng = np.random.default_rng(7)
    pop = w.activity.value_counts(normalize=True)
    srs = w.iloc[rng.choice(len(w), int(0.05 * len(w)), replace=False)].activity.value_counts(normalize=True)
    strat = w.groupby("activity").sample(frac=0.05, random_state=7).activity.value_counts(normalize=True)
    out["sampling"] = {"fraction": 0.05, "rows": [
        {"activity": a, "population": float(pop[a]), "srswor": float(srs.get(a, 0)), "stratified": float(strat.get(a, 0))}
        for a in pop.index],
        "max_abs_dev": {"srswor": float((srs.reindex(pop.index).fillna(0) - pop).abs().max()),
                        "stratified": float((strat.reindex(pop.index).fillna(0) - pop).abs().max())}}
    return out
