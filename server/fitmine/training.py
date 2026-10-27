"""Training features built on the user's own workouts: muscle progress, the daily
streak with its calendar, and the weekly plan (any split, not only push/pull/legs).

  training_plans   one row per user: the plan's name and its seven days as JSON (Mon..Sun)

Muscle progress counts hard sets per muscle and week. Each exercise works one or more
primary muscles (a set counts 1) and secondary muscles (a set counts 0.5). Sets, reps
and weight are optional when logging; an exercise logged without sets counts as 3.
Cardio and yoga mark a muscle as trained but add no sets. With weight and reps the
estimated one-rep max (Epley: kg x (1 + reps / 30)) tracks strength per exercise.

The streak counts days in a row with at least one workout that passed the data checks.
Rest days in the user's plan keep the streak alive without adding to it.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd

from .data import generator as G
from .data import store

MUSCLES = ["Chest", "Shoulders", "Triceps", "Back", "Biceps", "Core", "Quads", "Hamstrings", "Glutes", "Calves"]
MUSCLE_GROUP = {"Chest": "Upper", "Shoulders": "Upper", "Triceps": "Upper", "Back": "Upper", "Biceps": "Upper",
                "Core": "Core", "Quads": "Lower", "Hamstrings": "Lower", "Glutes": "Lower", "Calves": "Lower"}

# exercise -> (primary muscles, secondary muscles)
EXERCISE_MUSCLES: dict[str, tuple[list[str], list[str]]] = {
    "Bench Press": (["Chest"], ["Triceps", "Shoulders"]),
    "Overhead Press": (["Shoulders"], ["Triceps"]),
    "Tricep Dips": (["Triceps"], ["Chest"]),
    "Incline Dumbbell Press": (["Chest"], ["Shoulders", "Triceps"]),
    "Lateral Raise": (["Shoulders"], []),
    "Push-ups": (["Chest"], ["Triceps", "Shoulders", "Core"]),
    "Deadlift": (["Back", "Hamstrings", "Glutes"], ["Core"]),
    "Pull-ups": (["Back"], ["Biceps"]),
    "Barbell Row": (["Back"], ["Biceps"]),
    "Bicep Curl": (["Biceps"], []),
    "Lat Pulldown": (["Back"], ["Biceps"]),
    "Face Pull": (["Shoulders"], ["Back"]),
    "Squat": (["Quads", "Glutes"], ["Hamstrings", "Core"]),
    "Lunges": (["Quads", "Glutes"], ["Hamstrings"]),
    "Leg Press": (["Quads"], ["Glutes"]),
    "Calf Raise": (["Calves"], []),
    "Romanian Deadlift": (["Hamstrings"], ["Glutes", "Back"]),
    "Leg Curl": (["Hamstrings"], []),
    "Burpees": (["Chest", "Quads"], ["Shoulders", "Core"]),
    "Kettlebell Swing": (["Glutes", "Hamstrings"], ["Core", "Back"]),
    "Mountain Climbers": (["Core"], ["Shoulders"]),
    "Box Jumps": (["Quads", "Calves"], ["Glutes"]),
    "Jump Rope": (["Calves"], []),
    "Plank": (["Core"], []),
    "Battle Ropes": (["Shoulders"], ["Core"]),
    "Sun Salutation": ([], ["Core", "Shoulders"]),
    "Downward Dog": ([], ["Shoulders", "Hamstrings", "Calves"]),
    "Warrior Pose": ([], ["Quads", "Glutes"]),
    "Pigeon Pose": ([], ["Glutes"]),
    "Running": ([], ["Quads", "Calves", "Hamstrings", "Glutes"]),
    "Cycling": ([], ["Quads", "Glutes", "Calves"]),
    "Walking": ([], ["Calves"]),
    "Swimming": ([], ["Back", "Shoulders", "Core"]),
    # Offered when logging strength; the mining models were trained without them.
    "Chest Fly": (["Chest"], ["Shoulders"]),
    "Arnold Press": (["Shoulders"], ["Triceps"]),
    "Tricep Pushdown": (["Triceps"], []),
    "Skull Crusher": (["Triceps"], []),
    "Hammer Curl": (["Biceps"], []),
    "Seated Cable Row": (["Back"], ["Biceps"]),
    "Shrug": (["Back"], []),
    "Leg Extension": (["Quads"], []),
    "Bulgarian Split Squat": (["Quads", "Glutes"], ["Hamstrings"]),
    "Hip Thrust": (["Glutes"], ["Hamstrings"]),
    "Crunches": (["Core"], []),
    "Hanging Leg Raise": (["Core"], []),
}
EXTRA_EXERCISES = sorted(set(EXERCISE_MUSCLES) - set(G.ALL_EXERCISES))
KNOWN_EXERCISES = set(G.ALL_EXERCISES) | set(EXTRA_EXERCISES)
DEFAULT_SETS = 3
SETS_TARGET = (10, 20)  # hard sets per muscle per week, a common hypertrophy range
SECONDARY = 0.5

DDL = ["CREATE TABLE IF NOT EXISTS training_plans (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
       "days TEXT NOT NULL, updated_at TEXT NOT NULL)"]
# Columns added to existing tables after the first release (old databases get them on start-up).
COLUMNS = {"live_exercises": [("sets", "INTEGER"), ("reps", "INTEGER"), ("weight_kg", "DOUBLE PRECISION")],
           "live_workouts": [("plan_day", "TEXT")]}


def ensure_tables(con):
    with store._lock:
        for sql in DDL:
            con.execute(sql)
        for table, cols in COLUMNS.items():
            have = set(store.columns(table, con))
            for name, typ in cols:
                if name not in have:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
        con.commit()


def counts_sets(exercise: str) -> bool:
    """Strength and HIIT moves add sets; cardio and yoga only mark the muscle as trained."""
    primary, _ = EXERCISE_MUSCLES.get(exercise, ([], []))
    return bool(primary)


# ----------------------------------------------------------------------------- weekly plans

def _day(label, activity="Strength", focus=(), exercises=()):
    return {"label": label, "activity": activity, "focus": list(focus), "exercises": list(exercises)}


REST = _day("Rest", "Rest")
_PUSH = _day("Push", focus=["Chest", "Shoulders", "Triceps"],
             exercises=["Bench Press", "Overhead Press", "Incline Dumbbell Press", "Lateral Raise", "Tricep Dips"])
_PULL = _day("Pull", focus=["Back", "Biceps"],
             exercises=["Deadlift", "Pull-ups", "Barbell Row", "Face Pull", "Bicep Curl"])
_LEGS = _day("Legs", focus=["Quads", "Hamstrings", "Glutes", "Calves"],
             exercises=["Squat", "Romanian Deadlift", "Leg Press", "Lunges", "Calf Raise"])
_UPPER = _day("Upper", focus=["Chest", "Back", "Shoulders", "Biceps", "Triceps"],
              exercises=["Bench Press", "Barbell Row", "Overhead Press", "Lat Pulldown", "Bicep Curl", "Tricep Pushdown"])
_LOWER = _day("Lower", focus=["Quads", "Hamstrings", "Glutes", "Calves", "Core"],
              exercises=["Squat", "Romanian Deadlift", "Leg Press", "Leg Curl", "Calf Raise", "Plank"])
_FULL = _day("Full Body", focus=["Chest", "Back", "Quads", "Hamstrings", "Shoulders", "Core"],
             exercises=["Squat", "Bench Press", "Barbell Row", "Romanian Deadlift", "Overhead Press", "Plank"])

TEMPLATES = {
    "ppl": {"name": "Push / Pull / Legs", "days": [_PUSH, _PULL, _LEGS, _PUSH, _PULL, _LEGS, REST]},
    "upper_lower": {"name": "Upper / Lower", "days": [_UPPER, _LOWER, REST, _UPPER, _LOWER, REST, REST]},
    "full_body": {"name": "Full body x3", "days": [_FULL, REST, _FULL, REST, _FULL, _day("Walk", "Walk"), REST]},
    "bro": {"name": "Body-part split", "days": [
        _day("Chest", focus=["Chest"], exercises=["Bench Press", "Incline Dumbbell Press", "Chest Fly", "Push-ups"]),
        _day("Back", focus=["Back"], exercises=["Deadlift", "Pull-ups", "Barbell Row", "Seated Cable Row", "Shrug"]),
        _day("Shoulders", focus=["Shoulders"], exercises=["Overhead Press", "Arnold Press", "Lateral Raise", "Face Pull"]),
        _day("Arms", focus=["Biceps", "Triceps"],
             exercises=["Bicep Curl", "Hammer Curl", "Tricep Dips", "Skull Crusher", "Tricep Pushdown"]),
        _day("Legs", focus=["Quads", "Hamstrings", "Glutes", "Calves"],
             exercises=["Squat", "Leg Press", "Leg Extension", "Leg Curl", "Calf Raise"]),
        REST, REST]},
    "arnold": {"name": "Arnold split", "days": [
        _day("Chest & Back", focus=["Chest", "Back"],
             exercises=["Bench Press", "Pull-ups", "Incline Dumbbell Press", "Barbell Row", "Chest Fly"]),
        _day("Shoulders & Arms", focus=["Shoulders", "Biceps", "Triceps"],
             exercises=["Arnold Press", "Lateral Raise", "Bicep Curl", "Skull Crusher", "Hammer Curl"]),
        _LEGS,
        _day("Chest & Back", focus=["Chest", "Back"],
             exercises=["Bench Press", "Pull-ups", "Incline Dumbbell Press", "Barbell Row", "Chest Fly"]),
        _day("Shoulders & Arms", focus=["Shoulders", "Biceps", "Triceps"],
             exercises=["Arnold Press", "Lateral Raise", "Bicep Curl", "Skull Crusher", "Hammer Curl"]),
        _LEGS, REST]},
    "hybrid": {"name": "Hybrid: lift + run", "days": [
        _UPPER, _day("Easy run", "Run"), _LOWER, _day("Yoga", "Yoga"), _FULL, _day("Long run", "Run"), REST]},
}


def templates() -> list[dict]:
    return [{"key": k, "name": t["name"], "days": t["days"]} for k, t in TEMPLATES.items()]


def get_plan(con, user_id: int) -> dict | None:
    r = con.execute("SELECT name, days, updated_at FROM training_plans WHERE user_id=?", (int(user_id),)).fetchone()
    return None if r is None else {"name": r[0], "days": json.loads(r[1]), "updated_at": r[2]}


def save_plan(con, user_id: int, plan: dict) -> dict:
    days = [{"label": d["label"].strip() or ("Rest" if d["activity"] == "Rest" else d["activity"]),
             "activity": d["activity"],
             "focus": [m for m in MUSCLES if m in set(d.get("focus") or [])],
             "exercises": [e for e in dict.fromkeys(d.get("exercises") or []) if e in KNOWN_EXERCISES]}
            for d in plan["days"]]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with store._lock:
        con.execute("INSERT INTO training_plans (user_id, name, days, updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT (user_id) DO UPDATE SET name=excluded.name, days=excluded.days, "
                    "updated_at=excluded.updated_at", (int(user_id), plan["name"].strip(), json.dumps(days), now))
        con.commit()
    return get_plan(con, user_id)


def delete_plan(con, user_id: int):
    con.execute("DELETE FROM training_plans WHERE user_id=?", (int(user_id),))
    con.commit()


def rest_weekdays(plan: dict | None) -> set[int]:
    return {i for i, d in enumerate(plan["days"]) if d["activity"] == "Rest"} if plan else set()


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _counted(con, user_id: int, since: str | None = None) -> pd.DataFrame:
    q = "WHERE user_id=? AND NOT flagged" + (" AND start_time >= ?" if since else "")
    w = store.read("live_workouts", con, q, (int(user_id), since) if since else (int(user_id),))
    w["day"] = w.start_time.str[:10]
    return w


def plan_week(con, user_id: int, today: date) -> dict:
    """This week's plan, day by day, and whether each training day has been done."""
    plan = get_plan(con, user_id)
    start = monday(today)
    w = _counted(con, user_id, start.isoformat())
    week = []
    for i in range(7):
        d = start + timedelta(days=i)
        day = plan["days"][i] if plan else None
        got = w[w.day == d.isoformat()]
        if day and day["activity"] != "Rest":
            match = got[(got.plan_day == day["label"]) | (got.activity == day["activity"])]
        else:
            match = got
        week.append({"date": d.isoformat(), "weekday": i, "day": day, "today": d == today,
                     "done": bool(len(match)) if day is None or day["activity"] != "Rest" else False,
                     "workouts": [int(x) for x in got.workout_id]})
    planned = sum(1 for x in week if x["day"] and x["day"]["activity"] != "Rest")
    done = sum(1 for x in week if x["day"] and x["day"]["activity"] != "Rest" and x["done"])
    return {"plan": plan, "week": week, "planned": planned, "done": done,
            "today": next((x["day"] for x in week if x["today"]), None)}


