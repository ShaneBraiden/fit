"""SQLite storage. Tables are plain pandas frames; streams are compressed blobs.

Raw tables (what the app collects):  users_raw, workouts_raw, exercises, streams
Clean tables (written by U1):        users, workouts
Warehouse (written by U2):           dim_user, dim_date, dim_activity, dim_location, fact_workout
Mining outputs:                       user_insights, workout_flags
Ground truth (evaluation only):       gt_users, gt_workouts, gt_segments, gt_values
"""
from __future__ import annotations

import json
import sqlite3
import threading
import zlib

import numpy as np
import pandas as pd

from .. import config as C

_lock = threading.Lock()


def connect() -> sqlite3.Connection:
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(C.DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def write(df: pd.DataFrame, table: str, con: sqlite3.Connection | None = None, if_exists: str = "replace"):
    own = con is None
    con = con or connect()
    with _lock:
        df.to_sql(table, con, if_exists=if_exists, index=False)
        con.commit()
    if own:
        con.close()


def read(table: str, con: sqlite3.Connection | None = None, where: str = "", params=()) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    df = pd.read_sql_query(f"SELECT * FROM {table} {where}", con, params=params)
    if own:
        con.close()
    return df


def exists(table: str) -> bool:
    if not C.DB_PATH.exists():
        return False
    with connect() as con:
        return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


# ----------------------------------------------------------------------------- streams

def _enc(a: np.ndarray | None, scale: float, dtype) -> bytes | None:
    if a is None:
        return None
    return zlib.compress(np.round(np.asarray(a) * scale).astype(dtype).tobytes())


def _dec(b: bytes | None, scale: float, dtype) -> np.ndarray | None:
    if b is None:
        return None
    return np.frombuffer(zlib.decompress(b), dtype=dtype).astype(float) / scale


def write_streams(streams: dict, con: sqlite3.Connection, if_exists: str = "replace"):
    """streams: workout_id -> {"hr": array, "lat": array|None, "lon": array|None}."""
    rows = [(int(wid), len(s["hr"]), _enc(s["hr"], 1, np.int16),
             _enc(s["lat"], 1e6, np.int32), _enc(s["lon"], 1e6, np.int32)) for wid, s in streams.items()]
    with _lock:
        if if_exists == "replace":
            con.execute("DROP TABLE IF EXISTS streams")
        con.execute("CREATE TABLE IF NOT EXISTS streams (workout_id INTEGER PRIMARY KEY, n INTEGER, "
                    "hr BLOB, lat BLOB, lon BLOB)")
        con.executemany("INSERT OR REPLACE INTO streams VALUES (?,?,?,?,?)", rows)
        con.commit()


def _row_to_stream(row) -> dict:
    return {"hr": _dec(row[2], 1, np.int16), "lat": _dec(row[3], 1e6, np.int32), "lon": _dec(row[4], 1e6, np.int32)}


def load_streams(con: sqlite3.Connection, workout_ids=None) -> dict[int, dict]:
    if workout_ids is None:
        cur = con.execute("SELECT * FROM streams")
    else:
        ids = [int(i) for i in workout_ids]
        out = {}
        for i in range(0, len(ids), 900):
            chunk = ids[i:i + 900]
            cur = con.execute(f"SELECT * FROM streams WHERE workout_id IN ({','.join('?' * len(chunk))})", chunk)
            out.update({r[0]: _row_to_stream(r) for r in cur})
        return out
    return {r[0]: _row_to_stream(r) for r in cur}


def load_stream(con: sqlite3.Connection, workout_id: int) -> dict | None:
    r = con.execute("SELECT * FROM streams WHERE workout_id=?", (int(workout_id),)).fetchone()
    return None if r is None else _row_to_stream(r)


# ----------------------------------------------------------------------------- whole dataset

def save_dataset(ds, con: sqlite3.Connection | None = None):
    own = con is None
    con = con or connect()
    users = ds.users.copy()
    users["signup_date"] = users["signup_date"].astype(str)
    workouts = ds.workouts.copy()
    workouts["start_time"] = workouts["start_time"].astype(str)
    for df, name in ((users, "users_raw"), (workouts, "workouts_raw"), (ds.exercises, "exercises"),
                     (ds.gt_users, "gt_users"), (ds.gt_workouts, "gt_workouts"), (ds.gt_segments, "gt_segments"),
                     (ds.gt_values, "gt_values")):
        write(df, name, con)
    write_streams(ds.streams, con)
    write(pd.DataFrame([{"key": "planted", "value": json.dumps(ds.planted)}]), "meta", con)
    if own:
        con.close()


def planted(con: sqlite3.Connection | None = None) -> dict:
    df = read("meta", con, "WHERE key='planted'")
    return json.loads(df.value.iat[0])
