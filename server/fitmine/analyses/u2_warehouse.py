"""U2 Data warehouse and OLAP: a star schema over the clean workouts and a cube
with concept hierarchies (date: day < week < month < quarter < year, time: hour < band,
activity: activity < category, location: zone < city, user attributes)."""
from __future__ import annotations

import pandas as pd

from .. import config as C
from ..algorithms.olap import Cube
from ..data import geo, store

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BANDS = [(5, 8, "Early morning"), (8, 12, "Morning"), (12, 17, "Afternoon"), (17, 21, "Evening"), (21, 29, "Night")]
BAND_ORDER = [b for _, _, b in BANDS]
AGE_ORDER = ["18-24", "25-34", "35-44", "45-54", "55+"]
LEVEL_ORDER = C.LEVELS + ["Unassessed"]

HIERARCHIES = {
    "date": ["day", "week", "month", "quarter", "year"],
    "time": ["hour", "band"],
    "activity": ["activity", "category"],
    "location": ["zone", "city"],
    "gender": ["gender"],
    "age_group": ["age_group"],
    "level": ["level"],
    "device": ["device"],
    "weekday": ["day_name", "day_type"],
    "user": ["user_key"],
}
TABLES = {"date": "dim_date", "time": "dim_time", "activity": "dim_activity", "location": "dim_location",
          "gender": "dim_user", "age_group": "dim_user", "level": "dim_user", "device": "dim_user",
          "weekday": "dim_date", "user": "dim_user"}
MEASURES = ["sessions", "duration_min", "distance_km", "calories", "avg_hr"]
ORDERS = {"band": BAND_ORDER, "age_group": AGE_ORDER, "level": LEVEL_ORDER, "day_name": DAY_NAMES,
          "category": ["Cardio", "Strength", "Mind-Body"], "activity": C.ACTIVITIES, "zone": C.ZONES}


def band(hour: int) -> str:
    return next(b for lo, hi, b in BANDS if lo <= hour < hi) if 5 <= hour < 29 else "Night"


def build_star(con) -> dict[str, pd.DataFrame]:
    users = store.read("users", con)
    w = store.read("workouts", con)
    w["start_time"] = pd.to_datetime(w.start_time)

    dates = pd.to_datetime(sorted(w.start_time.dt.normalize().unique()))
    iso = dates.isocalendar()
    dim_date = pd.DataFrame({
        "date_key": dates.strftime("%Y%m%d").astype(int), "day": dates.strftime("%Y-%m-%d"),
        "day_name": dates.day_name(), "day_type": ["Weekend" if d >= 5 else "Weekday" for d in dates.dayofweek],
        "week": [f"{y}-W{wk:02d}" for y, wk in zip(iso.year, iso.week)], "month": dates.strftime("%Y-%m"),
        "quarter": [f"{d.year}-Q{d.quarter}" for d in dates], "year": dates.year.astype(str),
    })
    dim_time = pd.DataFrame({"time_key": range(24), "hour": [f"{h:02d}:00" for h in range(24)],
                             "band": [band(h) for h in range(24)]})
    dim_activity = pd.DataFrame({"activity_key": range(len(C.ACTIVITIES)), "activity": C.ACTIVITIES,
                                 "category": [C.ACTIVITY_CATEGORY[a] for a in C.ACTIVITIES]})
    dim_location = pd.DataFrame({"location_key": range(len(C.ZONES)), "zone": C.ZONES, "city": C.CITY})
    dim_user = users[["user_id", "gender", "age_group", "device", "home_zone"]].rename(columns={"user_id": "user_key"})
    dim_user["level"] = users.assessed_level.fillna("Unassessed")

    # Location of a workout: zone of its GPS start point, else the user's home zone.
    streams = store.load_streams(con, w.workout_id[w.has_gps.astype(bool)])
    starts = {wid: geo.nearest_zone(s["lat"][0], s["lon"][0]) for wid, s in streams.items() if s["lat"] is not None}
    home = users.set_index("user_id").home_zone
    zone = [starts.get(wid, home.get(uid)) for wid, uid in zip(w.workout_id, w.user_id)]
    fact = pd.DataFrame({
        "workout_id": w.workout_id, "user_key": w.user_id,
        "date_key": w.start_time.dt.strftime("%Y%m%d").astype(int), "time_key": w.start_time.dt.hour,
        "activity_key": w.activity.map({a: i for i, a in enumerate(C.ACTIVITIES)}),
        "location_key": pd.Series(zone).map({z: i for i, z in enumerate(C.ZONES)}).to_numpy(),
        "sessions": 1, "duration_min": w.duration_min, "distance_km": w.distance_km, "calories": w.calories,
        "avg_hr": w.avg_hr,
    })
    tables = {"dim_date": dim_date, "dim_time": dim_time, "dim_activity": dim_activity,
              "dim_location": dim_location, "dim_user": dim_user, "fact_workout": fact}
    for name, df in tables.items():
        store.write(df, name, con)
    return tables


def cube_from(tables: dict[str, pd.DataFrame]) -> Cube:
    f = tables["fact_workout"]
    base = (f.merge(tables["dim_date"], on="date_key").merge(tables["dim_time"], on="time_key")
            .merge(tables["dim_activity"], on="activity_key").merge(tables["dim_location"], on="location_key")
            .merge(tables["dim_user"], on="user_key"))
    base["user_key"] = base.user_key.astype(str)
    return Cube(base, HIERARCHIES, MEASURES, ORDERS, TABLES)


def load_cube(con) -> Cube:
    names = ["dim_date", "dim_time", "dim_activity", "dim_location", "dim_user", "fact_workout"]
    return cube_from({n: store.read(n, con) for n in names})


DEFAULT_SPEC = {"rows": [{"dim": "date", "level": "week"}], "cols": [{"dim": "activity", "level": "category"}],
                "measure": "duration_min", "agg": "sum", "filters": []}


def run(con) -> dict:
    tables = build_star(con)
    cube = cube_from(tables)
    schema = {name: {"rows": len(df), "columns": list(df.columns)} for name, df in tables.items()}
    examples = []
    for title, spec in [
        ("Training minutes per week by category", DEFAULT_SPEC),
        ("Calories by zone and month", {"rows": [{"dim": "location", "level": "zone"}],
                                        "cols": [{"dim": "date", "level": "month"}],
                                        "measure": "calories", "agg": "sum", "filters": []}),
        ("Peak workout times (sessions by band and weekday)", {"rows": [{"dim": "time", "level": "band"}],
                                                               "cols": [{"dim": "weekday", "level": "day_name"}],
                                                               "measure": "sessions", "agg": "sum", "filters": []}),
        ("Average heart rate by age group and activity", {"rows": [{"dim": "age_group", "level": "age_group"}],
                                                          "cols": [{"dim": "activity", "level": "activity"}],
                                                          "measure": "avg_hr", "agg": "avg", "filters": []}),
    ]:
        r = cube.query(spec)
        examples.append({"title": title, **r})
    lattice = cube.lattice([("date", "month"), ("activity", "activity"), ("location", "zone"), ("gender", "gender")],
                           "calories")
    return {
        "schema": schema,
        "hierarchies": {k: v for k, v in HIERARCHIES.items() if k != "user"},
        "measures": MEASURES,
        "default_spec": DEFAULT_SPEC,
        "examples": examples,
        "lattice": lattice,
        "facts": int(len(tables["fact_workout"])),
    }
