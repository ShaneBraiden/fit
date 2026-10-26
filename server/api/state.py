"""Process-wide helpers for the API: a database connection per request and the
pipeline's cached reports."""
from __future__ import annotations

from fastapi import HTTPException

from fitmine import config as C
from fitmine.analyses import common
from fitmine.data import store


def con():
    """A fresh connection per request (SQLite connections are not thread-safe; Postgres ones come from a pool)."""
    c = store.connect()
    try:
        yield c
    finally:
        c.close()


def report(name: str) -> dict:
    r = common.load_json(name)
    if r is None:
        raise HTTPException(503, f"report '{name}' missing: run `python -m fitmine.pipeline run` first")
    return r


def ready() -> bool:
    return (C.ARTIFACTS_DIR / "summary.json").exists() and store.exists("user_insights")
