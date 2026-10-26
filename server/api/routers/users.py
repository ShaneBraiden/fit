"""Mobile endpoints: each one applies mined knowledge to one user.

  profile          classifier (U4) + nearest persona centroid (U5) recomputed live,
                   weekly OLAP roll-up (U2), routines from GSP (U7)
  recommendations  association rules (U3) whose antecedent the user already does
  alerts           outlier flags (U6) on workouts and on the profile
  routes           route clusters (U7) and the user's matched tracks
  upload           a new (simulated) recording is scored by every detector, segmented,
                   matched to a route, stored, and the user's level/persona refreshed
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from fitmine import models_runtime as RT
from fitmine.algorithms.olap import Cube
from fitmine import config as C
from fitmine.analyses.common import jsonable
from fitmine.data import store

from .. import state
from ..schemas import (Alert, Profile, Recommendation, UploadRequest, UploadResult, UserRoutes, UserSummary,
                       WorkoutDetail, WorkoutItem)

router = APIRouter(prefix="/api/users", tags=["mobile"])

WORKOUT_SQL = """
SELECT w.workout_id, w.activity, w.session_type, w.title, w.start_time, w.duration_min, w.distance_km, w.avg_hr,
       w.max_hr, w.calories, w.has_gps, w.source, COALESCE(f.flagged, FALSE) AS flagged,
       COALESCE(f.reasons, '') AS reasons, r.route_name
FROM workouts w
LEFT JOIN workout_flags f USING (workout_id)
LEFT JOIN workout_routes r USING (workout_id)
"""


def _user(con, user_id: int) -> pd.Series:
    u = store.read("users", con, "WHERE user_id=?", (user_id,))
    if u.empty:
        raise HTTPException(404, f"user {user_id} not found")
    return u.iloc[0]


def _items(df: pd.DataFrame) -> list[WorkoutItem]:
    out = []
    for r in df.to_dict("records"):
        r = jsonable(r)
        r["has_gps"] = bool(r["has_gps"])
        r["flagged"] = bool(r["flagged"])
        r["reasons"] = r["reasons"] or ""
        out.append(WorkoutItem(**r))
    return out


def _workouts(con, user_id: int, where: str = "", params=(), limit: int | None = None) -> pd.DataFrame:
    q = WORKOUT_SQL + " WHERE w.user_id=? " + where + " ORDER BY w.start_time DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    return store.query(q, con, (user_id, *params))


@router.get("", response_model=list[UserSummary])
def list_users(query: str = "", limit: int = 50, featured: bool = False, con=Depends(state.con)):
    df = store.query(
        "SELECT u.user_id, u.name, u.gender, u.age, u.home_zone, i.level, i.level_source, i.persona, "
        "i.spoof_flag AS flagged FROM users u JOIN user_insights i USING (user_id) ORDER BY u.user_id", con)
    if query:
        q = query.lower()
        df = df[df.name.str.lower().str.contains(q, regex=False) | (df.user_id.astype(str) == q)
                | df.persona.str.lower().str.contains(q, regex=False)]
    if featured:  # a few users per persona plus every flagged profile: good demo accounts
        df = pd.concat([df.groupby("persona").head(3), df[df.flagged.astype(bool)]]).drop_duplicates("user_id")
    return [UserSummary(**{**r, "flagged": bool(r["flagged"])}) for r in jsonable(df.head(limit).to_dict("records"))]


def _weekly(w: pd.DataFrame) -> list[dict]:
    """OLAP on one user's slice: roll days up to weeks, minutes by activity category."""
    if w.empty:
        return []
    base = w.assign(start_time=pd.to_datetime(w.start_time))
    base["week"] = base.start_time.dt.strftime("%G-W%V")
    base["category"] = base.activity.map(C.ACTIVITY_CATEGORY)
    base["sessions"] = 1
    cube = Cube(base, {"date": ["week"], "activity": ["category"]}, ["duration_min", "sessions", "calories"])
    mins = cube.query({"rows": [{"dim": "date", "level": "week"}], "cols": [{"dim": "activity", "level": "category"}],
                       "measure": "duration_min", "agg": "sum", "filters": []})
    sess = cube.query({"rows": [{"dim": "date", "level": "week"}], "cols": [], "measure": "sessions", "agg": "sum",
                       "filters": []})
    cal = cube.query({"rows": [{"dim": "date", "level": "week"}], "cols": [], "measure": "calories", "agg": "sum",
                      "filters": []})
    cats = [c[0] for c in mins["col_headers"]]
    out = []
    for i, wk in enumerate(mins["row_headers"]):
        out.append({"week": wk[0], "minutes": {c: v or 0.0 for c, v in zip(cats, mins["values"][i])},
                    "sessions": int(sess["values"][i][0] or 0), "calories": float(cal["values"][i][0] or 0)})
    return out[-8:]


