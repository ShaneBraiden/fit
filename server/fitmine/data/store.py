"""Storage: SQLite on disk by default, or Postgres (Supabase) when DATABASE_URL is set.
Tables are plain pandas frames; streams are compressed blobs.

Synthetic training data (rebuilt by every pipeline run):
  raw tables                          users_raw, workouts_raw, exercises, streams
  clean tables (data cleaning)        users, workouts
  mining outputs                      user_insights, workout_flags, workout_features, workout_routes
  ground truth (evaluation only)      gt_users, gt_workouts, gt_segments, gt_values
Real accounts (never touched by the pipeline, see fitmine/live.py):
  accounts, auth_tokens, live_users, live_workouts, live_exercises, live_streams

Callers use one sqlite3-style surface for both: con.execute / executemany with `?` placeholders,
con.commit(), con.close(), and read / write / query below for pandas frames.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import zlib
from functools import lru_cache

import numpy as np
import pandas as pd

from .. import config as C

_lock = threading.Lock()


def is_postgres() -> bool:
    return bool(C.DATABASE_URL)


# ----------------------------------------------------------------------------- Postgres (Supabase)

@lru_cache(maxsize=1)
def _engine():
    import sqlalchemy as sa

    url = C.DATABASE_URL
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
    # prepare_threshold=None: no server-side prepared statements, which Supabase's pooler can't keep.
    engine = sa.create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                              connect_args={"prepare_threshold": None})

    @sa.event.listens_for(engine, "connect")
    def _schema(dbapi_con, _):
        # A private schema keeps the tables out of Supabase's public REST API.
        with dbapi_con.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{C.DB_SCHEMA}"; SET search_path TO "{C.DB_SCHEMA}"')
        dbapi_con.commit()

    return engine


def _py(v):
    """psycopg doesn't adapt numpy scalars."""
    return v.item() if isinstance(v, np.generic) else v


def _pg(sql: str, params) -> str:
    return sql.replace("%", "%%").replace("?", "%s") if params else sql


class PgConnection:
    """A SQLAlchemy connection with the sqlite3 methods the rest of the code calls."""

    def __init__(self):
        self.sa = _engine().connect()

    def execute(self, sql: str, params=()):
        params = tuple(_py(v) for v in params)
        return self.sa.exec_driver_sql(_pg(sql, params), params) if params else self.sa.exec_driver_sql(sql)

    def executemany(self, sql: str, rows):
        rows = [tuple(_py(v) for v in r) for r in rows]
        if rows:
            self.sa.exec_driver_sql(_pg(sql, True), rows)

    def commit(self):
        self.sa.commit()

    def close(self):
        self.sa.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.commit()
        self.close()


def _copy(table, conn, keys, data_iter):
    """pandas to_sql method: bulk-load with COPY, much faster than INSERTs over the network."""
    cols = ", ".join(f'"{k}"' for k in keys)
    with conn.connection.driver_connection.cursor() as cur:
        with cur.copy(f'COPY "{table.name}" ({cols}) FROM STDIN') as cp:
            for row in data_iter:
                cp.write_row([_py(v) for v in row])


# ----------------------------------------------------------------------------- tables

def connect():
    if is_postgres():
        return PgConnection()
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(C.DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def write(df: pd.DataFrame, table: str, con=None, if_exists: str = "replace"):
    own = con is None
    con = con or connect()
    with _lock:
        if isinstance(con, PgConnection):
            df.to_sql(table, con.sa, if_exists=if_exists, index=False, method=_copy, chunksize=20000)
        else:
            df.to_sql(table, con, if_exists=if_exists, index=False)
        con.commit()
    if own:
        con.close()


def query(sql: str, con, params=()) -> pd.DataFrame:
    """A SELECT with `?` placeholders, as a frame."""
    if isinstance(con, PgConnection):
        params = tuple(_py(v) for v in params)
        return pd.read_sql_query(_pg(sql, params), con.sa, params=params or None)
    return pd.read_sql_query(sql, con, params=params)


def read(table: str, con=None, where: str = "", params=()) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    df = query(f"SELECT * FROM {table} {where}", con, params)
    if own:
        con.close()
    return df


def exists(table: str) -> bool:
    if is_postgres():
        import sqlalchemy as sa
        return sa.inspect(_engine()).has_table(table, schema=C.DB_SCHEMA)
    if not C.DB_PATH.exists():
        return False
    with connect() as con:
        return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def columns(table: str, con) -> list[str]:
    if isinstance(con, PgConnection):
        return [r[0] for r in con.execute("SELECT column_name FROM information_schema.columns "
                                          "WHERE table_schema=? AND table_name=? ORDER BY ordinal_position",
                                          (C.DB_SCHEMA, table))]
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


# ----------------------------------------------------------------------------- streams

def _enc(a: np.ndarray | None, scale: float, dtype) -> bytes | None:
    if a is None:
        return None
    return zlib.compress(np.round(np.asarray(a) * scale).astype(dtype).tobytes())


def _dec(b: bytes | None, scale: float, dtype) -> np.ndarray | None:
    if b is None:
        return None
    return np.frombuffer(zlib.decompress(b), dtype=dtype).astype(float) / scale


def write_streams(streams: dict, con, if_exists: str = "replace", table: str = "streams"):
    """streams: workout_id -> {"hr": array, "lat": array|None, "lon": array|None}."""
    rows = [(int(wid), len(s["hr"]), _enc(s["hr"], 1, np.int16),
             _enc(s["lat"], 1e6, np.int32), _enc(s["lon"], 1e6, np.int32)) for wid, s in streams.items()]
    with _lock:
        if if_exists == "replace":
            con.execute(f"DROP TABLE IF EXISTS {table}")
        blob = "BYTEA" if isinstance(con, PgConnection) else "BLOB"
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} (workout_id INTEGER PRIMARY KEY, n INTEGER, "
                    f"hr {blob}, lat {blob}, lon {blob})")
        con.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?) ON CONFLICT (workout_id) DO UPDATE SET "
                        "n=excluded.n, hr=excluded.hr, lat=excluded.lat, lon=excluded.lon", rows)
        con.commit()


def _row_to_stream(row) -> dict:
    return {"hr": _dec(row[2], 1, np.int16), "lat": _dec(row[3], 1e6, np.int32), "lon": _dec(row[4], 1e6, np.int32)}


def load_streams(con, workout_ids=None) -> dict[int, dict]:
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


def load_stream(con, workout_id: int, table: str = "streams") -> dict | None:
    r = con.execute(f"SELECT * FROM {table} WHERE workout_id=?", (int(workout_id),)).fetchone()
    return None if r is None else _row_to_stream(r)


# ----------------------------------------------------------------------------- whole dataset

def save_dataset(ds, con=None):
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


def planted(con=None) -> dict:
    df = read("meta", con, "WHERE key='planted'")
    return json.loads(df.value.iat[0])
