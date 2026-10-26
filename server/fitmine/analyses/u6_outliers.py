"""U6 Outlier detection: faulty sensors, spoofed GPS, and fake profiles.

Workout level, per activity (contextual outliers: a 25 km/h "run" is odd, a
25 km/h ride is not). Features come from each HR/GPS stream. Detectors:
  zscore / iqr    univariate statistical tests on every feature
  lof             Local Outlier Factor on the standardised feature vector
  iforest         Isolation Forest on the same vectors
  rules           physiological and physical limits (domain knowledge)
  duplicates      identical stream fingerprints across different users
  ensemble        rules or duplicates, or at least two of {statistical, lof, iforest}

User level: rules, a regression-residual consistency check, LOF / iForest on
profile + behaviour, and shared-workout fingerprints for cloned accounts.
"""
from __future__ import annotations

import hashlib
import time

import numpy as np
import pandas as pd

from .. import config as C
from ..algorithms import outliers as O
from ..algorithms import preprocess as P
from ..algorithms.iforest import IsolationForest
from ..algorithms.lof import fit_reference
from ..algorithms.trajectory import speed_profile, xy
from ..data import store
from .common import expected_calories, hrmax_pred, user_features

DT = C.STREAM_INTERVAL_S
FEATURES = ["hr_max", "hr_mean", "hr_std", "hr_jump", "hr_zero_frac", "hr_flat_frac", "hr_over_pred",
            "calorie_ratio", "speed_avg", "speed_p95", "step_max_m", "speed_cv", "hr_per_speed"]
GPS_FEATURES = ["speed_avg", "speed_p95", "step_max_m", "speed_cv", "hr_per_speed"]
FAULTS = ["hr_spike", "hr_flatline", "hr_dropout", "gps_teleport", "car_speed", "gps_replay", "calorie_mismatch",
          "copied_workout"]
SPOOFS = ["age_falsified", "impossible_body", "vo2_inflated", "duplicate_account"]
METHODS = ["zscore", "iqr", "lof", "iforest", "rules", "duplicates", "ensemble"]

# Domain limits
MAX_SPEED_KMH = {"Run": 25, "Walk": 9, "Cycle": 60}
TELEPORT_STEP_M = 500  # metres in one 15 s sample = 120 km/h


def _longest_run(a: np.ndarray) -> int:
    if len(a) == 0:
        return 0
    change = np.flatnonzero(np.diff(a) != 0)
    edges = np.r_[-1, change, len(a) - 1]
    return int(np.diff(edges).max())


def stream_features(stream: dict, age: float, activity: str, calories: float, weight: float,
                    duration_min: float) -> dict:
    hr = stream["hr"]
    pos = hr[hr > 0]
    f = {
        "hr_max": float(hr.max()), "hr_mean": float(pos.mean()) if len(pos) else 0.0,
        "hr_std": float(pos.std()) if len(pos) else 0.0,
        "hr_jump": float(np.abs(np.diff(hr)).max()) if len(hr) > 1 else 0.0,
        "hr_zero_frac": float((hr == 0).mean()),
        "hr_flat_frac": _longest_run(hr) / len(hr),
        "hr_over_pred": float(hr.max() - hrmax_pred(age)),
    }
    speed_kmh = None
    if stream["lat"] is not None:
        P_ = xy(stream["lat"], stream["lon"])
        v = speed_profile(P_, DT) * 3.6
        steps = np.hypot(*np.diff(P_, axis=0).T)
        moving = v[v > 1]
        speed_kmh = float(steps.sum() / 1000 / (duration_min / 60))
        f.update(speed_avg=float(np.median(v)), speed_p95=float(np.percentile(v, 95)),
                 step_max_m=float(steps.max()), speed_cv=float(moving.std() / moving.mean()) if len(moving) else 0.0,
                 hr_per_speed=float((f["hr_mean"]) / max(np.median(v), 0.5)))
    else:
        f.update({k: np.nan for k in GPS_FEATURES})
    exp = expected_calories(activity, weight, duration_min, speed_kmh)
    f["calorie_ratio"] = float(calories / exp) if exp > 0 else np.nan
    return f


