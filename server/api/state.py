"""Lazily loaded, process-wide state for the API: cached reports and the
datasets that live re-runs need (built once, reused by every request)."""
from __future__ import annotations

import threading
from functools import lru_cache

from fastapi import HTTPException

from fitmine import config as C
from fitmine.analyses import common
from fitmine.data import store

_lock = threading.Lock()


def con():
    """A fresh SQLite connection per request (SQLite connections are not thread-safe)."""
    c = store.connect()
    try:
        yield c
    finally:
        c.close()


def report(name: str) -> dict:
    r = common.load_json(name)
    if r is None:
        raise HTTPException(503, f"artifact '{name}' missing: run `python -m fitmine.pipeline run` first")
    return r


def ready() -> bool:
    return (C.ARTIFACTS_DIR / "summary.json").exists() and C.DB_PATH.exists()


@lru_cache(maxsize=1)
def cube():
    from fitmine.analyses.u2_warehouse import load_cube
    c = store.connect()
    try:
        return load_cube(c)
    finally:
        c.close()


@lru_cache(maxsize=1)
def session_baskets():
    from fitmine.analyses.u3_association import baskets
    c = store.connect()
    try:
        return {"session": baskets(c, "session"), "user_week": baskets(c, "user_week")}
    finally:
        c.close()


@lru_cache(maxsize=1)
def classification_data():
    from fitmine.analyses.u4_classification import dataset
    c = store.connect()
    try:
        return dataset(c)
    finally:
        c.close()


@lru_cache(maxsize=1)
def clustering_data():
    from fitmine.algorithms.pca import PCA
    from fitmine.analyses.u5_clustering import dataset
    c = store.connect()
    try:
        feats, Z, _ = dataset(c)
    finally:
        c.close()
    return feats, Z, PCA(2).fit(Z).transform(Z)


@lru_cache(maxsize=1)
def outlier_data():
    c = store.connect()
    try:
        F = store.read("workout_features", c)
        truth = store.read("gt_workouts", c).set_index("workout_id").fault_type.dropna()
    finally:
        c.close()
    return F, truth


@lru_cache(maxsize=1)
def sequence_data():
    from fitmine.analyses.u7_sequences_trajectories import week_sequences
    c = store.connect()
    try:
        return week_sequences(c), store.planted(c)["sequences"]
    finally:
        c.close()


@lru_cache(maxsize=1)
def track_data():
    from fitmine.analyses.u7_sequences_trajectories import gps_tracks
    c = store.connect()
    try:
        w, streams = gps_tracks(c)
        gt_route = store.read("gt_workouts", c).set_index("workout_id").route_id
    finally:
        c.close()
    return w, streams, gt_route, common.load_pickle("route_state")


def clear():
    for f in (cube, session_baskets, classification_data, clustering_data, outlier_data, sequence_data, track_data):
        f.cache_clear()
