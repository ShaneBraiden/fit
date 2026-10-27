"""Streak arithmetic, and the plan / muscles / friends endpoints (the API ones need the pipeline)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api import state
from api.main import app
from fitmine.training import streak_numbers

client = TestClient(app)
needs_models = pytest.mark.skipif(not state.ready(), reason="run `python -m fitmine.pipeline run` first")
TODAY = date.today()


def _d(back: int) -> str:
    return (TODAY - timedelta(days=back)).isoformat()


def test_streak_numbers():
    assert streak_numbers(set(), set(), TODAY) == (0, 0)
    assert streak_numbers({_d(0), _d(1), _d(2)}, set(), TODAY) == (3, 3)
    # nothing yet today: the streak still runs from yesterday
    assert streak_numbers({_d(1), _d(2)}, set(), TODAY) == (2, 2)
    # a missed day breaks it; the older run is the longest
    assert streak_numbers({_d(0), _d(2), _d(3), _d(4)}, set(), TODAY) == (1, 3)
    # a planned rest day keeps it alive without adding to it
    rest = {(TODAY - timedelta(days=1)).weekday()}
    assert streak_numbers({_d(0), _d(2), _d(3)}, rest, TODAY) == (3, 3)


def _signup(name="Test Lifter"):
    import uuid
    body = {"email": f"t{uuid.uuid4().hex[:10]}@example.com", "password": "correct horse", "name": name,
            "gender": "M", "age": 31, "height_cm": 178, "weight_kg": 80}
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 200, r.text
    return body["email"], {"Authorization": f"Bearer {r.json()['token']}"}


def _lift(h, back: int, exercises, loads=(), plan_day=None):
    start = (TODAY - timedelta(days=back)).isoformat() + "T07:00:00"
    r = client.post("/api/me/workouts", headers=h, json={
        "activity": "Strength", "duration_min": 50, "start_time": start, "exercises": exercises,
        "loads": list(loads), "plan_day": plan_day})
    assert r.status_code == 200, r.text
    return r.json()


@needs_models
def test_plan_streak_and_muscles():
    _, h = _signup()
    q = f"?today={TODAY.isoformat()}"
    assert client.get("/api/me/plan" + q, headers=h).json()["plan"] is None
    cat = client.get("/api/catalog").json()
    assert "Hip Thrust" in cat["exercises"]["Strength"] and cat["exercise_muscles"]["Squat"]["primary"]
    upper_lower = next(t for t in cat["plan_templates"] if t["key"] == "upper_lower")
    r = client.put("/api/me/plan" + q, headers=h, json={"name": "My split", "days": upper_lower["days"]})
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["name"] == "My split" and r.json()["planned"] == 4

    w = _lift(h, 1, ["Bench Press"], [{"exercise": "Bench Press", "sets": 4, "reps": 8, "weight_kg": 60}], "Upper")
    assert w["workout"]["title"] == "Upper"
    assert w["detail"]["loads"] == [{"exercise": "Bench Press", "sets": 4, "reps": 8, "weight_kg": 60.0}]
    _lift(h, 0, ["Bench Press", "Hip Thrust"], [{"exercise": "Bench Press", "sets": 3, "reps": 5, "weight_kg": 70}])

    s = client.get("/api/me/streak" + q, headers=h).json()
    assert s["current"] >= 2 and s["today_done"] and not s["at_risk"]
    assert s["weekly_goal"] == 4 and len(s["week"]) == 7

    m = {x["muscle"]: x for x in client.get("/api/me/muscles" + q, headers=h).json()["muscles"]}
    assert m["Chest"]["sets_this_week"] + sum(x["sets"] for x in m["Chest"]["weekly"][:-1]) == 7
    assert m["Triceps"]["weekly"][-1]["sets"] + m["Triceps"]["weekly"][-2]["sets"] == 3.5  # secondary: half a set
    assert m["Glutes"]["days_since"] == 0 and m["Calves"]["status"] == "not_trained"
    bench = next(e for e in m["Chest"]["exercises"] if e["exercise"] == "Bench Press")
    assert bench["best_e1rm"] == pytest.approx(81.7, abs=0.1) and len(bench["history"]) == 2

    assert client.post("/api/me/workouts", headers=h, json={
        "activity": "Strength", "duration_min": 30, "loads": [{"exercise": "Juggling", "sets": 3}]}).status_code == 422


@needs_models
def test_friends_flow():
    a_email, a = _signup("Ana")
    _, b = _signup("Ben")
    b_code = client.get("/api/me/friends", headers=b).json()["code"]
    assert client.post("/api/me/friends", headers=a, json={"handle": "nobody@example.com"}).status_code == 400
    assert client.post("/api/me/friends", headers=a, json={"handle": a_email}).status_code == 400  # self
    r = client.post("/api/me/friends", headers=a, json={"handle": f"{b_code[:4]}-{b_code[4:]}".lower()})
    assert r.json()["status"] == "pending"
    assert client.post("/api/me/friends", headers=a, json={"handle": b_code}).status_code == 400  # twice

    b_list = client.get("/api/me/friends", headers=b).json()
    a_id = b_list["incoming"][0]["user_id"]
    b_id = b_list["me"]["user_id"]
    assert client.get(f"/api/me/friends/{b_id}/compare", headers=a).status_code == 404  # not accepted yet
    assert client.post(f"/api/me/friends/{a_id}/accept", headers=b).status_code == 204

    _lift(b, 0, ["Squat"])
    a_list = client.get(f"/api/me/friends?today={TODAY.isoformat()}", headers=a).json()
    assert [f["name"] for f in a_list["friends"]] == ["Ben"] and a_list["leaderboard"][0] == b_id
    c = client.get(f"/api/me/friends/{b_id}/compare?today={TODAY.isoformat()}", headers=a).json()
    assert c["friend"]["streak"] == 1 and c["friend"]["muscle_sets"]["Quads"] > 0 and c["me"]["name"] == "Ana"

    assert client.delete(f"/api/me/friends/{b_id}", headers=a).status_code == 204
    assert client.get(f"/api/me/friends/{b_id}/compare", headers=a).status_code == 404
