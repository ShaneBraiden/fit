"""Synthetic smart-fitness dataset with planted, recoverable structure.

The generator behaves like the back end of a Strava/Fitbit style app: users with
profiles, workouts with summaries, exercise baskets, and per-workout HR + GPS
streams. Every pattern the mining is meant to find is *planted* here and
recorded in ground-truth tables (gt_*) and in `planted`, which only the
evaluation code reads:

  U1  missing values, duplicate re-syncs, mixed units, messy activity labels
  U3  exercise session templates  -> co-occurrence rules
  U4  latent fitness score        -> assessed fitness level (noisy, 75% labelled)
  U5  five personas               -> activity mix
  U6  sensor faults + spoofing    -> anomalies
  U7  weekly schedules            -> sequential patterns; popular routes and run phases
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from scipy.signal import lfilter

from .. import config as C
from . import geo

DT = C.STREAM_INTERVAL_S

FIRST_M = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Kabir", "Ishaan", "Rahul", "Siddharth", "Nikhil",
           "Karan", "Varun", "Aman", "Pranav", "Yash", "Dev", "Omkar", "Tejas", "Harsh", "Manish",
           "Farhan", "Imran", "Joel", "Neil", "Ritesh", "Sameer", "Tanmay", "Vikram", "Zaid", "Akash"]
FIRST_F = ["Ananya", "Diya", "Saanvi", "Aanya", "Isha", "Priya", "Kavya", "Meera", "Riya", "Sneha",
           "Pooja", "Neha", "Tanvi", "Shreya", "Aditi", "Nisha", "Sara", "Zoya", "Fatima", "Rhea",
           "Ira", "Mitali", "Gauri", "Komal", "Leela", "Naina", "Radhika", "Sana", "Trisha", "Vaishnavi"]
LAST = ["Sharma", "Patel", "Iyer", "Nair", "Desai", "Kulkarni", "Joshi", "Mehta", "Shah", "Rao",
        "Pillai", "Fernandes", "D'Souza", "Khan", "Sheikh", "Gupta", "Verma", "Reddy", "Menon", "Bhat",
        "Chavan", "Patil", "Pawar", "Jadhav", "Gaikwad", "Kapoor", "Malhotra", "Bose", "Das", "Sinha"]

DEVICES = ["PulseWatch 3", "FitBand Lite", "StrideBand US", "Phone GPS"]
DEVICE_P = [0.35, 0.30, 0.15, 0.20]
IMPERIAL_DEVICE = "StrideBand US"

PERSONA_MIX = [0.22, 0.24, 0.16, 0.18, 0.20]
PERSONA_FIT = {"Endurance Runner": 0.45, "Gym Strength": 0.2, "HIIT Enthusiast": 0.3,
               "Yoga & Mobility": -0.1, "Casual Walker": -0.75}
PERSONA_AGE = {"Endurance Runner": (34, 9), "Gym Strength": (30, 7), "HIIT Enthusiast": (29, 6),
               "Yoga & Mobility": (38, 11), "Casual Walker": (48, 12)}
PERSONA_MALE = {"Endurance Runner": 0.55, "Gym Strength": 0.7, "HIIT Enthusiast": 0.5,
                "Yoga & Mobility": 0.3, "Casual Walker": 0.5}

# Weekly schedule slots (weekday 0=Mon, session type, probability). The order of the
# slots inside a week is what sequential pattern mining should recover.
SCHEDULE = {
    "Endurance Runner": [(0, "EasyRun", .85), (1, "Cycle", .2), (2, "IntervalRun", .8), (3, "Legs", .35),
                         (3, "TempoRun", .3), (4, "Yoga", .2), (5, "LongRun", .5), (6, "LongRun", .4)],
    "Gym Strength": [(0, "Push", .9), (1, "Pull", .85), (2, "Legs", .85), (3, "Push", .5), (4, "Pull", .45),
                     (5, "Legs", .4), (5, "HIIT", .15), (6, "EasyRun", .25)],
    "HIIT Enthusiast": [(0, "HIIT", .85), (1, "EasyRun", .5), (2, "HIIT", .8), (3, "Push", .3), (4, "HIIT", .7),
                        (5, "Legs", .3), (6, "Cycle", .3)],
    "Yoga & Mobility": [(0, "Yoga", .85), (1, "Walk", .5), (2, "Yoga", .75), (3, "Swim", .3), (4, "Yoga", .6),
                        (5, "Walk", .5), (6, "Yoga", .4)],
    "Casual Walker": [(0, "Walk", .6), (1, "Walk", .3), (2, "Walk", .55), (3, "Cycle", .25), (4, "Walk", .4),
                      (5, "Walk", .5), (6, "Yoga", .3), (6, "Swim", .2)],
}
SESSION_ACTIVITY = {"EasyRun": "Run", "IntervalRun": "Run", "TempoRun": "Run", "LongRun": "Run",
                    "Push": "Strength", "Pull": "Strength", "Legs": "Strength", "HIIT": "HIIT",
                    "Yoga": "Yoga", "Walk": "Walk", "Cycle": "Cycle", "Swim": "Swim"}
SESSION_TITLES = {
    "EasyRun": ["Easy Run", "Morning Run", "Recovery Run"], "IntervalRun": ["Intervals", "Track Intervals", "Speed Work"],
    "TempoRun": ["Tempo Run", "Threshold Run"], "LongRun": ["Long Run", "Sunday Long Run", "LSD Run"],
    "Push": ["Push Day", "Chest & Shoulders", "Push"], "Pull": ["Pull Day", "Back & Biceps", "Pull"],
    "Legs": ["Leg Day", "Legs", "Lower Body"], "HIIT": ["HIIT Circuit", "Tabata", "Bootcamp"],
    "Yoga": ["Yoga", "Vinyasa Flow", "Morning Yoga"], "Walk": ["Evening Walk", "Morning Walk", "Walk"],
    "Cycle": ["Ride", "Morning Ride", "Cycling"], "Swim": ["Swim", "Pool Laps"],
}
DURATION = {"EasyRun": (30, 50), "IntervalRun": (40, 55), "TempoRun": (35, 45), "LongRun": (65, 100),
            "Push": (45, 70), "Pull": (45, 70), "Legs": (45, 70), "HIIT": (25, 40), "Yoga": (40, 70),
            "Walk": (30, 70), "Cycle": (45, 90), "Swim": (30, 50)}

# Exercise templates: (exercise, probability it is done in that session type).
TEMPLATES = {
    "Push": [("Bench Press", .95), ("Overhead Press", .85), ("Tricep Dips", .8), ("Incline Dumbbell Press", .5),
             ("Lateral Raise", .5), ("Push-ups", .4)],
    "Pull": [("Deadlift", .9), ("Pull-ups", .85), ("Barbell Row", .85), ("Bicep Curl", .75), ("Lat Pulldown", .45),
             ("Face Pull", .4)],
    "Legs": [("Squat", .95), ("Lunges", .8), ("Leg Press", .8), ("Calf Raise", .6), ("Romanian Deadlift", .45)],
    "HIIT": [("Burpees", .9), ("Kettlebell Swing", .8), ("Mountain Climbers", .75), ("Box Jumps", .7),
             ("Jump Rope", .5), ("Plank", .5), ("Battle Ropes", .35)],
    "Yoga": [("Sun Salutation", .95), ("Downward Dog", .9), ("Warrior Pose", .85), ("Meditation", .8),
             ("Pigeon Pose", .5)],
}
CARDIO_ITEM = {"Run": "Running", "Cycle": "Cycling", "Walk": "Walking", "Swim": "Swimming"}
ALL_EXERCISES = sorted({e for t in TEMPLATES.values() for e, _ in t}
                       | set(CARDIO_ITEM.values()) | {"Stretching", "Foam Rolling", "Leg Curl"})

PLANTED_RULES = [
    (["Bench Press", "Overhead Press"], ["Tricep Dips"]),
    (["Deadlift", "Pull-ups"], ["Barbell Row"]),
    (["Lunges", "Squat"], ["Leg Press"]),
    (["Romanian Deadlift"], ["Leg Curl"]),
    (["Burpees", "Kettlebell Swing"], ["Mountain Climbers"]),
    (["Downward Dog", "Sun Salutation"], ["Warrior Pose"]),
    (["Warrior Pose"], ["Meditation"]),
    (["Foam Rolling", "Running"], ["Stretching"]),
]
PLANTED_SEQUENCES = [["Push", "Pull", "Legs"], ["EasyRun", "IntervalRun", "LongRun"],
                     ["HIIT", "EasyRun", "HIIT"], ["Yoga", "Walk", "Yoga"]]

# Popular routes: ground truth. Lines are run out-and-back, loops are lapped.
POPULAR_ROUTES = [
    {"id": 0, "name": "Marine Drive Promenade", "kind": "line",
     "pts": [(18.9256, 72.8236), (18.9320, 72.8238), (18.9390, 72.8240), (18.9440, 72.8232), (18.9490, 72.8205),
             (18.9530, 72.8160), (18.9545, 72.8135)]},
    {"id": 1, "name": "Shivaji Park Loop", "kind": "loop", "center": (19.0269, 72.8384), "radii": (230, 200)},
    {"id": 2, "name": "Worli Sea Face", "kind": "line",
     "pts": [(19.0080, 72.8152), (19.0120, 72.8155), (19.0160, 72.8162), (19.0200, 72.8170), (19.0235, 72.8180)]},
    {"id": 3, "name": "Bandstand to Carter Road", "kind": "line",
     "pts": [(19.0450, 72.8195), (19.0500, 72.8212), (19.0555, 72.8225), (19.0610, 72.8232), (19.0665, 72.8228)]},
    {"id": 4, "name": "Juhu Beach Stretch", "kind": "line",
     "pts": [(19.0880, 72.8262), (19.0940, 72.8263), (19.1000, 72.8265), (19.1060, 72.8262), (19.1100, 72.8258)]},
    {"id": 5, "name": "Powai Lake Loop", "kind": "loop", "center": (19.1270, 72.9050), "radii": (700, 900)},
    {"id": 6, "name": "Aarey Colony Trail", "kind": "line",
     "pts": [(19.1520, 72.8700), (19.1560, 72.8740), (19.1600, 72.8760), (19.1650, 72.8790), (19.1700, 72.8820)]},
    {"id": 7, "name": "SGNP Forest Trail", "kind": "line",
     "pts": [(19.2250, 72.8650), (19.2290, 72.8700), (19.2320, 72.8760), (19.2360, 72.8800), (19.2400, 72.8850)]},
]

# Phase name -> (relative speed, fraction of heart-rate reserve)
PHASES = {"warmup": (0.78, 0.45), "steady": (1.0, 0.62), "long": (1.0, 0.60), "tempo": (1.08, 0.78),
          "interval_fast": (1.28, 0.90), "interval_recovery": (0.72, 0.62), "cooldown": (0.72, 0.40),
          "stop": (0.0, 0.50)}
GENTLE_HRR = {"Walk": 0.35, "Cycle": 0.65}

WORKOUT_FAULTS = {"hr_spike": .008, "hr_flatline": .006, "hr_dropout": .006, "gps_teleport": .012,
                  "car_speed": .008, "gps_replay": .006, "calorie_mismatch": .006}
N_IMPLAUSIBLE_PROFILES = 12
N_DUPLICATE_ACCOUNTS = 10
P_RESYNC_DUPLICATE = 0.01
P_MISSING = {"avg_hr": 0.04, "calories": 0.03, "weight": 0.02}
P_MESSY_LABEL = 0.12
MESSY_LABELS = {"Run": ["run", "RUN", "Running", "running", "Jog"], "Cycle": ["cycle", "Cycling", "BIKE", "Bike"],
                "Walk": ["walk", "Walking", "WALK"], "Swim": ["swim", "Swimming"],
                "Strength": ["strength", "Weights", "WEIGHTS", "Strength Training"],
                "HIIT": ["hiit", "Hiit", "Circuit"], "Yoga": ["yoga", "YOGA", "Yoga Flow"]}


def history_start() -> date:
    return C.HISTORY_END - timedelta(days=7 * C.WEEKS - 1)


@dataclass
class Dataset:
    users: pd.DataFrame
    workouts: pd.DataFrame
    exercises: pd.DataFrame
    streams: dict  # workout_id -> {"hr": int array, "lat": array|None, "lon": array|None}
    gt_users: pd.DataFrame
    gt_workouts: pd.DataFrame
    gt_segments: pd.DataFrame
    gt_values: pd.DataFrame
    planted: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- routes

def _route_xy(route: dict) -> tuple[np.ndarray, str]:
    if route["kind"] == "loop":
        cx, cy = geo.to_xy(*route["center"])
        rx, ry = route["radii"]
        th = np.linspace(0, 2 * np.pi, 49)[:-1]
        return np.column_stack([cx + rx * np.cos(th), cy + ry * np.sin(th)]), "loop"
    lat, lon = np.array(route["pts"]).T
    x, y = geo.to_xy(lat, lon)
    return np.column_stack([x, y]), "line"


def _personal_loop(rng, home_xy, radius) -> np.ndarray:
    cx, cy = home_xy + rng.normal(0, 250, 2)
    th = np.linspace(0, 2 * np.pi, 49)[:-1]
    k, phase = rng.integers(2, 4), rng.uniform(0, 2 * np.pi)
    r = radius * (1 + 0.22 * np.sin(k * th + phase))
    return np.column_stack([cx + r * np.cos(th), cy + 0.8 * r * np.sin(th)])


def _traversal(verts: np.ndarray, kind: str, times: int, rng) -> np.ndarray:
    if kind == "loop":
        start = rng.integers(len(verts))
        one = np.vstack([np.roll(verts, -start, axis=0), np.roll(verts, -start, axis=0)[:1]])
        return np.vstack([one] + [one[1:]] * (times - 1))
    if rng.random() < 0.5:
        verts = verts[::-1]
    out_back = np.vstack([verts, verts[-2::-1]])
    return np.vstack([out_back] + [out_back[1:]] * (times - 1))


def _poly_len(p: np.ndarray) -> float:
    return float(np.hypot(*np.diff(p, axis=0).T).sum())


# ----------------------------------------------------------------------------- phases

def _phase_plan(stype: str, n: int, rng) -> list[tuple[int, int, str]]:
    """Split n samples into labelled phases: warm-up, main body, cool-down."""
    wu = max(2, int(round(n * rng.uniform(0.10, 0.14))))
    cd = max(2, int(round(n * rng.uniform(0.08, 0.12))))
    lo, hi = wu, n - cd
    plan = [(0, wu, "warmup")]
    if stype == "IntervalRun":
        i, fast = lo, True
        while i < hi:
            j = min(hi, i + int(rng.integers(8, 13) if fast else rng.integers(6, 9)))
            if hi - j < 4:
                j = hi
            plan.append((i, j, "interval_fast" if fast else "interval_recovery"))
            i, fast = j, not fast
    elif stype == "TempoRun":
        plan.append((lo, hi, "tempo"))
    else:
        body = "long" if stype == "LongRun" else "steady"
        cuts = sorted(rng.choice(np.arange(lo + 6, hi - 6), size=int(rng.integers(0, 3)), replace=False)) \
            if hi - lo > 20 else []
        i = lo
        for c in cuts:
            if c - i < 4:
                continue
            plan.append((i, c, body))
            plan.append((c, c + int(rng.integers(2, 5)), "stop"))
            i = plan[-1][1]
        plan.append((i, hi, body))
    plan.append((hi, n, "cooldown"))
    return plan


def _plan_arrays(plan, n, activity):
    rel, hrr = np.empty(n), np.empty(n)
    for a, b, ph in plan:
        r, h = PHASES[ph]
        if activity in GENTLE_HRR and ph not in ("stop",):
            r = 1.0 if ph in ("steady", "long") else (0.85 if ph != "stop" else 0.0)
            h = GENTLE_HRR[activity] * (0.75 if ph in ("warmup", "cooldown") else 1.0)
        rel[a:b], hrr[a:b] = r, h
    return rel, hrr


def _hr_series(rng, hrr: np.ndarray, rest: float, hrmax: float) -> np.ndarray:
    # First-order lag: the heart rate moves 30% of the way to its target each sample.
    target = rest + hrr * (hrmax - rest)
    out, _ = lfilter([0.3], [1, -0.7], target, zi=[0.7 * (rest + 10)])
    return np.clip(np.round(out + rng.normal(0, 1.5, len(out))), 35, 215).astype(int)


def _gym_hrr(rng, stype: str, n: int) -> np.ndarray:
    """Heart-rate reserve pattern for sessions without GPS."""
    h = np.empty(n)
    i, work = 0, True
    while i < n:
        if stype == "HIIT":
            ln, val = (int(rng.integers(2, 4)), 0.88) if work else (2, 0.5)
        elif stype == "Yoga":
            ln, val = int(rng.integers(6, 12)), rng.uniform(0.18, 0.32)
        elif stype == "Swim":
            ln, val = int(rng.integers(6, 10)), 0.65 if work else 0.45
        else:
            ln, val = (3, 0.55) if work else (int(rng.integers(4, 7)), 0.3)
        h[i:i + ln] = val
        i, work = i + ln, not work
    return h


# ----------------------------------------------------------------------------- generator

class _Gen:
    def __init__(self, seed: int, n_users: int):
        self.rng = np.random.default_rng(seed)
        self.n_users = n_users
        self.routes = [_route_xy(r) for r in POPULAR_ROUTES]
        self.route_centres = np.array([v.mean(0) for v, _ in self.routes])
        self.loops: dict[int, np.ndarray] = {}
        self.ride_loops: dict[int, np.ndarray] = {}
        self.rows: list[dict] = []
        self.ex: dict[int, list[str]] = {}
        self.streams: dict[int, dict] = {}
        self.gt_w: dict[int, dict] = {}
        self.gt_seg: list[tuple] = []

    # ---- users
    def users(self) -> pd.DataFrame:
        rng, n = self.rng, self.n_users
        personas = rng.choice(C.PERSONAS, size=n, p=PERSONA_MIX)
        zones = rng.choice(C.ZONES, size=n, p=[.15, .25, .25, .2, .15])
        rows = []
        for i in range(n):
            p = personas[i]
            male = rng.random() < PERSONA_MALE[p]
            age = int(np.clip(rng.normal(*PERSONA_AGE[p]), 18, 75))
            f = PERSONA_FIT[p] - 0.025 * (age - 35) + rng.normal(0, 0.8)
            height = rng.normal(174, 7) if male else rng.normal(161, 6)
            bmi = np.clip(22.5 - 0.8 * f + rng.normal(0, 2.4), 16.5, 38)
            hx, hy = geo.to_xy(*geo.ZONE_CENTERS[zones[i]])
            home = np.array([hx, hy]) + rng.normal(0, 900, 2)
            self.loops[i + 1] = _personal_loop(rng, home, rng.uniform(350, 900))
            self.ride_loops[i + 1] = _personal_loop(rng, home, rng.uniform(1500, 2600))
            rows.append(dict(
                user_id=i + 1, persona=str(p), gender="M" if male else "F", age=age, fitness=f,
                name=f"{rng.choice(FIRST_M if male else FIRST_F)} {rng.choice(LAST)}",
                height_cm=round(float(height), 1), weight_kg=round(float(bmi * (height / 100) ** 2), 1),
                resting_hr=int(np.clip(round(74 - 7 * f + rng.normal(0, 3)), 38, 100)),
                vo2max=round(float(np.clip(40 + 7 * f - 0.2 * (age - 35) - (4 if not male else 0)
                                           + rng.normal(0, 2.5), 15, 85)), 1),
                hrmax=float(208 - 0.7 * age + rng.normal(0, 4)),
                device=str(rng.choice(DEVICES, p=DEVICE_P)), home_zone=str(zones[i]), home_x=home[0], home_y=home[1],
                pace=float(np.clip(6.6 - 0.65 * f + 0.02 * (age - 35) + rng.normal(0, .25), 3.3, 9.0)),
                walk_kmh=float(np.clip(5.0 + 0.3 * f + rng.normal(0, .3), 3.5, 6.8)),
                ride_kmh=float(np.clip(21 + 2.5 * f + rng.normal(0, 1.5), 13, 34)),
                morning=rng.random() < 0.6,
                signup=history_start() - timedelta(days=int(rng.integers(30, 700))),
            ))
        df = pd.DataFrame(rows)
        q = np.quantile(df.fitness, [0.40, 0.75, 0.93])
        df["level"] = [C.LEVELS[int(np.searchsorted(q, v))] for v in df.fitness]
        return df

    # ---- one workout
    def _route_for(self, u, activity):
        rng = self.rng
        p_popular = {"Run": .55, "Walk": .45, "Cycle": .4}[activity]
        if rng.random() < p_popular:
            d = np.hypot(*(self.route_centres - [u["home_x"], u["home_y"]]).T)
            near = np.argsort(d)[:2]
            rid = int(near[0] if rng.random() < 0.65 else near[1])
            verts, kind = self.routes[rid]
            return rid, verts, kind
        loops = self.ride_loops if activity == "Cycle" else self.loops
        return 100 + int(u["user_id"]), loops[int(u["user_id"])], "loop"

    def workout(self, u, stype: str, start: datetime) -> int:
        rng = self.rng
        k = len(self.rows)
        activity = SESSION_ACTIVITY[stype]
        lo, hi = DURATION[stype]
        minutes = rng.uniform(lo, hi) * float(np.clip(1 + 0.08 * u["fitness"], 0.85, 1.2))
        n = int(minutes * 60 / DT)
        lat = lon = None
        distance = None
        route_id = -1
        if activity in C.GPS_ACTIVITIES:
            speed = {"Run": 1000 / (u["pace"] * 60), "Walk": u["walk_kmh"] / 3.6,
                     "Cycle": u["ride_kmh"] / 3.6}[activity] * rng.normal(1, 0.03)
            if stype == "LongRun":
                speed *= 0.93
            route_id, verts, kind = self._route_for(u, activity)
            one = _poly_len(_traversal(verts, kind, 1, rng))
            times = max(1, int(round(speed * minutes * 60 / one)))
            path = _traversal(verts, kind, times, rng)
            length = _poly_len(path)
            plan = _phase_plan(stype if activity == "Run" else activity, n, rng)
            rel, _ = _plan_arrays(plan, n, activity)
            n = max(30, int(round(length / (speed * rel.mean() * DT))))
            plan = _phase_plan(stype if activity == "Run" else activity, n, rng)
            rel, hrr = _plan_arrays(plan, n, activity)
            noise = np.convolve(rng.normal(0, 0.035, n + 2), np.ones(3) / 3, mode="valid")
            v = speed * rel * (1 + noise)
            v *= length / (v.sum() * DT)
            s = np.concatenate([[0.0], np.cumsum(v[:-1] * DT)])
            cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(path, axis=0).T))])
            x = np.interp(s, cum, path[:, 0]) + rng.normal(0, 4, n)
            y = np.interp(s, cum, path[:, 1]) + rng.normal(0, 4, n)
            lat, lon = geo.to_latlon(x, y)
            distance = length / 1000 * rng.normal(1, 0.01)
            for a, b, ph in plan:
                self.gt_seg.append((k, a, b, ph))
            avg_kmh = distance / (n * DT / 3600)
            met = avg_kmh if activity == "Run" else C.MET[activity]
        else:
            hrr = _gym_hrr(rng, stype, n)
            met = C.MET[activity] * float(np.clip(1 + 0.08 * u["fitness"], 0.85, 1.2))
            if activity == "Swim":
                distance = 2.2 * minutes / 60 * float(np.clip(1 + 0.15 * u["fitness"], 0.6, 1.5))
        hr = _hr_series(rng, hrr, u["resting_hr"], u["hrmax"])
        hours = n * DT / 3600
        self.rows.append(dict(
            k=k, user_id=u["user_id"], activity=activity, title=rng.choice(SESSION_TITLES[stype]),
            start_time=start, duration_min=round(n * DT / 60, 2),
            distance_km=None if distance is None else round(float(distance), 3),
            avg_hr=round(float(hr.mean()), 1), max_hr=int(hr.max()),
            calories=round(float(met * u["weight_kg"] * hours * rng.normal(1, 0.06)), 1),
        ))
        self.streams[k] = {"hr": hr, "lat": lat, "lon": lon}
        self.ex[k] = self._basket(stype, activity)
        self.gt_w[k] = dict(session_type=stype, route_id=route_id, fault_type=None, duplicate_of=None)
        return k

    def _basket(self, stype, activity) -> list[str]:
        rng = self.rng
        items: list[str] = []
        if stype in TEMPLATES:
            items = [e for e, p in TEMPLATES[stype] if rng.random() < p]
            if stype == "Legs":
                rdl = "Romanian Deadlift" in items
                if rng.random() < (0.75 if rdl else 0.15):
                    items.append("Leg Curl")
            if stype in ("Push", "Pull", "Legs"):
                items += [e for e, p in (("Plank", .25), ("Stretching", .3), ("Foam Rolling", .15)) if rng.random() < p]
        else:
            items = [CARDIO_ITEM[activity]]
            if activity == "Run":
                fr = rng.random() < 0.35
                if fr:
                    items.append("Foam Rolling")
                if rng.random() < (0.9 if fr else 0.5):
                    items.append("Stretching")
            else:
                items += [e for e, p in (("Stretching", .25), ("Foam Rolling", .1)) if rng.random() < p]
        if rng.random() < 0.08:
            items.append(str(rng.choice(ALL_EXERCISES)))
        return sorted(set(items))

    # ---- schedules
    def schedule(self, users: pd.DataFrame):
        rng = self.rng
        start = history_start()
        for _, u in users.iterrows():
            factor = float(np.clip(1 + 0.15 * u["fitness"], 0.5, 1.4))
            # Real users are not pure types: each one blends in a secondary persona's habits
            # and has personal slot preferences, so the personas overlap in feature space.
            other = str(rng.choice([p for p in C.PERSONAS if p != u["persona"]]))
            mix = rng.uniform(0.0, 0.45)
            slots = [(d, s, p * (1 - mix) * rng.uniform(0.7, 1.15)) for d, s, p in SCHEDULE[u["persona"]]] + \
                    [(d, s, p * mix * rng.uniform(0.7, 1.15)) for d, s, p in SCHEDULE[other]]
            slots.sort(key=lambda x: x[0])
            for w in range(C.WEEKS):
                long_done = False
                per_day: dict[int, int] = {}
                for dow, stype, prob in slots:
                    if stype == "LongRun" and long_done or per_day.get(dow, 0) >= 2:
                        continue
                    if rng.random() >= min(0.97, prob * factor):
                        continue
                    long_done |= stype == "LongRun"
                    day = start + timedelta(days=7 * w + dow)
                    slot = per_day.get(dow, 0)
                    per_day[dow] = slot + 1
                    base_h = (6.5 if u["morning"] else 18.5) + (11 if slot and u["morning"] else -10 if slot else 0)
                    hour = float(np.clip(base_h + rng.normal(0, 0.6), 5, 21.5))
                    self.workout(u, stype, datetime.combine(day, datetime.min.time()) + timedelta(seconds=int(hour * 3600)))

    # ---- faults (U6)
    def faults(self, users: pd.DataFrame):
        rng = self.rng
        gps = [r["k"] for r in self.rows if self.streams[r["k"]]["lat"] is not None]
        all_k = [r["k"] for r in self.rows]
        taken: set[int] = set()

        def pick(pool, rate, cond=lambda k: True):
            cand = [k for k in pool if k not in taken and cond(k)]
            m = int(round(rate * len(all_k)))
            chosen = list(rng.choice(cand, size=min(m, len(cand)), replace=False))
            taken.update(chosen)
            return chosen

        by_k = {r["k"]: r for r in self.rows}
        for k in pick(all_k, WORKOUT_FAULTS["hr_spike"]):
            hr = self.streams[k]["hr"]
            idx = rng.choice(len(hr), size=min(len(hr), int(rng.integers(3, 9))), replace=False)
            hr[idx] = rng.integers(225, 256, len(idx))
            self._fault(k, "hr_spike")
        for k in pick(all_k, WORKOUT_FAULTS["hr_flatline"]):
            hr = self.streams[k]["hr"]
            i0 = int(len(hr) * rng.uniform(0.2, 0.4))
            hr[i0:] = hr[i0]
            self._fault(k, "hr_flatline")
        for k in pick(all_k, WORKOUT_FAULTS["hr_dropout"]):
            hr = self.streams[k]["hr"]
            for _ in range(int(rng.integers(2, 5))):
                a = int(rng.integers(0, len(hr) - 5))
                hr[a:a + int(len(hr) * rng.uniform(0.1, 0.2))] = 0
            self._fault(k, "hr_dropout")
        for k in pick(gps, WORKOUT_FAULTS["gps_teleport"]):
            st = self.streams[k]
            x, y = geo.to_xy(st["lat"], st["lon"])
            for _ in range(int(rng.integers(1, 3))):
                i = int(rng.integers(5, len(x) - 5))
                ang, dist = rng.uniform(0, 2 * np.pi), rng.uniform(3000, 15000)
                j = i + int(rng.integers(1, 3))
                x[i:j] += dist * np.cos(ang)
                y[i:j] += dist * np.sin(ang)
            st["lat"], st["lon"] = geo.to_latlon(x, y)
            by_k[k]["distance_km"] = round(_poly_len(np.column_stack([x, y])) / 1000, 3)
            self._fault(k, "gps_teleport")
        for k in pick(gps, WORKOUT_FAULTS["car_speed"], lambda k: by_k[k]["activity"] in ("Run", "Walk")):
            self._car_speed(k, users.set_index("user_id").loc[by_k[k]["user_id"]])
        for k in pick(gps, WORKOUT_FAULTS["gps_replay"]):
            # Re-upload of someone else's earlier activity file.
            cands = [g for g in gps if by_k[g]["user_id"] != by_k[k]["user_id"] and g not in taken
                     and by_k[g]["activity"] == by_k[k]["activity"] and by_k[g]["start_time"] < by_k[k]["start_time"]]
            if not cands:
                taken.discard(k)
                continue
            src = rng.choice(cands)
            self.streams[k] = {key: (None if a is None else a.copy()) for key, a in self.streams[src].items()}
            for col in ("duration_min", "distance_km", "avg_hr", "max_hr", "calories"):
                by_k[k][col] = by_k[src][col]
            self._fault(k, "gps_replay")
        for k in pick(all_k, WORKOUT_FAULTS["calorie_mismatch"]):
            by_k[k]["calories"] = round(by_k[k]["calories"] * (rng.uniform(2.5, 4) if rng.random() < .5
                                                              else rng.uniform(.15, .3)), 1)
            self._fault(k, "calorie_mismatch")
        for k in taken:
            hr = self.streams[k]["hr"]
            if self.gt_w[k]["fault_type"] != "calorie_mismatch":
                by_k[k]["avg_hr"], by_k[k]["max_hr"] = round(float(hr.mean()), 1), int(hr.max())

    def _fault(self, k, kind):
        self.gt_w[k]["fault_type"] = kind

    def _car_speed(self, k, u):
        rng = self.rng
        st = self.streams[k]
        x, y = geo.to_xy(st["lat"], st["lon"])
        path = np.column_stack([x, y])
        cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(path, axis=0).T))])
        v = rng.uniform(10, 15) * (1 + rng.normal(0, 0.05, 10_000))
        for _ in range(int(rng.integers(1, 3))):
            a = int(rng.integers(5, 40))
            v[a:a + int(rng.integers(2, 5))] = 0
        s = np.concatenate([[0.0], np.cumsum(v * DT)])
        n = int(np.searchsorted(s, cum[-1])) + 1
        s = np.minimum(s[:n], cum[-1])
        st["lat"], st["lon"] = geo.to_latlon(np.interp(s, cum, x), np.interp(s, cum, y))
        st["hr"] = _hr_series(rng, np.full(n, 0.08), u["resting_hr"], u["hrmax"])
        self.rows[k]["duration_min"] = round(n * DT / 60, 2)
        self._fault(k, "car_speed")

    # ---- profile spoofing (U6)
    def spoof_profiles(self, users: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        users = users.copy()
        users["spoof_type"] = None
        users["source_user"] = None
        fit = users[users.persona.isin(["Endurance Runner", "HIIT Enthusiast"]) & (users.fitness > 0.6)].user_id
        walkers = users[users.persona == "Casual Walker"].user_id
        chosen = list(rng.choice(fit, size=8, replace=False))
        for i, uid in enumerate(chosen):
            m = users.user_id == uid
            if i % 2 == 0:  # age falsified: elite young physiology, claimed 70+
                users.loc[m, "age"] = int(rng.integers(70, 80))
                users.loc[m, "spoof_type"] = "age_falsified"
            else:  # impossible body: BMI under 11
                h = users.loc[m, "height_cm"].iloc[0] / 100
                users.loc[m, "weight_kg"] = round(float(rng.uniform(8.5, 11) * h * h), 1)
                users.loc[m, "spoof_type"] = "impossible_body"
        for uid in rng.choice(walkers, size=N_IMPLAUSIBLE_PROFILES - 8, replace=False):
            m = users.user_id == uid  # inflated fitness metrics for a slow walker
            users.loc[m, ["vo2max", "resting_hr"]] = [round(float(rng.uniform(88, 96)), 1), int(rng.integers(26, 32))]
            users.loc[m, "spoof_type"] = "vo2_inflated"
        return users

    def duplicate_accounts(self, users: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        src_ids = rng.choice(users[users.spoof_type.isna()].user_id, size=N_DUPLICATE_ACCOUNTS, replace=False)
        new_rows = []
        next_id = int(users.user_id.max()) + 1
        for sid in src_ids:
            src = users[users.user_id == sid].iloc[0].to_dict()
            male = src["gender"] == "M"
            src.update(user_id=next_id, name=f"{rng.choice(FIRST_M if male else FIRST_F)} {rng.choice(LAST)}",
                       age=int(np.clip(src["age"] + rng.integers(-3, 4), 18, 80)),
                       spoof_type="duplicate_account", source_user=int(sid),
                       signup=history_start() - timedelta(days=int(rng.integers(1, 20))))
            for r in [r for r in self.rows if r["user_id"] == sid]:
                k = len(self.rows)
                self.rows.append({**r, "k": k, "user_id": next_id})
                self.streams[k] = {key: (None if a is None else a.copy()) for key, a in self.streams[r["k"]].items()}
                self.ex[k] = list(self.ex[r["k"]])
                self.gt_w[k] = {**self.gt_w[r["k"]], "fault_type": "copied_workout"}
            new_rows.append(src)
            next_id += 1
        return pd.concat([users, pd.DataFrame(new_rows)], ignore_index=True)

    # ---- U1 data quality issues
    def resync_duplicates(self):
        rng = self.rng
        clean = [r for r in self.rows if self.gt_w[r["k"]]["fault_type"] is None]
        for i in rng.choice(len(clean), size=int(P_RESYNC_DUPLICATE * len(self.rows)), replace=False):
            r = clean[i]
            k = len(self.rows)
            self.rows.append({**r, "k": k, "start_time": r["start_time"] + timedelta(seconds=int(rng.integers(1, 90)))})
            self.streams[k] = self.streams[r["k"]]
            self.ex[k] = list(self.ex[r["k"]])
            self.gt_w[k] = {**self.gt_w[r["k"]], "duplicate_of": r["k"]}


def generate(seed: int = C.SEED, n_users: int = C.N_USERS) -> Dataset:
    g = _Gen(seed, n_users)
    rng = g.rng
    users = g.users()
    g.schedule(users)
    g.faults(users)
    users = g.spoof_profiles(users)
    users = g.duplicate_accounts(users)
    g.resync_duplicates()

    # Workout ids follow upload order (start time), like an app database.
    order = sorted(g.rows, key=lambda r: (r["start_time"], r["k"]))
    kid = {r["k"]: i + 1 for i, r in enumerate(order)}
    workouts = pd.DataFrame(order).assign(workout_id=lambda d: d.k.map(kid))
    exercises = pd.DataFrame([(kid[k], e) for k, items in g.ex.items() for e in items],
                             columns=["workout_id", "exercise"]).sort_values(["workout_id", "exercise"])
    streams = {kid[k]: s for k, s in g.streams.items()}
    gt_workouts = pd.DataFrame([{"workout_id": kid[k], **v,
                                 "duplicate_of": None if v["duplicate_of"] is None else kid[v["duplicate_of"]]}
                                for k, v in g.gt_w.items()]).sort_values("workout_id")
    gt_segments = pd.DataFrame([(kid[k], int(a), int(b), ph) for k, a, b, ph in g.gt_seg
                                if g.gt_w[k]["fault_type"] is None],
                               columns=["workout_id", "start_idx", "end_idx", "phase"])

    # ---- U1 corruption, remembering the true values
    gt_values = []
    imperial_users = set(users.loc[users.device == IMPERIAL_DEVICE, "user_id"])
    for col in ("avg_hr", "calories"):
        idx = rng.choice(len(workouts), size=int(P_MISSING[col] * len(workouts)), replace=False)
        gt_values += [("workouts", int(workouts.workout_id.iat[i]), col, float(workouts[col].iat[i])) for i in idx]
        workouts.loc[workouts.index[idx], col] = np.nan
    imperial = workouts.user_id.isin(imperial_users)
    workouts["distance_unit"] = np.where(imperial, "mi", "km")
    workouts.loc[imperial, "distance_km"] = (workouts.loc[imperial, "distance_km"] / 1.609344).round(3)
    workouts = workouts.rename(columns={"distance_km": "distance"})
    messy = rng.random(len(workouts)) < P_MESSY_LABEL
    workouts.loc[messy, "activity"] = [str(rng.choice(MESSY_LABELS[a])) for a in workouts.loc[messy, "activity"]]

    users["weight_unit"] = np.where(users.user_id.isin(imperial_users), "lb", "kg")
    users["weight"] = np.where(users.weight_unit == "lb", (users.weight_kg * 2.20462).round(1), users.weight_kg)
    idx = rng.choice(len(users), size=int(P_MISSING["weight"] * len(users)), replace=False)
    gt_values += [("users", int(users.user_id.iat[i]), "weight_kg", float(users.weight_kg.iat[i])) for i in idx]
    users.loc[users.index[idx], "weight"] = np.nan
    labelled = rng.random(len(users)) < 0.75
    noisy = rng.random(len(users)) < 0.10
    assessed = []
    for lvl, lab, nz in zip(users.level, labelled, noisy):
        if not lab:
            assessed.append(None)
            continue
        i = C.LEVELS.index(lvl)
        if nz:
            i = int(np.clip(i + rng.choice([-1, 1]), 0, len(C.LEVELS) - 1))
        assessed.append(C.LEVELS[i])
    users["assessed_level"] = assessed

    gt_users = users[["user_id", "persona", "level", "fitness", "hrmax", "spoof_type", "source_user"]].copy()
    gt_users = gt_users.rename(columns={"fitness": "fitness_latent", "hrmax": "hrmax_true"})
    users_raw = users[["user_id", "name", "gender", "age", "height_cm", "weight", "weight_unit", "device",
                       "resting_hr", "vo2max", "assessed_level", "home_zone", "signup"]].rename(
        columns={"signup": "signup_date"})
    workouts_raw = workouts[["workout_id", "user_id", "activity", "title", "start_time", "duration_min", "distance",
                             "distance_unit", "avg_hr", "max_hr", "calories"]]

    planted = {
        "seed": seed, "n_users": n_users, "weeks": C.WEEKS, "history_start": history_start().isoformat(),
        "rules": [{"antecedent": a, "consequent": c} for a, c in PLANTED_RULES],
        "sequences": PLANTED_SEQUENCES,
        "personas": C.PERSONAS, "levels": C.LEVELS,
        "workout_faults": WORKOUT_FAULTS,
        "popular_routes": [{"id": r["id"], "name": r["name"], "kind": r["kind"]} for r in POPULAR_ROUTES],
    }
    return Dataset(users_raw.reset_index(drop=True), workouts_raw.reset_index(drop=True), exercises, streams,
                   gt_users, gt_workouts, gt_segments,
                   pd.DataFrame(gt_values, columns=["table", "row_id", "column", "true_value"]), planted)