def fingerprint(stream: dict) -> str:
    h = hashlib.blake2b(digest_size=12)
    h.update(np.asarray(stream["hr"], np.int16).tobytes())
    if stream["lat"] is not None:
        h.update(np.round(np.asarray(stream["lat"]) * 1e5).astype(np.int64).tobytes())
    return h.hexdigest()


def build_features(con) -> pd.DataFrame:
    users = store.read("users", con).set_index("user_id")
    w = store.read("workouts", con)
    streams = store.load_streams(con, w.workout_id)
    rows = []
    for r in w.itertuples():
        s = streams.get(r.workout_id)
        if s is None:
            continue
        u = users.loc[r.user_id]
        f = stream_features(s, u.age, r.activity, r.calories, u.weight_kg, r.duration_min)
        rows.append({"workout_id": r.workout_id, "user_id": r.user_id, "activity": r.activity,
                     "start_time": r.start_time, "signup_date": u.signup_date, "fingerprint": fingerprint(s), **f})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- detectors

def rule_reasons(row) -> list[str]:
    out = []
    if row.hr_max >= 220 or row.hr_over_pred > 30 or row.hr_jump > 60:
        out.append("hr_spike")
    if row.hr_flat_frac > 0.4:
        out.append("hr_flatline")
    if row.hr_zero_frac > 0.05:
        out.append("hr_dropout")
    if not np.isnan(row.step_max_m) and row.step_max_m > TELEPORT_STEP_M:
        out.append("gps_teleport")
    if not np.isnan(row.speed_avg) and row.speed_avg > MAX_SPEED_KMH.get(row.activity, 99):
        out.append("car_speed")
    if not np.isnan(row.calorie_ratio) and (row.calorie_ratio > 2.0 or row.calorie_ratio < 0.4):
        out.append("calorie_mismatch")
    return out


def duplicate_flags(F: pd.DataFrame) -> pd.Series:
    """Workouts whose stream fingerprint already exists under a different user. The first
    upload (earliest start, then oldest account) is the original; later copies are flagged."""
    users_per_fp = F.groupby("fingerprint").user_id.nunique()
    shared = F[F.fingerprint.isin(set(users_per_fp[users_per_fp > 1].index))]
    first = shared.sort_values(["start_time", "signup_date", "workout_id"]).groupby("fingerprint").head(1).index
    return pd.Series(F.index.isin(shared.index.difference(first)), index=F.index)


def _activity_matrix(F: pd.DataFrame, activity: str):
    g = F[F.activity == activity]
    cols = [c for c in FEATURES if g[c].notna().any()]
    X = g[cols].to_numpy(float)
    X = np.where(np.isnan(X), np.nanmedian(X, 0), X)
    return g.index, cols, X