# ----------------------------------------------------------------------------- streak

def streak_numbers(active: set[str], rest: set[int], today: date) -> tuple[int, int]:
    """(current, longest) runs of active days; planned rest days neither break nor extend a run.
    Today not trained yet doesn't break the current streak: it is still running from yesterday."""
    if not active:
        return 0, 0
    first = date.fromisoformat(min(active))
    current = 0
    d = today if today.isoformat() in active else today - timedelta(days=1)
    while d >= first and (d.isoformat() in active or d.weekday() in rest):
        current += d.isoformat() in active
        d -= timedelta(days=1)
    longest = run = 0
    d = first
    while d <= today:
        if d.isoformat() in active:
            run += 1
        elif d.weekday() not in rest and d != today:
            run = 0
        longest = max(longest, run)
        d += timedelta(days=1)
    return current, max(longest, current)


def streak(con, user_id: int, today: date) -> dict:
    plan = get_plan(con, user_id)
    rest = rest_weekdays(plan)
    w = _counted(con, user_id)
    w = w[w.day <= today.isoformat()]
    by_day = w.groupby("day").agg(workouts=("workout_id", "size"), minutes=("duration_min", "sum"))
    active = set(by_day.index)
    current, longest = streak_numbers(active, rest, today)
    start = monday(today)
    week = []
    for i in range(7):
        d = start + timedelta(days=i)
        k = d.isoformat()
        status = ("done" if k in active else "rest" if i in rest else "today" if d == today
                  else "upcoming" if d > today else "missed")
        week.append({"date": k, "status": status})
    since = (today - timedelta(days=400)).isoformat()
    return {
        "current": current, "longest": longest, "today_done": today.isoformat() in active,
        "at_risk": current > 0 and today.isoformat() not in active and today.weekday() not in rest,
        "rest_weekdays": sorted(rest), "week": week,
        "this_week_sessions": int(w[w.day >= start.isoformat()].day.nunique()),
        "weekly_goal": 7 - len(rest) if plan else None,
        "active_days_total": len(active),
        "days": [{"date": k, "workouts": int(r.workouts), "minutes": float(r.minutes)}
                 for k, r in by_day.iterrows() if k >= since],
    }


