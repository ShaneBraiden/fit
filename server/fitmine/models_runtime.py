"""Apply the mined models to live data: score an uploaded workout, refresh a
user's level and persona, recommend exercises from the association rules."""
from __future__ import annotations

import threading
from datetime import datetime

import numpy as np
import pandas as pd

from . import config as C
from .algorithms import trajectory as T
from .algorithms.lof import lof_novelty
from .analyses import u6_outliers as U6
from .analyses import u7_sequences_trajectories as U7
from .analyses.common import load_pickle, user_features
from .data import generator as G
from .data import store

_lock = threading.Lock()
_models = None


def models() -> dict:
    global _models
    with _lock:
        if _models is None:
            _models = load_pickle("models")
        return _models


def reload():
    global _models
    with _lock:
        _models = None


# ----------------------------------------------------------------------------- scoring one workout

def score_workout(user: pd.Series, activity: str, calories: float, duration_min: float, stream: dict,
                  start_time: str, user_id: int) -> dict:
    """Run the U6 detectors on a single new workout, using the reference statistics of its activity."""
    m = models()["outliers"]
    f = U6.stream_features(stream, user.age, activity, calories, user.weight_kg, duration_min)
    row = pd.Series({**f, "activity": activity})
    reasons = U6.rule_reasons(row)
    fp = U6.fingerprint(stream)
    owner = m["fingerprints"].get(fp)
    if owner is not None and owner != user_id:
        reasons.append("duplicate_of_other_user")
    ref = m["ref"].get(activity)
    detectors = {"rules": bool(U6.rule_reasons(row)), "duplicates": owner is not None and owner != user_id}
    scores = {}
    if ref:
        x = np.array([f.get(c, np.nan) for c in ref["cols"]], float)
        x = np.where(np.isnan(x), ref["medians"], x)
        z = ref["scaler"].transform(x[None])
        scores["iforest"] = float(ref["iforest"].score(z)[0])
        L = ref["lof"]
        scores["lof"] = float(lof_novelty(L["X"], L["lrd"], L["k_dist"], z, L["k"])[0])
        out_of_fence = [c for c, v, (lo, hi) in zip(ref["cols"], x, ref["fences"]) if v < lo or v > hi]
        detectors["iqr"] = bool(out_of_fence)
        detectors["iforest"] = scores["iforest"] > ref["if_thr"]
        detectors["lof"] = scores["lof"] > ref["lof_thr"]
        votes = detectors["iqr"] + detectors["iforest"] + detectors["lof"]
        if votes >= 2 and not reasons:
            reasons.append(f"unusual for a {activity.lower()} ({', '.join(out_of_fence[:3]) or 'multivariate'})")
    return {"flagged": bool(reasons), "reasons": reasons, "detectors": detectors, "scores": scores,
            "features": {k: (None if isinstance(v, float) and np.isnan(v) else round(float(v), 3))
                         for k, v in f.items()}}


def match_route(stream: dict) -> dict | None:
    if stream["lat"] is None:
        return None
    r = models()["routes"]
    track = U7.resampled({0: stream}, [0])
    hit = U7.assign_routes(r, track)[0]
    return None if hit is None else {"cluster": hit[0], "name": hit[1], "hausdorff_m": round(hit[2], 1)}


def segment(stream: dict) -> dict | None:
    if stream["lat"] is None:
        return None
    r = T.segment_track(stream["lat"], stream["lon"], C.STREAM_INTERVAL_S)
    return {"kind": r["kind"], "segments": r["segments"], "change_points": r["change_points"],
            "speed_kmh": (r["speed"] * 3.6).round(2).tolist()}


# ----------------------------------------------------------------------------- per user

