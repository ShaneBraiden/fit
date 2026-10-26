"""Real accounts and their own workouts.

Everything here lives in its own tables, which the mining pipeline never rebuilds,
so accounts and recorded workouts survive every redeploy:

  accounts       email, password hash (scrypt), when the account was made
  auth_tokens    sha-256 of each sign-in token, with an expiry
  live_users     the profile the user entered (age, body, optional resting HR / VO2max)
  live_workouts  each recorded or logged workout, with its data-check verdict and route
  live_exercises the exercises done in each workout
  live_streams   resampled GPS (and HR when available) streams, same encoding as `streams`

The models trained on the synthetic population are applied to these rows: the
fitness level and persona come from the user's own last eight weeks of workouts.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import config as C
from . import models_runtime as RT
from .algorithms import trajectory as T
from .analyses.common import expected_calories, hrmax_pred, jsonable
from .data import generator as G
from .data import store

WINDOW_DAYS = 7 * C.WEEKS  # the profile is computed from this many recent days
TS = "%Y-%m-%d %H:%M:%S"

DDL = [
    "CREATE TABLE IF NOT EXISTS accounts (user_id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, "
    "password_hash TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS auth_tokens (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, "
    "created_at TEXT NOT NULL, expires_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS live_users (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, gender TEXT NOT NULL, "
    "age INTEGER NOT NULL, height_cm DOUBLE PRECISION NOT NULL, weight_kg DOUBLE PRECISION NOT NULL, "
    "bmi DOUBLE PRECISION NOT NULL, resting_hr DOUBLE PRECISION, vo2max DOUBLE PRECISION, signup_date TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS live_workouts (workout_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
    "activity TEXT NOT NULL, session_type TEXT NOT NULL, title TEXT NOT NULL, start_time TEXT NOT NULL, "
    "duration_min DOUBLE PRECISION NOT NULL, distance_km DOUBLE PRECISION, avg_hr DOUBLE PRECISION, "
    "max_hr DOUBLE PRECISION, calories DOUBLE PRECISION, speed_kmh DOUBLE PRECISION, pace_min_km DOUBLE PRECISION, "
    "has_gps BOOLEAN NOT NULL, source TEXT NOT NULL, flagged BOOLEAN NOT NULL, reasons TEXT NOT NULL, "
    "route_name TEXT, start_lat DOUBLE PRECISION, start_lon DOUBLE PRECISION)",
    "CREATE TABLE IF NOT EXISTS live_exercises (workout_id INTEGER NOT NULL, exercise TEXT NOT NULL)",
]
_ready = False


def ensure_tables(con):
    global _ready
    if _ready:
        return
    with store._lock:
        for sql in DDL:
            con.execute(sql)
        con.commit()
    store.write_streams({}, con, if_exists="append", table="live_streams")
    _ready = True


def _now() -> str:
    return datetime.now().strftime(TS)


def _next_id(con, table: str, col: str) -> int:
    return int(con.execute(f"SELECT COALESCE(MAX({col}), 0) + 1 FROM {table}").fetchone()[0])


# ----------------------------------------------------------------------------- passwords and tokens

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
    except ValueError:
        return False
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
    return hmac.compare_digest(got.hex(), h)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(con, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    con.execute("INSERT INTO auth_tokens (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (_token_hash(token), int(user_id), now.strftime(TS),
                 (now + timedelta(days=C.TOKEN_DAYS)).strftime(TS)))
    con.commit()
    return token


def user_for_token(con, token: str) -> int | None:
    r = con.execute("SELECT user_id, expires_at FROM auth_tokens WHERE token_hash=?", (_token_hash(token),)).fetchone()
    if r is None or r[1] < _now():
        return None
    return int(r[0])


def revoke_token(con, token: str):
    con.execute("DELETE FROM auth_tokens WHERE token_hash=?", (_token_hash(token),))
    con.commit()


# ----------------------------------------------------------------------------- accounts

class AccountError(ValueError):
    pass


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def signup(con, email: str, password: str, profile: dict) -> int:
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise AccountError("Enter a valid email address.")
    if len(password) < 8:
        raise AccountError("Use a password of at least 8 characters.")
    with store._lock:
        if con.execute("SELECT 1 FROM accounts WHERE email=?", (email,)).fetchone():
            raise AccountError("An account with this email already exists. Sign in instead.")
        uid = _next_id(con, "accounts", "user_id")
        con.execute("INSERT INTO accounts (user_id, email, password_hash, created_at) VALUES (?,?,?,?)",
                    (uid, email, hash_password(password), _now()))
        p = profile
        bmi = round(p["weight_kg"] / (p["height_cm"] / 100) ** 2, 1)
        con.execute("INSERT INTO live_users (user_id, name, gender, age, height_cm, weight_kg, bmi, resting_hr, vo2max, "
                    "signup_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (uid, p["name"].strip(), p["gender"], int(p["age"]), float(p["height_cm"]), float(p["weight_kg"]),
                     bmi, p.get("resting_hr"), p.get("vo2max"), datetime.now().strftime("%Y-%m-%d")))
        con.commit()
    return uid


def login(con, email: str, password: str) -> int | None:
    r = con.execute("SELECT user_id, password_hash FROM accounts WHERE email=?", (email.strip().lower(),)).fetchone()
    if r is None or not check_password(password, r[1]):
        return None
    return int(r[0])


def account(con, user_id: int) -> dict:
    a = con.execute("SELECT email FROM accounts WHERE user_id=?", (int(user_id),)).fetchone()
    u = store.read("live_users", con, "WHERE user_id=?", (int(user_id),))
    if a is None or u.empty:
        raise KeyError(user_id)
    return {**jsonable(u.iloc[0].to_dict()), "email": a[0], "is_admin": a[0] in C.ADMIN_EMAILS}


def update_profile(con, user_id: int, changes: dict) -> dict:
    u = store.read("live_users", con, "WHERE user_id=?", (int(user_id),)).iloc[0].to_dict()
    u.update({k: v for k, v in changes.items() if k in ("name", "gender", "age", "height_cm", "weight_kg",
                                                         "resting_hr", "vo2max")})
    u["bmi"] = round(u["weight_kg"] / (u["height_cm"] / 100) ** 2, 1)
    con.execute("UPDATE live_users SET name=?, gender=?, age=?, height_cm=?, weight_kg=?, bmi=?, resting_hr=?, "
                "vo2max=? WHERE user_id=?",
                (u["name"], u["gender"], int(u["age"]), float(u["height_cm"]), float(u["weight_kg"]), u["bmi"],
                 None if pd.isna(u["resting_hr"]) else float(u["resting_hr"]),
                 None if pd.isna(u["vo2max"]) else float(u["vo2max"]), int(user_id)))
    con.commit()
    return account(con, user_id)


# ----------------------------------------------------------------------------- reading a user's data

def user_row(con, user_id: int) -> pd.DataFrame:
    return store.read("live_users", con, "WHERE user_id=?", (int(user_id),))


def workouts(con, user_id: int, where: str = "", params=(), limit: int | None = None) -> pd.DataFrame:
    q = "WHERE user_id=? " + where + " ORDER BY start_time DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    return store.read("live_workouts", con, q, (int(user_id), *params))


def exercises(con, workout_ids) -> pd.DataFrame:
    ids = [int(i) for i in workout_ids]
    if not ids:
        return pd.DataFrame(columns=["workout_id", "exercise"])
    return store.read("live_exercises", con, f"WHERE workout_id IN ({','.join('?' * len(ids))})", ids)


def recent_window(w: pd.DataFrame) -> pd.DataFrame:
    """The last WINDOW_DAYS of workouts that passed the data checks: what the models see."""
    since = (datetime.now() - timedelta(days=WINDOW_DAYS)).strftime(TS)
    return w[(w.start_time >= since) & ~w.flagged.astype(bool)]


def weeks_of_history(signup_date: str) -> float:
    """Divide weekly totals by the weeks the account has existed (1 .. C.WEEKS), so a new
    user with three workouts in their first week trains 3 times a week, not 3/8."""
    days = (datetime.now() - datetime.strptime(signup_date, "%Y-%m-%d")).days + 1
    return float(np.clip(days / 7, 1, C.WEEKS))


def estimate_vo2max(u: pd.Series, w: pd.DataFrame) -> tuple[float | None, str | None]:
    """The user's own value if they entered one; otherwise the best recent run (Daniels &
    Gilbert VDOT); otherwise the heart-rate ratio method (Uth et al. 2004) from resting HR."""
    if pd.notna(u.vo2max):
        return float(u.vo2max), "entered"
    runs = w[(w.activity == "Run") & (w.distance_km >= 1.5) & (w.duration_min >= 8)]
    if len(runs):
        t = runs.duration_min.to_numpy(float)
        v = runs.distance_km.to_numpy(float) * 1000 / t  # metres per minute
        vo2 = -4.60 + 0.182258 * v + 0.000104 * v ** 2
        frac = 0.8 + 0.1894393 * np.exp(-0.012778 * t) + 0.2989558 * np.exp(-0.1932605 * t)
        return float(np.clip((vo2 / frac).max(), 20, 85)), "your runs"
    if pd.notna(u.resting_hr):
        return float(np.clip(15.3 * hrmax_pred(u.age) / u.resting_hr, 20, 85)), "resting heart rate"
    return None, None


def weekly(w: pd.DataFrame) -> list[dict]:
    """Minutes per activity category, sessions and calories per ISO week (last 8 weeks)."""
    if w.empty:
        return []
    b = w.assign(start_time=pd.to_datetime(w.start_time))
    b["week"] = b.start_time.dt.strftime("%G-W%V")
    b["category"] = b.activity.map(C.ACTIVITY_CATEGORY)
    mins = b.pivot_table(index="week", columns="category", values="duration_min", aggfunc="sum", fill_value=0)
    out = []
    for wk, g in b.groupby("week"):
        out.append({"week": wk, "minutes": {c: float(mins.at[wk, c]) for c in mins.columns},
                    "sessions": int(len(g)), "calories": float(g.calories.fillna(0).sum())})
    return out[-8:]


def profile(con, user_id: int) -> dict:
    u = user_row(con, user_id)
    w_all = workouts(con, user_id)
    w = recent_window(w_all)
    vo2, vo2_src = estimate_vo2max(u.iloc[0], w)
    feats_user = u.assign(vo2max=vo2)[["user_id", "gender", "age", "bmi", "resting_hr", "vo2max"]]
    rt = RT.profile_of(feats_user, w, weeks_of_history(u.signup_date.iat[0]))
    f = rt["features"]
    return {
        "user": {**jsonable(u.iloc[0].to_dict()), "vo2max_estimate": vo2, "vo2max_source": vo2_src},
        "level": {"value": rt["predicted_level"], "source": "predicted", "predicted": rt["predicted_level"],
                  "probabilities": rt["level_proba"]},
        "persona": {"name": rt["persona"], "cluster": rt["cluster"], "distances": rt["persona_distance"]},
        "weekly": weekly(w_all[~w_all.flagged.astype(bool)]),
        "routines": RT.routines(w),
        "stats": {k: f.get(k) for k in ("sessions_per_week", "minutes_per_week", "avg_duration", "avg_intensity",
                                        "run_pace", "longest_km", "vo2max", "resting_hr", "bmi")},
        "workouts_counted": int(len(w)),
        "flagged_workouts": int(w_all.flagged.astype(bool).sum()),
    }


def recommendations(con, user_id: int, recent: int = 6) -> list[dict]:
    w = workouts(con, user_id, "AND NOT flagged", limit=recent)
    return RT.recommend(w, exercises(con, w.workout_id))


# ----------------------------------------------------------------------------- recording a workout

STRENGTH_SPLITS = ("Push", "Pull", "Legs")


def session_type(activity: str, kind: str | None, exercises_: list[str], seg: dict | None,
                 duration_min: float, distance_km: float | None) -> str:
    if activity == "Run":
        if seg and seg["kind"] == "intervals":
            return "IntervalRun"
        if seg and seg["kind"] == "tempo":
            return "TempoRun"
        return "LongRun" if duration_min >= 65 or (distance_km or 0) >= 14 else "EasyRun"
    if activity == "Strength":
        if kind and kind.title() in STRENGTH_SPLITS:
            return kind.title()
        overlap = {s: len(set(exercises_) & {e for e, _ in G.TEMPLATES[s]}) for s in STRENGTH_SPLITS}
        return max(overlap, key=overlap.get) if max(overlap.values()) else "Push"
    return activity


def resample_track(points: list[dict]) -> dict | None:
    """Phone GPS fixes (t in ms, lat, lon, accuracy m) -> a stream on the 15 s grid the
    models were trained on. Fixes less accurate than 35 m are dropped."""
    pts = sorted((p for p in points if (p.get("accuracy") or 0) <= 35), key=lambda p: p["t"])
    if len(pts) < 2:
        return None
    t = np.array([p["t"] for p in pts], float) / 1000
    t, keep = np.unique(t, return_index=True)
    lat = np.array([p["lat"] for p in pts], float)[keep]
    lon = np.array([p["lon"] for p in pts], float)[keep]
    if len(t) < 2 or t[-1] - t[0] < 30:
        return None
    grid = np.arange(t[0], t[-1] + 1e-9, C.STREAM_INTERVAL_S)
    if len(grid) < 2:
        grid = np.array([t[0], t[-1]])
    return {"hr": np.zeros(0, int), "lat": np.interp(grid, t, lat), "lon": np.interp(grid, t, lon)}


def record(con, user_id: int, req: dict) -> dict:
    """Store one workout (GPS-tracked or logged by hand), check it, and return the
    profile before and after so the app can show what changed."""
    ensure_tables(con)
    u = user_row(con, user_id).iloc[0]
    before = profile(con, user_id)
    activity = req["activity"]
    stream = resample_track(req.get("track") or []) if activity in C.GPS_ACTIVITIES else None
    distance = req.get("distance_km")
    duration = float(req["duration_min"])
    if stream is not None:
        distance = round(float(T.step_lengths(T.xy(stream["lat"], stream["lon"])).sum() / 1000), 3)
    has_gps = stream is not None
    speed = distance / (duration / 60) if distance else None
    pace = duration / distance if distance and activity in ("Run", "Walk") else None
    ex = sorted(set(req.get("exercises") or []))
    if activity in G.CARDIO_ITEM:
        ex = sorted(set(ex) | {G.CARDIO_ITEM[activity]})
    seg = RT.segment(stream) if stream is not None else None
    stype = session_type(activity, req.get("kind"), ex, seg, duration, distance)
    calories = req.get("calories") or round(expected_calories(activity, float(u.weight_kg), duration, speed), 1)
    check_stream = stream or {"hr": np.zeros(0, int), "lat": None, "lon": None}
    verdict = RT.score_workout(u, activity, float(calories), duration, check_stream, -int(user_id))
    route = RT.match_route(stream) if stream is not None else None
    start = req.get("start_time") or _now()
    with store._lock:
        wid = _next_id(con, "live_workouts", "workout_id")
        con.execute(
            "INSERT INTO live_workouts (workout_id, user_id, activity, session_type, title, start_time, duration_min, "
            "distance_km, avg_hr, max_hr, calories, speed_kmh, pace_min_km, has_gps, source, flagged, reasons, "
            "route_name, start_lat, start_lon) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wid, int(user_id), activity, stype, (req.get("title") or "").strip() or G.SESSION_TITLES[stype][0],
             start, duration, distance, req.get("avg_hr"), req.get("max_hr"), float(calories), speed, pace, has_gps,
             "gps" if has_gps else "manual", verdict["flagged"], ", ".join(verdict["reasons"]),
             None if route is None else route["name"],
             float(stream["lat"][0]) if has_gps else None, float(stream["lon"][0]) if has_gps else None))
        con.executemany("INSERT INTO live_exercises (workout_id, exercise) VALUES (?, ?)", [(wid, e) for e in ex])
        con.commit()
    if stream is not None:
        store.write_streams({wid: stream}, con, if_exists="append", table="live_streams")
    after = profile(con, user_id)
    return {"workout_id": wid, "verdict": verdict, "before": before, "after": after,
            "recommendations": recommendations(con, user_id)}


def delete_workout(con, user_id: int, workout_id: int) -> bool:
    with store._lock:
        hit = con.execute("SELECT 1 FROM live_workouts WHERE workout_id=? AND user_id=?",
                          (int(workout_id), int(user_id))).fetchone()
        if not hit:
            return False
        for t in ("live_workouts", "live_exercises", "live_streams"):
            con.execute(f"DELETE FROM {t} WHERE workout_id=?", (int(workout_id),))
        con.commit()
    return True