# ----------------------------------------------------------------------------- muscle progress

def _sets_table(con, user_id: int, since: str) -> pd.DataFrame:
    """One row per (workout, exercise, muscle) with weighted sets and volume."""
    w = _counted(con, user_id, since)
    if w.empty:
        return pd.DataFrame(columns=["workout_id", "day", "exercise", "muscle", "role", "sets", "volume", "e1rm",
                                     "weight_kg", "reps"])
    ids = [int(i) for i in w.workout_id]
    ex = store.read("live_exercises", con, f"WHERE workout_id IN ({','.join('?' * len(ids))})", ids)
    ex = ex.merge(w[["workout_id", "day"]], on="workout_id")
    rows = []
    for r in ex.itertuples():
        primary, secondary = EXERCISE_MUSCLES.get(r.exercise, ([], []))
        sets = (int(r.sets) if pd.notna(r.sets) and r.sets else DEFAULT_SETS) if counts_sets(r.exercise) else 0
        kg = float(r.weight_kg) if pd.notna(r.weight_kg) and r.weight_kg else None
        reps = int(r.reps) if pd.notna(r.reps) and r.reps else None
        e1rm = kg * (1 + reps / 30) if kg and reps and reps <= 30 else None
        for role, muscles, k in (("primary", primary, 1.0), ("secondary", secondary, SECONDARY)):
            for m in muscles:
                rows.append({"workout_id": r.workout_id, "day": r.day, "exercise": r.exercise, "muscle": m,
                             "role": role, "sets": sets * k, "volume": (sets * reps * kg * k) if kg and reps else 0.0,
                             "e1rm": e1rm, "weight_kg": kg, "reps": reps})
    return pd.DataFrame(rows, columns=["workout_id", "day", "exercise", "muscle", "role", "sets", "volume", "e1rm",
                                       "weight_kg", "reps"])


