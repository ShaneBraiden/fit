"""Account endpoints: sign up, sign in, and everything about the signed-in user.

Every /api/me request carries `Authorization: Bearer <token>`; the token decides
whose data is read or written, so one user can never reach another's workouts.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Response

from fitmine import config as C
from fitmine import live
from fitmine import models_runtime as RT
from fitmine.analyses.common import jsonable
from fitmine.data import generator as G
from fitmine.data import geo, store

from .. import state
from ..schemas import (Account, Alert, AuthResult, Catalog, LoginRequest, Profile, ProfileUpdate, Recommendation,
                       RecordRequest, RecordResult, SignupRequest, UserRoutes, WorkoutDetail, WorkoutItem)

router = APIRouter(prefix="/api", tags=["account"])

ITEM_COLS = ["workout_id", "activity", "session_type", "title", "start_time", "duration_min", "distance_km", "avg_hr",
             "max_hr", "calories", "has_gps", "flagged", "reasons", "route_name", "source"]

# Brute-force guard: at most 10 failed sign-ins per email per 15 minutes (per server process).
_fails: dict[str, list[float]] = defaultdict(list)
_fails_lock = threading.Lock()


def db(con=Depends(state.con)):
    live.ensure_tables(con)
    return con


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in first.")
    return authorization[7:].strip()


def current_user(authorization: str | None = Header(None), con=Depends(db)) -> int:
    uid = live.user_for_token(con, _bearer(authorization))
    if uid is None:
        raise HTTPException(401, "Your session has expired. Sign in again.")
    return uid


def admin_user(uid: int = Depends(current_user), con=Depends(db)) -> int:
    if not live.account(con, uid)["is_admin"]:
        raise HTTPException(403, "Only admins can open the model pages.")
    return uid


# ----------------------------------------------------------------------------- auth

@router.post("/auth/signup", response_model=AuthResult)
def signup(req: SignupRequest, con=Depends(db)):
    try:
        uid = live.signup(con, req.email, req.password, req.model_dump(exclude={"email", "password"}))
    except live.AccountError as e:
        raise HTTPException(400, str(e))
    return {"token": live.issue_token(con, uid), "account": live.account(con, uid)}


@router.post("/auth/login", response_model=AuthResult)
def login(req: LoginRequest, con=Depends(db)):
    key = req.email.strip().lower()
    now = time.time()
    with _fails_lock:
        _fails[key] = [t for t in _fails[key] if now - t < 900]
        if len(_fails[key]) >= 10:
            raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    uid = live.login(con, req.email, req.password)
    if uid is None:
        with _fails_lock:
            _fails[key].append(now)
        raise HTTPException(401, "Wrong email or password.")
    with _fails_lock:
        _fails.pop(key, None)
    return {"token": live.issue_token(con, uid), "account": live.account(con, uid)}


@router.post("/auth/logout", status_code=204)
def logout(authorization: str | None = Header(None), con=Depends(db)):
    live.revoke_token(con, _bearer(authorization))
    return Response(status_code=204)


@router.get("/me", response_model=Account)
def me(uid: int = Depends(current_user), con=Depends(db)):
    return live.account(con, uid)


@router.patch("/me", response_model=Account)
def update_me(req: ProfileUpdate, uid: int = Depends(current_user), con=Depends(db)):
    return live.update_profile(con, uid, req.model_dump(exclude_unset=True))


@router.get("/catalog", response_model=Catalog)
def catalog():
    extras = ["Plank", "Stretching", "Foam Rolling"]
    strength = sorted({e for s in ("Push", "Pull", "Legs") for e, _ in G.TEMPLATES[s]} | {"Leg Curl", *extras})
    return {
        "activities": C.ACTIVITIES, "gps_activities": sorted(C.GPS_ACTIVITIES),
        "exercises": {
            "Strength": strength,
            "HIIT": [e for e, _ in G.TEMPLATES["HIIT"]] + ["Stretching"],
            "Yoga": [e for e, _ in G.TEMPLATES["Yoga"]] + ["Stretching"],
            **{a: ["Stretching", "Foam Rolling"] for a in ("Run", "Walk", "Cycle", "Swim")},
        },
    }


# ----------------------------------------------------------------------------- the user's data

def _items(df: pd.DataFrame) -> list[dict]:
    out = []
    for r in df[ITEM_COLS].to_dict("records"):
        r = jsonable(r)
        r["has_gps"] = bool(r["has_gps"])
        r["flagged"] = bool(r["flagged"])
        r["reasons"] = r["reasons"] or ""
        out.append(r)
    return out


def _detail(con, uid: int, workout_id: int) -> dict:
    df = live.workouts(con, uid, "AND workout_id=?", (workout_id,))
    if df.empty:
        raise HTTPException(404, "Workout not found.")
    s = store.load_stream(con, workout_id, "live_streams")
    out = {"workout": _items(df)[0], "exercises": live.exercises(con, [workout_id]).exercise.tolist(),
           "hr": [] if s is None else s["hr"].astype(int).tolist(), "dt": C.STREAM_INTERVAL_S, "lat": None,
           "lon": None, "speed_kmh": None, "segments": None, "run_kind": None, "route": None}
    if s is not None and s["lat"] is not None:
        out.update(lat=np.round(s["lat"], 6).tolist(), lon=np.round(s["lon"], 6).tolist())
        seg = RT.segment(s)
        if seg:
            out.update(speed_kmh=seg["speed_kmh"], segments=jsonable(seg["segments"]), run_kind=seg["kind"])
        out["route"] = RT.match_route(s)
    return out


@router.get("/me/profile", response_model=Profile)
def profile(uid: int = Depends(current_user), con=Depends(db)):
    return jsonable(live.profile(con, uid))


@router.get("/me/workouts", response_model=list[WorkoutItem])
def workouts(limit: int = 60, uid: int = Depends(current_user), con=Depends(db)):
    return _items(live.workouts(con, uid, limit=min(limit, 500)))


@router.get("/me/workouts/{workout_id}", response_model=WorkoutDetail)
def workout_detail(workout_id: int, uid: int = Depends(current_user), con=Depends(db)):
    return _detail(con, uid, workout_id)


@router.delete("/me/workouts/{workout_id}", status_code=204)
def delete_workout(workout_id: int, uid: int = Depends(current_user), con=Depends(db)):
    if not live.delete_workout(con, uid, workout_id):
        raise HTTPException(404, "Workout not found.")
    return Response(status_code=204)


@router.post("/me/workouts", response_model=RecordResult)
def record(req: RecordRequest, uid: int = Depends(current_user), con=Depends(db)):
    known = set(G.ALL_EXERCISES)
    unknown = [e for e in req.exercises if e not in known]
    if unknown:
        raise HTTPException(422, f"Unknown exercise: {', '.join(unknown)}")
    body = req.model_dump()
    body["start_time"] = (req.start_time.replace(tzinfo=None).strftime(live.TS) if req.start_time else None)
    body["track"] = [p.model_dump() for p in req.track] if req.track else None
    r = live.record(con, uid, body)
    return {
        "workout": _items(live.workouts(con, uid, "AND workout_id=?", (r["workout_id"],)))[0],
        "verdict": {"flagged": r["verdict"]["flagged"], "reasons": r["verdict"]["reasons"]},
        "detail": _detail(con, uid, r["workout_id"]),
        "level_before": r["before"]["level"]["value"], "level_after": r["after"]["level"]["value"],
        "persona_before": r["before"]["persona"]["name"], "persona_after": r["after"]["persona"]["name"],
        "recommendations": r["recommendations"],
    }


@router.get("/me/recommendations", response_model=list[Recommendation])
def recommendations(uid: int = Depends(current_user), con=Depends(db)):
    return live.recommendations(con, uid)


@router.get("/me/alerts", response_model=list[Alert])
def alerts(uid: int = Depends(current_user), con=Depends(db)):
    return [{"workout_id": int(r["workout_id"]), "title": f"{r['title']} needs a look", "detail": r["reasons"],
             "start_time": r["start_time"]}
            for r in live.workouts(con, uid, "AND flagged").to_dict("records")]


@router.get("/me/routes", response_model=UserRoutes)
def routes(uid: int = Depends(current_user), con=Depends(db)):
    w = live.workouts(con, uid, "AND has_gps")
    starts = w[["start_lat", "start_lon"]].dropna().to_numpy(float)
    popular = []
    for c in state.report("routines_routes")["routes"]["clusters"]:
        la, lo = c["track"][0]
        if len(starts) and geo.haversine_m(starts[:, 0], starts[:, 1], la, lo).min() < 25_000:
            popular.append({"cluster": c["cluster"], "name": c["landmark"], "size": c["size"], "track": c["track"]})
    return {"popular": popular, "workouts": _items(w)}
