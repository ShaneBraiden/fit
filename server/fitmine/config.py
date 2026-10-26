"""Project-wide settings: paths, dataset size, and the synthetic city."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent

# server/.env (gitignored) can hold DATABASE_URL; real environment variables win.
_ENV = SERVER_DIR / ".env"
if _ENV.exists():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        _k, _sep, _v = _line.partition("=")
        if _sep and not _line.lstrip().startswith("#"):
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

DATA_DIR = SERVER_DIR / "data"
DB_PATH = DATA_DIR / "fitmine.db"
# Supabase (Postgres) connection string. Empty means the local SQLite file at DB_PATH.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_SCHEMA = os.environ.get("DB_SCHEMA", "fitmine")
ARTIFACTS_DIR = SERVER_DIR / "artifacts"

SEED = 42
N_USERS = 1000
WEEKS = 8
# The history ends on Sunday 2026-10-18; WEEKS full Monday-to-Sunday weeks before it.
HISTORY_END = date(2026, 10, 18)
STREAM_INTERVAL_S = 15  # one HR / GPS sample every 15 seconds

ACTIVITIES = ["Run", "Cycle", "Walk", "Swim", "Strength", "HIIT", "Yoga"]
ACTIVITY_CATEGORY = {
    "Run": "Cardio", "Cycle": "Cardio", "Walk": "Cardio", "Swim": "Cardio",
    "Strength": "Strength", "HIIT": "Strength", "Yoga": "Mind-Body",
}
GPS_ACTIVITIES = {"Run", "Cycle", "Walk"}

# Metabolic equivalents used to sanity-check reported calories (kcal = MET x kg x hours).
MET = {"Walk": 3.5, "Cycle": 8.0, "Swim": 7.0, "Strength": 5.0, "HIIT": 8.0, "Yoga": 2.5}
# Running MET grows with speed: roughly 1 MET per km/h.

PERSONAS = ["Endurance Runner", "Gym Strength", "HIIT Enthusiast", "Yoga & Mobility", "Casual Walker"]
LEVELS = ["Beginner", "Intermediate", "Advanced", "Elite"]

ZONES = ["South Mumbai", "Central Mumbai", "Western Suburbs", "Eastern Suburbs", "North Suburbs"]
CITY = "Mumbai"
