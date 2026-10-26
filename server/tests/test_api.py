"""End-to-end account flow against the pipeline's models (skipped until the pipeline has run)."""
import time
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import state
from api.main import app

pytestmark = pytest.mark.skipif(not state.ready(), reason="run `python -m fitmine.pipeline run` first")
client = TestClient(app)


def _signup(**extra):
    body = {"email": f"t{uuid.uuid4().hex[:10]}@example.com", "password": "correct horse", "name": "Test Runner",
            "gender": "F", "age": 29, "height_cm": 165, "weight_kg": 58, **extra}
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 200, r.text
    return body, r.json()["token"]


def _track(km=5.0, minutes=30.0, lat0=13.0350, lon0=80.1450):
    """A straight-ish run near Chennai: one fix per second."""
    n = int(minutes * 60)
    t0 = time.time() * 1000 - n * 1000
    north = np.linspace(0, km * 1000, n) / 110_540
    return [{"t": t0 + i * 1000, "lat": lat0 + north[i], "lon": lon0 + 0.0001 * np.sin(i / 60), "accuracy": 5}
            for i in range(n)]


def test_auth_required():
    assert client.get("/api/me/profile").status_code == 401
    assert client.get("/api/me/profile", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_signup_login_logout():
    body, token = _signup()
    assert client.post("/api/auth/signup", json=body).status_code == 400  # duplicate email
    assert client.post("/api/auth/login", json={"email": body["email"], "password": "wrong pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": body["email"].upper(), "password": body["password"]})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    me = client.get("/api/me", headers=h).json()
    assert me["email"] == body["email"] and me["is_admin"] is False
    assert client.post("/api/auth/logout", headers=h).status_code == 204
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_live_predictions_use_own_workouts():
    _, token = _signup(resting_hr=58)
    h = {"Authorization": f"Bearer {token}"}
    p0 = client.get("/api/me/profile", headers=h).json()
    assert p0["workouts_counted"] == 0 and p0["user"]["vo2max_source"] == "resting heart rate"

    r = client.post("/api/me/workouts", headers=h, json={"activity": "Run", "duration_min": 30, "track": _track()})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["workout"]["has_gps"] and 4.5 < run["workout"]["distance_km"] < 5.5
    assert run["verdict"]["flagged"] is False
    assert run["detail"]["lat"] and run["detail"]["segments"]

    r = client.post("/api/me/workouts", headers=h, json={
        "activity": "Strength", "duration_min": 55, "exercises": ["Bench Press", "Overhead Press"]})
    assert r.status_code == 200, r.text
    lift = r.json()
    assert lift["workout"]["session_type"] == "Push"
    assert any(x["exercise"] == "Tricep Dips" for x in lift["recommendations"])  # a planted rule

    p = client.get("/api/me/profile", headers=h).json()
    assert p["workouts_counted"] == 2 and p["stats"]["sessions_per_week"] == 2
    assert p["user"]["vo2max_source"] == "your runs"
    assert sum(p["level"]["probabilities"].values()) == pytest.approx(1.0)

    # a "run" at car speed is caught and left out of the predictions
    r = client.post("/api/me/workouts", headers=h, json={"activity": "Run", "duration_min": 10,
                                                        "track": _track(km=12, minutes=10)})
    assert r.json()["verdict"]["flagged"]
    assert client.get("/api/me/profile", headers=h).json()["workouts_counted"] == 2
    assert len(client.get("/api/me/alerts", headers=h).json()) == 1

    wid = run["workout"]["workout_id"]
    assert client.get(f"/api/me/workouts/{wid}", headers=h).status_code == 200
    _, other = _signup()
    assert client.get(f"/api/me/workouts/{wid}", headers={"Authorization": f"Bearer {other}"}).status_code == 404
    assert client.delete(f"/api/me/workouts/{wid}", headers=h).status_code == 204
    assert len(client.get("/api/me/workouts", headers=h).json()) == 2


def test_unknown_exercise_rejected_and_catalog():
    _, token = _signup()
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/me/workouts", headers=h, json={"activity": "HIIT", "duration_min": 20, "exercises": ["Juggling"]})
    assert r.status_code == 422
    cat = client.get("/api/catalog").json()
    assert "Burpees" in cat["exercises"]["HIIT"]


def test_model_pages_are_admin_only():
    _, token = _signup()
    r = client.get("/api/models/summary", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
