"""Tests always use the local SQLite database, never the DATABASE_URL in server/.env:
the API tests create accounts and workouts."""
import os

os.environ["DATABASE_URL"] = ""