def user_profile(con, user_id: int) -> dict:
    """Recompute features from the user's current workouts, then classify and cluster."""
    users = store.read("users", con, "WHERE user_id=?", (int(user_id),))
    w = store.read("workouts", con, "WHERE user_id=?", (int(user_id),))
    feats = user_features(users, w)
    mm = models()
    clf = mm["classifier"]
    proba = clf.predict_proba(feats)[0]
    cm = mm["cluster"]
    x = feats[cm["features"]].fillna(pd.Series(cm["medians"])).to_numpy(float)
    z = cm["scaler"].transform(x)
    d = ((cm["centres"] - z) ** 2).sum(1)
    cluster = int(d.argmin())
    sim = ((cm["Z"] - z) ** 2).sum(1)
    order = [int(cm["user_ids"][i]) for i in np.argsort(sim) if int(cm["user_ids"][i]) != int(user_id)][:5]
    f = feats.iloc[0]
    return {
        "level_proba": {str(c): float(p) for c, p in zip(clf.classes_, proba)},
        "predicted_level": str(clf.classes_[proba.argmax()]),
        "cluster": cluster, "persona": cm["names"][cluster],
        "persona_distance": {cm["names"][i]: float(np.sqrt(v)) for i, v in enumerate(d)},
        "similar": order,
        "features": {k: (None if pd.isna(v) else (float(v) if not isinstance(v, str) else v)) for k, v in f.items()},
    }


def recommendations(con, user_id: int, recent: int = 6, top: int = 6) -> list[dict]:
    """For each of the user's latest workouts: rules whose antecedent was done in that session
    and whose consequent was not, i.e. "next time you do X, people usually add Y"."""
    w = store.read("workouts", con, "WHERE user_id=? ORDER BY start_time DESC LIMIT ?", (int(user_id), recent))
    if w.empty:
        return []
    ids = ",".join(str(int(i)) for i in w.workout_id)
    ex = store.read("exercises", con, f"WHERE workout_id IN ({ids})")
    baskets = ex.groupby("workout_id").exercise.apply(set)
    rules = [r for r in models()["session_rules"] if len(r["consequent"]) == 1]
    best: dict[str, dict] = {}
    for wid in w.workout_id:
        done = baskets.get(wid, set())
        for r in rules:
            item = r["consequent"][0]
            if item in done or not set(r["antecedent"]) <= done:
                continue
            score = r["confidence"] * r["lift"]
            if item not in best or score > best[item]["_score"]:
                best[item] = {"exercise": item, "because": sorted(r["antecedent"]), "confidence": r["confidence"],
                              "lift": r["lift"], "support": r["support"], "_score": score}
    out = sorted(best.values(), key=lambda r: -r["_score"])[:top]
    for r in out:
        r.pop("_score")
    return out


# ----------------------------------------------------------------------------- simulated uploads

SIM_SESSION = {"Run": {"easy": "EasyRun", "intervals": "IntervalRun", "tempo": "TempoRun", "long": "LongRun"},
               "Walk": {"easy": "Walk"}, "Cycle": {"easy": "Cycle"}}


def simulate_stream(con, user_id: int, activity: str, kind: str = "easy", route: str = "popular",
                    faults: list[str] | None = None, seed: int | None = None) -> dict:
    """Synthesize a realistic HR/GPS recording for a user, optionally with injected sensor faults,
    using the same generator that produced the dataset. Pace and fitness come from the user's
    own profile and history (not from ground truth)."""
    rng = np.random.default_rng(seed)
    uid = int(user_id)
    u = store.read("users", con, "WHERE user_id=?", (uid,)).iloc[0]
    runs = store.read("workouts", con, "WHERE user_id=? AND activity='Run'", (uid,))
    fit = float((u.vo2max - 40 + 0.2 * (u.age - 35) + (4 if u.gender == "F" else 0)) / 7)
    pace = float(runs.pace_min_km.median()) if runs.pace_min_km.notna().any() else         float(np.clip(6.6 - 0.65 * fit + 0.02 * (u.age - 35), 3.3, 9.0))
    g = G._Gen(int(rng.integers(1 << 30)), 1)
    hx, hy = G.geo.to_xy(*G.geo.ZONE_CENTERS.get(u.home_zone, (19.05, 72.85)))
    person = {"user_id": uid, "fitness": fit, "home_x": hx, "home_y": hy, "resting_hr": float(u.resting_hr),
              "hrmax": float(208 - 0.7 * u.age), "weight_kg": float(u.weight_kg), "pace": pace,
              "walk_kmh": 5.0 + 0.3 * fit, "ride_kmh": 21 + 2.5 * fit}
    stype = SIM_SESSION.get(activity, {}).get(kind) or {"Yoga": "Yoga", "HIIT": "HIIT", "Swim": "Swim"}.get(
        activity, {"pull": "Pull", "legs": "Legs"}.get(kind, "Push"))
    if activity in C.GPS_ACTIVITIES:
        if route == "personal":
            radius = 2000 if activity == "Cycle" else 600
            chosen = (100 + uid, G._personal_loop(g.rng, np.array([hx, hy]), radius), "loop")
        else:  # the popular route closest to home
            rid = int(np.argmin(np.hypot(*(g.route_centres - [hx, hy]).T)))
            chosen = (rid, *g.routes[rid])
        g._route_for = lambda _u, _a: chosen
    k = g.workout(person, stype, datetime.now())
    row, s = g.rows[k], g.streams[k]
    for f in faults or []:
        _inject(rng, f, s, person)
    if s["lat"] is not None:
        P = T.xy(s["lat"], s["lon"])
        row["distance_km"] = round(float(T.step_lengths(P).sum() / 1000), 3)
        row["duration_min"] = round(len(s["hr"]) * C.STREAM_INTERVAL_S / 60, 2)
    row["avg_hr"] = round(float(s["hr"].mean()), 1)
    row["max_hr"] = int(s["hr"].max())
    if "calorie_mismatch" in (faults or []):
        row["calories"] = round(row["calories"] * 3.2, 1)
    return {"row": row, "stream": s, "session_type": stype, "exercises": g.ex[k]}


