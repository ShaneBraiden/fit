"""Apply the mined models to live data: check an uploaded workout, compute a
user's level and persona from their own workouts, suggest exercises from the
association rules, find routines, match routes and split runs into phases."""
from __future__ import annotations

import threading

import numpy as np
import pandas as pd

from . import config as C
from .algorithms import trajectory as T
from .analyses import data_checks as DC
from .analyses import routines_routes as RR
from .analyses.common import load_pickle, user_features

_lock = threading.Lock()
_models = None


def models() -> dict:
    global _models
    with _lock:
        if _models is None:
            _models = load_pickle("models")
            if _models is None:
                raise RuntimeError("models missing: run `python -m fitmine.pipeline run` first")
        return _models


def reload():
    global _models
    with _lock:
        _models = None


# ----------------------------------------------------------------------------- checking one workout

def score_workout(user: pd.Series, activity: str, calories: float, duration_min: float, stream: dict,
                  user_id: int) -> dict:
    """Run the data checks on a single new workout, using the reference statistics of its activity."""
    m = models()["outliers"]
    f = DC.stream_features(stream, user.age, activity, calories, user.weight_kg, duration_min)
    row = pd.Series({**f, "activity": activity})
    reasons = DC.rule_reasons(row)
    has_data = len(stream["hr"]) > 0 or stream["lat"] is not None
    owner = m["fingerprints"].get(DC.fingerprint(stream)) if has_data else None
    if owner is not None and owner != user_id:
        reasons.append("duplicate_of_other_user")
    ref = m["ref"].get(activity)
    detectors = {"rules": bool(DC.rule_reasons(row)), "duplicates": owner is not None and owner != user_id}
    scores = {}
    if ref:
        x = np.array([f.get(c, np.nan) for c in ref["cols"]], float)
        x = np.where(np.isnan(x), ref["medians"], x)
        z = ref["scaler"].transform(x[None])
        scores["iforest"] = float(ref["iforest"].score(z)[0])
        out_of_fence = [c for c, v, (lo, hi) in zip(ref["cols"], x, ref["fences"]) if v < lo or v > hi]
        detectors["iqr"] = bool(out_of_fence)
        detectors["iforest"] = scores["iforest"] > ref["if_thr"]
        if detectors["iqr"] and detectors["iforest"] and not reasons:
            reasons.append(f"unusual for a {activity.lower()} ({', '.join(out_of_fence[:3])})")
    return {"flagged": bool(reasons), "reasons": reasons, "detectors": detectors, "scores": scores,
            "features": {k: (None if isinstance(v, float) and np.isnan(v) else round(float(v), 3))
                         for k, v in f.items()}}


def match_route(stream: dict) -> dict | None:
    if stream["lat"] is None or len(stream["lat"]) < 2:
        return None
    r = models()["routes"]
    track = RR.resampled({0: stream}, [0])
    hit = RR.assign_routes(r, track)[0]
    return None if hit is None else {"cluster": hit[0], "name": hit[1], "hausdorff_m": round(hit[2], 1)}


def segment(stream: dict) -> dict | None:
    if stream["lat"] is None or len(stream["lat"]) < 8:
        return None
    r = T.segment_track(stream["lat"], stream["lon"], C.STREAM_INTERVAL_S)
    return {"kind": r["kind"], "segments": r["segments"], "change_points": r["change_points"],
            "speed_kmh": (r["speed"] * 3.6).round(2).tolist()}


# ----------------------------------------------------------------------------- per user

def profile_of(users: pd.DataFrame, w: pd.DataFrame, weeks: float = C.WEEKS) -> dict:
    """Features from one user's workouts, then the fitness-level tree and the nearest persona centre."""
    feats = user_features(users, w, weeks)
    mm = models()
    clf = mm["classifier"]
    proba = clf.predict_proba(feats)[0]
    cm = mm["cluster"]
    x = feats[cm["features"]].fillna(pd.Series(cm["medians"])).to_numpy(float)
    z = cm["scaler"].transform(x)
    d = ((cm["centres"] - z) ** 2).sum(1)
    cluster = int(d.argmin())
    f = feats.iloc[0]
    return {
        "level_proba": {str(c): float(p) for c, p in zip(clf.classes_, proba)},
        "predicted_level": str(clf.classes_[proba.argmax()]),
        "cluster": cluster, "persona": cm["names"][cluster],
        "persona_distance": {cm["names"][i]: float(np.sqrt(v)) for i, v in enumerate(d)},
        "features": {k: (None if pd.isna(v) else (float(v) if not isinstance(v, str) else v)) for k, v in f.items()},
    }


def recommend(w_recent: pd.DataFrame, ex: pd.DataFrame, top: int = 6) -> list[dict]:
    """For each of the user's latest workouts: rules whose antecedent was done in that session
    and whose consequent was not, i.e. "next time you do X, people usually add Y"."""
    if w_recent.empty:
        return []
    baskets = ex.groupby("workout_id").exercise.apply(set)
    rules = [r for r in models()["session_rules"] if len(r["consequent"]) == 1]
    best: dict[str, dict] = {}
    for wid in w_recent.workout_id:
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


def routines(w: pd.DataFrame) -> list[dict]:
    """Mined weekly routines this user follows in at least half of their weeks."""
    if w.empty:
        return []
    seqs, keys = RR.sequences_of(w)
    return RR.user_routines(seqs, keys, models()["patterns"]).get(int(w.user_id.iat[0]), [])