def detect(F: pd.DataFrame, method: str, params: dict | None = None) -> tuple[np.ndarray, np.ndarray, list]:
    """Returns (flag, score, reasons) aligned with F's rows."""
    p = params or {}
    n = len(F)
    flag, score = np.zeros(n, bool), np.zeros(n)
    reasons: list = [[] for _ in range(n)]
    pos = {ix: i for i, ix in enumerate(F.index)}
    if method in ("zscore", "iqr"):
        for act in F.activity.unique():
            idx, cols, X = _activity_matrix(F, act)
            for j, c in enumerate(cols):
                if method == "zscore":
                    s = O.zscore_scores(X[:, j])
                    hit = s > float(p.get("z", 4.0))
                else:
                    lo, hi = O.iqr_fences(X[:, j], float(p.get("iqr_k", 3.0)))
                    s = np.maximum((lo - X[:, j]), (X[:, j] - hi)) / max(hi - lo, 1e-9)
                    hit = (X[:, j] < lo) | (X[:, j] > hi)
                for ix, h, sc in zip(idx, hit, s):
                    i = pos[ix]
                    score[i] = max(score[i], sc)
                    if h:
                        flag[i] = True
                        reasons[i].append(c)
    elif method in ("lof", "iforest"):
        contamination = float(p.get("contamination", 0.03))
        for act in F.activity.unique():
            idx, cols, X = _activity_matrix(F, act)
            Z = P.Standardizer().fit_transform(X)
            if method == "lof":
                s = fit_reference(Z, int(p.get("lof_k", 20)))["scores"]
            else:
                s = IsolationForest(int(p.get("n_trees", 100)), 256, seed=0).fit(Z).score(Z)
            thr = np.quantile(s, 1 - contamination)
            for ix, sc in zip(idx, s):
                i = pos[ix]
                score[i] = sc
                if sc > thr:
                    flag[i] = True
                    reasons[i].append(f"{method} score {sc:.2f}")
    elif method == "rules":
        for i, row in enumerate(F.itertuples()):
            reasons[i] = rule_reasons(row)
            flag[i] = bool(reasons[i])
            score[i] = len(reasons[i])
    elif method == "duplicates":
        flag = duplicate_flags(F).to_numpy()
        score = flag.astype(float)
        reasons = [["shared stream fingerprint"] if f else [] for f in flag]
    elif method == "ensemble":
        r_f, _, r_r = detect(F, "rules")
        d_f, _, _ = detect(F, "duplicates")
        votes = np.zeros(n)
        for m in ("iqr", "lof", "iforest"):
            votes += detect(F, m, p)[0]
        flag = r_f | d_f | (votes >= 2)
        score = r_f * 2 + d_f * 2 + votes
        reasons = [rr + (["shared stream fingerprint"] if d else []) + ([f"{int(v)} of 3 statistical detectors"]
                                                                     if v >= 2 else [])
                   for rr, d, v in zip(r_r, d_f, votes)]
    else:
        raise ValueError(method)
    return flag, score, reasons