def muscle_sets_per_week(con, user_id: int, today: date, weeks: int = 4) -> dict[str, float]:
    """Average weighted sets per week for each muscle over the last `weeks` weeks (for comparing)."""
    start = monday(today) - timedelta(weeks=weeks - 1)
    t = _sets_table(con, user_id, start.isoformat())
    t = t[t.day <= today.isoformat()]
    s = t.groupby("muscle").sets.sum() / weeks
    return {m: round(float(s.get(m, 0.0)), 1) for m in MUSCLES}


def muscles(con, user_id: int, today: date, weeks: int = 8) -> dict:
    start = monday(today) - timedelta(weeks=weeks - 1)
    week_keys = [(start + timedelta(weeks=i)).isoformat() for i in range(weeks)]
    t = _sets_table(con, user_id, start.isoformat())
    t = t[t.day <= today.isoformat()]
    t["week"] = [monday(date.fromisoformat(d)).isoformat() for d in t.day]
    # the last time each muscle was worked, looking back further than the chart
    older = _sets_table(con, user_id, (today - timedelta(days=120)).isoformat())
    older = older[older.day <= today.isoformat()]
    last = older.groupby("muscle").day.max()
    out = []
    for m in MUSCLES:
        g = t[t.muscle == m]
        per_week = g.groupby("week").agg(sets=("sets", "sum"), volume=("volume", "sum"),
                                         sessions=("workout_id", "nunique"))
        weekly = [{"week": k, "sets": round(float(per_week.sets.get(k, 0.0)), 1),
                   "volume_kg": round(float(per_week.volume.get(k, 0.0))),
                   "sessions": int(per_week.sessions.get(k, 0))} for k in week_keys]
        this_week = weekly[-1]["sets"]
        recent = sum(x["sets"] for x in weekly[-4:])
        before = sum(x["sets"] for x in weekly[-8:-4])
        lt = last.get(m)
        days_since = None if lt is None else (today - date.fromisoformat(lt)).days
        status = ("not_trained" if days_since is None else "recovering" if days_since <= 1
                  else "overdue" if days_since > 7 else "ready")
        lo, hi = SETS_TARGET
        exercises = []
        for e, ge in g[g.role == "primary"].groupby("exercise"):
            lifts = ge.dropna(subset=["e1rm"]).sort_values("day")
            hist = lifts.groupby("day").agg(e1rm=("e1rm", "max"), weight_kg=("weight_kg", "max"), reps=("reps", "max"))
            history = [{"date": d, "e1rm": round(float(r.e1rm), 1), "weight_kg": float(r.weight_kg), "reps": int(r.reps)}
                       for d, r in hist.iterrows()]
            first, latest = (history[0]["e1rm"], history[-1]["e1rm"]) if history else (None, None)
            exercises.append({"exercise": e, "sessions": int(ge.workout_id.nunique()),
                              "best_e1rm": max((h["e1rm"] for h in history), default=None),
                              "first_e1rm": first, "latest_e1rm": latest,
                              "change_pct": round((latest - first) / first, 3) if first else None,
                              "history": history})
        exercises.sort(key=lambda x: -x["sessions"])
        out.append({
            "muscle": m, "group": MUSCLE_GROUP[m], "sets_this_week": this_week,
            "sets_avg": round(sum(x["sets"] for x in weekly) / weeks, 1),
            "target_low": lo, "target_high": hi,
            "volume_status": "low" if this_week < lo else "high" if this_week > hi else "on_target",
            "trend_pct": round((recent - before) / before, 3) if before else None,
            "last_trained": lt, "days_since": days_since, "status": status,
            "weekly": weekly, "exercises": exercises,
        })
    return {"weeks": week_keys, "muscles": out, "total_sets_this_week": round(sum(m["sets_this_week"] for m in out), 1),
            "sets_target": list(SETS_TARGET)}


def parse_today(s: str | None) -> date:
    """The client's local date, so "today" matches the user's calendar, not the server's time zone."""
    if s:
        try:
            d = date.fromisoformat(s[:10])
            if abs((d - date.today()).days) <= 2:
                return d
        except ValueError:
            pass
    return date.today()

