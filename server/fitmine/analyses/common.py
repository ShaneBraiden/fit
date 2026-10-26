"""Shared helpers for the unit analyses: artifacts, JSON conversion, feature builders."""
from __future__ import annotations

import json
import math
import pickle
import time
from contextlib import contextmanager

import numpy as np
import pandas as pd

from .. import config as C

ACTIVITY_SHARES = ["share_run", "share_cycle", "share_walk", "share_swim", "share_strength", "share_hiit", "share_yoga"]


def hrmax_pred(age):
    """Tanaka et al. (2001): HRmax = 208 - 0.7 x age."""
    return 208 - 0.7 * np.asarray(age, float)


def expected_calories(activity, weight_kg, duration_min, speed_kmh=None):
    met = speed_kmh if activity == "Run" and speed_kmh else C.MET.get(activity, 5.0)
    return met * weight_kg * duration_min / 60


# ----------------------------------------------------------------------------- JSON / artifacts

def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else float(f"{f:.7g}")  # 7 significant digits
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if o is pd.NA:
        return None
    return o


def save_json(name: str, obj) -> None:
    C.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (C.ARTIFACTS_DIR / f"{name}.json").write_text(json.dumps(jsonable(obj)), encoding="utf-8")


def load_json(name: str):
    p = C.ARTIFACTS_DIR / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_pickle(name: str, obj) -> None:
    C.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(C.ARTIFACTS_DIR / f"{name}.pkl", "wb") as f:
        pickle.dump(obj, f)


def load_pickle(name: str):
    p = C.ARTIFACTS_DIR / f"{name}.pkl"
    if not p.exists():
        return None
    with open(p, "rb") as f:
        return pickle.load(f)


@contextmanager
def timer(store: dict, key: str):
    t = time.perf_counter()
    yield
    store[key] = round((time.perf_counter() - t) * 1000, 1)


def histogram(x, bins: int = 20) -> dict:
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    counts, edges = np.histogram(x, bins=bins)
    return {"counts": counts.tolist(), "edges": edges.round(4).tolist()}


# ----------------------------------------------------------------------------- features

def user_features(users: pd.DataFrame, workouts: pd.DataFrame, weeks: float = C.WEEKS) -> pd.DataFrame:
    """One row per user: profile attributes plus behaviour aggregated over the history."""
    w = workouts.copy()
    w["start_time"] = pd.to_datetime(w["start_time"])
    # A live user's columns can be empty or all-null (no heart-rate sensor), which pandas reads as object.
    for c in ("duration_min", "distance_km", "avg_hr", "max_hr", "pace_min_km"):
        w[c] = pd.to_numeric(w[c], errors="coerce")
    users = users.astype({c: float for c in ("age", "bmi", "resting_hr", "vo2max")})
    u = users.set_index("user_id")
    w["hrr"] = (w.avg_hr - u.resting_hr.reindex(w.user_id).to_numpy()) / (
        hrmax_pred(u.age.reindex(w.user_id).to_numpy()) - u.resting_hr.reindex(w.user_id).to_numpy())
    g = w.groupby("user_id")
    f = pd.DataFrame(index=users.user_id)
    f["sessions_per_week"] = g.size().reindex(f.index).fillna(0) / weeks
    f["minutes_per_week"] = g.duration_min.sum().reindex(f.index).fillna(0) / weeks
    f["avg_duration"] = g.duration_min.mean().reindex(f.index)
    f["avg_intensity"] = g.hrr.mean().reindex(f.index).clip(0, 1.2)
    counts = w.pivot_table(index="user_id", columns="activity", values="workout_id", aggfunc="count", fill_value=0)
    total = counts.sum(axis=1)
    for col, act in zip(ACTIVITY_SHARES, ["Run", "Cycle", "Walk", "Swim", "Strength", "HIIT", "Yoga"]):
        f[col] = (counts[act] / total).reindex(f.index).fillna(0) if act in counts else 0.0
    runs = w[w.activity == "Run"]
    f["run_pace"] = runs.groupby("user_id").pace_min_km.median().reindex(f.index)
    f["longest_km"] = g.distance_km.max().reindex(f.index).fillna(0)
    f["morning_share"] = g.start_time.apply(lambda s: (s.dt.hour < 12).mean()).reindex(f.index)
    f["weekend_share"] = g.start_time.apply(lambda s: (s.dt.dayofweek >= 5).mean()).reindex(f.index)
    f["max_hr_p95"] = g.max_hr.quantile(0.95).reindex(f.index)
    prof = users.set_index("user_id")[["gender", "age", "bmi", "resting_hr", "vo2max"]]
    return prof.join(f).reset_index()