def evaluate(F: pd.DataFrame, flag: np.ndarray, truth: pd.Series) -> dict:
    t = truth.reindex(F.workout_id).to_numpy()
    is_fault = pd.notna(t)
    tp = int((flag & is_fault).sum())
    fp = int((flag & ~is_fault).sum())
    fn = int((~flag & is_fault).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    per = {}
    for ft in FAULTS:
        m = t == ft
        if m.any():
            per[ft] = {"n": int(m.sum()), "detected": int((flag & m).sum()), "recall": float((flag & m).mean() / m.mean())}
    return {"flagged": int(flag.sum()), "tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec,
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0, "per_type": per}


# ----------------------------------------------------------------------------- user level

def user_level(con, F: pd.DataFrame, workout_flag: np.ndarray) -> tuple[pd.DataFrame, dict]:
    users = store.read("users", con)
    w = store.read("workouts", con)
    U = user_features(users, w).set_index("user_id")
    U["signup_date"] = users.set_index("user_id").signup_date.reindex(U.index)
    # Observed peak HR from workouts that passed the sensor checks (a spiking strap says nothing about age).
    clean = F[~workout_flag]
    U["max_hr_p95"] = clean.groupby("user_id").hr_max.quantile(0.95).reindex(U.index)
    reasons = {uid: [] for uid in U.index}
    # 1. hard limits
    for uid, r in U.iterrows():
        if r.bmi < 13 or r.bmi > 60:
            reasons[uid].append(f"BMI {r.bmi:.1f} outside human range")
        if r.vo2max > 85 or r.resting_hr < 32:
            reasons[uid].append(f"VO2max {r.vo2max:.0f} / resting HR {r.resting_hr:.0f} beyond physiological limits")
        if r.max_hr_p95 > hrmax_pred(r.age) + 12:
            reasons[uid].append(f"observed peak HR {r.max_hr_p95:.0f} exceeds age-predicted max "
                                f"{float(hrmax_pred(r.age)):.0f} for claimed age {r.age:.0f}")
    # 2. consistency model: regress VO2max on behaviour; large residual = claimed fitness doesn't match activity
    cols = ["age", "resting_hr", "sessions_per_week", "minutes_per_week", "avg_intensity", "share_run", "share_walk"]
    X = U[cols].fillna(U[cols].median()).to_numpy(float)
    A = np.c_[np.ones(len(X)), X]
    coef, *_ = np.linalg.lstsq(A, U.vo2max.to_numpy(float), rcond=None)
    resid = U.vo2max.to_numpy(float) - A @ coef
    rz = O.robust_z_scores(resid)
    for uid, z, res in zip(U.index, rz, resid):
        if res > 0 and z > 4.5:
            reasons[uid].append(f"VO2max {res:+.1f} above what their training predicts (robust z {z:.1f})")
    # Second consistency model: predict age from physiology; a claimed age far above it is suspicious.
    acols = ["vo2max", "resting_hr", "max_hr_p95", "avg_intensity", "sessions_per_week", "bmi"]
    Xa = U[acols].fillna(U[acols].median()).to_numpy(float)
    Aa = np.c_[np.ones(len(Xa)), Xa]
    ca, *_ = np.linalg.lstsq(Aa, U.age.to_numpy(float), rcond=None)
    age_hat = Aa @ ca
    age_res = U.age.to_numpy(float) - age_hat
    az = O.robust_z_scores(age_res)
    for uid, z, res, ah in zip(U.index, az, age_res, age_hat):
        if res > 0 and z > 3.5:
            reasons[uid].append(f"claimed age {U.age[uid]:.0f} but physiology suggests about {ah:.0f} "
                                f"(robust z {z:.1f})")
    # 3. cloned accounts: most of their workouts already exist under an older account
    fp_users = F.groupby("fingerprint").user_id.apply(set)
    shared = F[F.fingerprint.map(fp_users.apply(len)) > 1]
    signup = U.signup_date
    for uid, g in shared.groupby("user_id"):
        older = [{o for o in fp_users[fp] if o != uid and signup.get(o, "9999") < signup.get(uid, "0000")}
                 for fp in g.fingerprint]
        copied = sum(1 for s in older if s)
        total = int((F.user_id == uid).sum())
        if copied / total > 0.5:
            top = pd.Series([o for s in older for o in s]).value_counts().index[0]
            reasons[uid].append(f"{copied}/{total} workouts identical to older account {top}")
    # 4. multivariate scores for context
    Z = P.Standardizer().fit_transform(np.c_[X, U[["bmi", "vo2max", "max_hr_p95"]].fillna(0).to_numpy(float)])
    lof_s = fit_reference(Z, 20)["scores"]
    if_s = IsolationForest(200, 256, seed=1).fit(Z).score(Z)
    out = pd.DataFrame({"user_id": U.index, "lof": lof_s, "iforest": if_s,
                        "reasons": [reasons[u] for u in U.index]})
    out["flagged"] = out.reasons.apply(bool)
    gt = store.read("gt_users", con).set_index("user_id").spoof_type
    t = gt.reindex(out.user_id).to_numpy()
    is_spoof = pd.notna(t)
    ev = {}
    for name, flag in (("rules + consistency + clones", out.flagged.to_numpy()),
                       ("LOF top 3%", lof_s > np.quantile(lof_s, 0.97)),
                       ("iForest top 3%", if_s > np.quantile(if_s, 0.97))):
        tp = int((flag & is_spoof).sum())
        prec = tp / flag.sum() if flag.sum() else 0.0
        rec = tp / is_spoof.sum()
        ev[name] = {"flagged": int(flag.sum()), "tp": tp, "precision": float(prec), "recall": float(rec),
                    "per_type": {s: {"n": int((t == s).sum()), "detected": int((flag & (t == s)).sum())} for s in SPOOFS}}
    return out, ev


# ----------------------------------------------------------------------------- report

def examples(F: pd.DataFrame, flag: np.ndarray, reasons: list, truth: pd.Series, con) -> list[dict]:
    """One detected workout per fault type, with its stream for plotting."""
    out = []
    t = truth.reindex(F.workout_id)
    for ft in FAULTS:
        cand = F[(t.to_numpy() == ft) & flag]
        if cand.empty:
            continue
        r = cand.iloc[0]
        s = store.load_stream(con, int(r.workout_id))
        i = F.index.get_loc(cand.index[0])
        out.append({"fault": ft, "workout_id": int(r.workout_id), "activity": r.activity, "reasons": reasons[i],
                    "hr": s["hr"].tolist(),
                    "lat": None if s["lat"] is None else np.round(s["lat"], 6).tolist(),
                    "lon": None if s["lon"] is None else np.round(s["lon"], 6).tolist()})
    return out


def run_method(F, truth, method, params=None) -> tuple[dict, np.ndarray, list]:
    t = time.perf_counter()
    flag, score, reasons = detect(F, method, params)
    ev = evaluate(F, flag, truth)
    ev["ms"] = round((time.perf_counter() - t) * 1000, 1)
    ev["method"] = method
    ev["params"] = params or {}
    ev["score_hist"] = np.histogram(score, bins=30)[0].tolist()
    ev["top"] = [{"workout_id": int(F.workout_id.iat[i]), "activity": F.activity.iat[i], "score": float(score[i]),
                  "reasons": reasons[i], "truth": truth.get(int(F.workout_id.iat[i]))}
                 for i in np.argsort(-score)[:40]]
    return ev, flag, reasons


def run(con) -> tuple[dict, pd.DataFrame, pd.DataFrame, dict]:
    F = build_features(con)
    store.write(F, "workout_features", con)
    truth = store.read("gt_workouts", con).set_index("workout_id").fault_type.dropna()
    methods = {}
    for m in METHODS:
        methods[m], flag, reasons = run_method(F, truth, m)
    ens_flag, ens_score, ens_reasons = detect(F, "ensemble")
    flags = pd.DataFrame({"workout_id": F.workout_id, "flagged": ens_flag, "score": ens_score,
                          "reasons": [", ".join(r) for r in ens_reasons]})
    store.write(flags, "workout_flags", con)
    users_out, user_eval = user_level(con, F, ens_flag)

    # Reference statistics so new uploads can be scored the same way (models_runtime).
    ref = {}
    for act in F.activity.unique():
        idx, cols, X = _activity_matrix(F, act)
        sc = P.Standardizer().fit(X)
        Z = sc.transform(X)
        forest = IsolationForest(100, 256, seed=0).fit(Z)
        lof_ref = fit_reference(Z, 20)
        ref[act] = {"cols": cols, "scaler": sc, "medians": np.nanmedian(X, 0), "iforest": forest,
                    "if_thr": float(np.quantile(forest.score(Z), 0.97)), "lof": lof_ref,
                    "lof_thr": float(np.quantile(lof_ref["scores"], 0.97)),
                    "fences": [O.iqr_fences(X[:, j], 3.0) for j in range(X.shape[1])]}
    model = {"ref": ref, "fingerprints": dict(zip(F.fingerprint, F.user_id))}

    report = {
        "n_workouts": int(len(F)), "features": FEATURES,
        "n_true_faults": int(F.workout_id.isin(truth.index).sum()),
        "fault_counts": truth.reindex(F.workout_id).value_counts().to_dict(),
        "methods": methods,
        "comparison": [{"method": m, **{k: methods[m][k] for k in ("flagged", "precision", "recall", "f1", "ms")}}
                       for m in METHODS],
        "recall_matrix": {m: {ft: methods[m]["per_type"].get(ft, {}).get("recall", 0.0) for ft in FAULTS}
                          for m in METHODS},
        "examples": examples(F, ens_flag, ens_reasons, truth, con),
        "users": {"evaluation": user_eval,
                  "flagged": [{"user_id": int(r.user_id), "reasons": r.reasons, "lof": float(r.lof),
                               "iforest": float(r.iforest)} for r in users_out[users_out.flagged].itertuples()],
                  "scatter": [{"user_id": int(r.user_id), "lof": float(r.lof), "iforest": float(r.iforest),
                               "flagged": bool(r.flagged)} for r in users_out.itertuples()]},
    }
    return report, flags, users_out, model
