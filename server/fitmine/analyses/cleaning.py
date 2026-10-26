"""Data cleaning: profile the raw app data, clean it, write the clean tables.

Steps, each scored against the planted ground truth where possible:
  1. activity label normalisation (synonyms, case)          -> mapping table
  2. unit harmonisation (lb -> kg, mi -> km)
  3. re-sync duplicate removal                              -> precision / recall
  4. session type from free-text titles                     -> accuracy
  5. missing values filled by kNN imputation (k = 5, within the same activity);
     its error against the hidden true values is reported next to mean imputation
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .. import config as C
from ..algorithms import preprocess as P
from ..data import store

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


def _impute(df: pd.DataFrame, col: str, truth: pd.Series, knn) -> tuple[dict, np.ndarray]:
    """Fill col with kNN imputation; report its error on the hidden true values next to
    the mean-imputation baseline."""
    miss = df[col].isna().to_numpy()
    t = truth.reindex(df.index[miss]).to_numpy(float)
    ok = ~np.isnan(t)
    filled = knn()
    baseline = P.impute_mean(df[col].to_numpy(float))
    rows = [{"method": name, "rmse": _rmse(v[miss][ok], t[ok]), "mae": float(np.mean(np.abs(v[miss][ok] - t[ok])))}
            for name, v in (("kNN k=5", filled), ("mean (baseline)", baseline))]
    return {"column": col, "n_missing": int(miss.sum()), "methods": rows, "chosen": "kNN k=5"}, filled


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
    rep, filled = _impute(w, "avg_hr", t_hr,
                          lambda: _knn_by_group(w, "avg_hr", ["max_hr", "duration_min", "distance_km"], "activity"))
    imput.append(rep)
    w["avg_hr_imputed"] = w.avg_hr.isna()
    w["avg_hr"] = np.round(filled, 1)

    users = users.set_index("user_id", drop=False)
    users["gender_m"] = (users.gender == "M").astype(float)
    rep, filled = _impute(users, "weight_kg", t_wt,
                          lambda: _knn_by_group(users.assign(all=1), "weight_kg",
                                                ["height_cm", "gender_m", "vo2max", "resting_hr"], "all"))
    imput.append(rep)
    users["weight_imputed"] = users.weight_kg.isna()
    users["weight_kg"] = np.round(filled, 1)
    users["bmi"] = (users.weight_kg / (users.height_cm / 100) ** 2).round(1)

    w["speed_kmh"] = w.distance_km / (w.duration_min / 60)
    w["kg"] = users.weight_kg.reindex(w.user_id).to_numpy()
    rep, filled = _impute(w, "calories", t_cal,
                          lambda: _knn_by_group(w, "calories", ["duration_min", "distance_km", "kg", "avg_hr"],
                                                "activity"))
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
    return report