def _profile(con, user_id: int) -> dict:
    u = _user(con, user_id)
    ins = store.read("user_insights", con, "WHERE user_id=?", (user_id,))
    rt = RT.user_profile(con, user_id)
    assessed = u.assessed_level if isinstance(u.assessed_level, str) else None
    names = store.query(
        f"SELECT u.user_id, u.name, i.persona FROM users u JOIN user_insights i USING (user_id) "
        f"WHERE u.user_id IN ({','.join(str(int(s)) for s in rt['similar']) or '0'})", con).set_index("user_id")
    w = store.read("workouts", con, "WHERE user_id=?", (user_id,))
    nflag = con.execute("SELECT COUNT(*) FROM workout_flags f JOIN workouts w USING (workout_id) "
                        "WHERE w.user_id=? AND f.flagged", (user_id,)).fetchone()[0]
    f = rt["features"]
    return {
        "user": jsonable(u.drop(labels=["weight_imputed"], errors="ignore").to_dict()),
        "level": {"value": assessed or rt["predicted_level"], "source": "assessed" if assessed else "predicted",
                  "predicted": rt["predicted_level"], "probabilities": rt["level_proba"]},
        "persona": {"name": rt["persona"], "cluster": rt["cluster"], "distances": rt["persona_distance"]},
        "similar": [{"user_id": int(s), "name": names.name.get(s, "?"), "persona": names.persona.get(s, "?")}
                    for s in rt["similar"]],
        "weekly": _weekly(w),
        "routines": json.loads(ins.routines.iat[0]) if len(ins) else [],
        "stats": {k: f.get(k) for k in ("sessions_per_week", "minutes_per_week", "avg_duration", "avg_intensity",
                                        "run_pace", "longest_km", "vo2max", "resting_hr", "bmi")},
        "spoof_flag": bool(ins.spoof_flag.iat[0]) if len(ins) else False,
        "spoof_reasons": json.loads(ins.spoof_reasons.iat[0]) if len(ins) else [],
        "flagged_workouts": int(nflag),
    }


@router.get("/{user_id}/profile", response_model=Profile)
def profile(user_id: int, con=Depends(state.con)):
    return _profile(con, user_id)


@router.get("/{user_id}/workouts", response_model=list[WorkoutItem])
def workouts(user_id: int, limit: int = 60, con=Depends(state.con)):
    _user(con, user_id)
    return _items(_workouts(con, user_id, limit=limit))


def _detail(con, user_id: int, workout_id: int) -> dict:
    df = _workouts(con, user_id, "AND w.workout_id=?", (workout_id,))
    if df.empty:
        raise HTTPException(404, "workout not found for this user")
    s = store.load_stream(con, workout_id)
    ex = store.read("exercises", con, "WHERE workout_id=?", (workout_id,)).exercise.tolist()
    item = _items(df)[0]
    out = {"workout": item, "exercises": ex, "hr": [] if s is None else s["hr"].astype(int).tolist(),
           "dt": C.STREAM_INTERVAL_S, "lat": None, "lon": None, "speed_kmh": None, "segments": None,
           "run_kind": None, "route": None}
    if s is not None and s["lat"] is not None:
        seg = RT.segment(s)
        out.update(lat=np.round(s["lat"], 6).tolist(), lon=np.round(s["lon"], 6).tolist(),
                   speed_kmh=seg["speed_kmh"], segments=jsonable(seg["segments"]), run_kind=seg["kind"],
                   route=RT.match_route(s))
    return out


@router.get("/{user_id}/workouts/{workout_id}", response_model=WorkoutDetail)
def workout_detail(user_id: int, workout_id: int, con=Depends(state.con)):
    return _detail(con, user_id, workout_id)


@router.get("/{user_id}/recommendations", response_model=list[Recommendation])
def recommendations(user_id: int, con=Depends(state.con)):
    _user(con, user_id)
    return RT.recommendations(con, user_id)


@router.get("/{user_id}/routes", response_model=UserRoutes)
def routes(user_id: int, con=Depends(state.con)):
    _user(con, user_id)
    rep = state.report("u7")["routes"]
    popular = [{"cluster": c["cluster"], "name": c["landmark"], "size": c["size"], "track": c["track"]}
               for c in rep["clusters"]]
    return {"popular": popular, "workouts": _items(_workouts(con, user_id, "AND w.has_gps"))}


@router.get("/{user_id}/alerts", response_model=list[Alert])
def alerts(user_id: int, con=Depends(state.con)):
    _user(con, user_id)
    out = []
    ins = store.read("user_insights", con, "WHERE user_id=?", (user_id,))
    if len(ins) and bool(ins.spoof_flag.iat[0]):
        for r in json.loads(ins.spoof_reasons.iat[0]):
            out.append({"kind": "profile", "workout_id": None, "title": "Profile looks inconsistent", "detail": r,
                        "start_time": None})
    for r in _workouts(con, user_id, "AND f.flagged").to_dict("records"):
        out.append({"kind": "workout", "workout_id": int(r["workout_id"]),
                    "title": f"{r['title']} flagged", "detail": r["reasons"], "start_time": r["start_time"]})
    return out


@router.post("/{user_id}/workouts", response_model=UploadResult)
def upload(user_id: int, req: UploadRequest, con=Depends(state.con)):
    u = _user(con, user_id)
    before = RT.user_profile(con, user_id)
    sim = RT.simulate_stream(con, user_id, req.activity, req.kind, req.route, list(req.faults))
    row, s = sim["row"], sim["stream"]
    row["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if req.title:
        row["title"] = req.title
    verdict = RT.score_workout(u, req.activity, row["calories"], row["duration_min"], s, row["start_time"], user_id)
    route = RT.match_route(s)
    wid = RT.insert_workout(con, user_id, row, s, req.exercises or sim["exercises"], sim["session_type"], verdict)
    if s["lat"] is not None:
        con.execute("INSERT INTO workout_routes (workout_id, route_cluster, route_name, hausdorff_m) VALUES (?,?,?,?)",
                    (wid, None if route is None else route["cluster"], None if route is None else route["name"],
                     None if route is None else route["hausdorff_m"]))
        con.commit()
    after = RT.user_profile(con, user_id)
    detail = _detail(con, user_id, wid)
    return {
        "workout": detail["workout"], "verdict": jsonable(verdict), "detail": detail,
        "level_before": before["predicted_level"], "level_after": after["predicted_level"],
        "persona_before": before["persona"], "persona_after": after["persona"],
        "recommendations": RT.recommendations(con, user_id),
    }