def _inject(rng, fault: str, s: dict, person: dict):
    hr = s["hr"]
    if fault == "hr_spike":
        idx = rng.choice(len(hr), size=6, replace=False)
        hr[idx] = rng.integers(228, 255, len(idx))
    elif fault == "hr_flatline":
        i0 = len(hr) // 3
        hr[i0:] = hr[i0]
    elif fault == "hr_dropout":
        a = len(hr) // 4
        hr[a:a + len(hr) // 4] = 0
    elif fault == "gps_teleport" and s["lat"] is not None:
        x, y = G.geo.to_xy(s["lat"], s["lon"])
        i = len(x) // 2
        x[i:i + 2] += 8000
        s["lat"], s["lon"] = G.geo.to_latlon(x, y)
    elif fault == "car_speed" and s["lat"] is not None:
        x, y = G.geo.to_xy(s["lat"], s["lon"])
        P = np.column_stack([x, y])
        cum = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
        n = max(10, int(cum[-1] / (12.5 * C.STREAM_INTERVAL_S)))
        sp = np.linspace(0, cum[-1], n)
        s["lat"], s["lon"] = G.geo.to_latlon(np.interp(sp, cum, x), np.interp(sp, cum, y))
        s["hr"] = np.clip(np.round(person["resting_hr"] + 12 + rng.normal(0, 2, n)), 40, 120).astype(int)


def insert_workout(con, user_id: int, row: dict, stream: dict, exercises: list[str], session_type: str,
                   flags: dict) -> int:
    with store._lock:
        wid = int(con.execute("SELECT COALESCE(MAX(workout_id), 0) + 1 FROM workouts").fetchone()[0])
        wid = max(wid, int(con.execute("SELECT COALESCE(MAX(workout_id), 0) + 1 FROM streams").fetchone()[0]))
        dist = row.get("distance_km")
        dur = float(row["duration_min"])
        speed = dist / (dur / 60) if dist else None
        pace = dur / dist if dist and row["activity"] in ("Run", "Walk") else None
        con.execute(
            "INSERT INTO workouts (workout_id, user_id, activity, session_type, title, start_time, duration_min, "
            "distance_km, avg_hr, max_hr, calories, speed_kmh, pace_min_km, has_gps, avg_hr_imputed, "
            "calories_imputed, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wid, int(user_id), row["activity"], session_type, row.get("title", session_type),
             row["start_time"], dur, dist, row["avg_hr"], row["max_hr"], row["calories"], speed, pace,
             stream["lat"] is not None, False, False, "app"))
        con.executemany("INSERT INTO exercises (workout_id, exercise) VALUES (?, ?)",
                        [(wid, e) for e in exercises])
        con.execute("INSERT INTO workout_flags (workout_id, flagged, score, reasons) VALUES (?,?,?,?)",
                    (wid, flags["flagged"], float(len(flags["reasons"])), ", ".join(flags["reasons"])))
        con.commit()
    store.write_streams({wid: stream}, con, if_exists="append")
    return wid
