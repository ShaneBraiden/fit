"""Smoke-test every endpoint against the pipeline's artifacts (skipped until the pipeline has run)."""
import pytest
from fastapi.testclient import TestClient

from api import state
from api.main import app

pytestmark = pytest.mark.skipif(not state.ready(), reason="run `python -m fitmine.pipeline run` first")
client = TestClient(app)


@pytest.mark.parametrize("path", [
    "/api/health", "/api/summary", "/api/dataset/summary", "/api/preprocess/report", "/api/olap/meta",
    "/api/olap/examples", "/api/association/report", "/api/classify/report", "/api/cluster/report",
    "/api/outliers/report", "/api/sequences/report", "/api/trajectories/report", "/api/verify",
])
def test_reports(path):
    r = client.get(path)
    assert r.status_code == 200, r.text


def test_live_reruns():
    spec = client.get("/api/olap/meta").json()["default_spec"]
    r = client.post("/api/olap/query", json={"spec": spec, "op": {"type": "rollup", "dim": "date"}})
    assert r.status_code == 200 and r.json()["spec"]["rows"][0]["level"] == "month"
    assert client.post("/api/association/run", json={"algorithm": "apriori", "min_support": 0.05}).status_code == 200
    r = client.post("/api/classify/run", json={"model": "cart", "max_depth": 4})
    assert r.status_code == 200 and "tree" in r.json()
    assert client.post("/api/cluster/run", json={"algorithm": "kmedoids", "k": 4}).status_code == 200
    assert client.post("/api/outliers/run", json={"method": "iqr", "k": 2.5}).status_code == 200
    assert client.post("/api/sequences/run", json={"min_support": 0.05}).status_code == 200
    assert client.post("/api/trajectories/routes", json={"eps": 120}).status_code == 200
    run = client.get("/api/trajectories/report").json()["example_workout"]
    assert client.get(f"/api/trajectories/{run}/segments").status_code == 200
    assert client.get(f"/api/outliers/workout/{run}").status_code == 200


def test_mobile_flow():
    users = client.get("/api/users", params={"featured": True}).json()
    assert users
    uid = users[0]["user_id"]
    for p in ("profile", "workouts", "recommendations", "routes", "alerts"):
        r = client.get(f"/api/users/{uid}/{p}")
        assert r.status_code == 200, (p, r.text)
    ws = client.get(f"/api/users/{uid}/workouts").json()
    assert client.get(f"/api/users/{uid}/workouts/{ws[0]['workout_id']}").status_code == 200
    r = client.post(f"/api/users/{uid}/workouts", json={"activity": "Run", "kind": "intervals",
                                                       "faults": ["gps_teleport"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"]["flagged"] and "gps_teleport" in body["verdict"]["reasons"]
    clean = client.post(f"/api/users/{uid}/workouts", json={"activity": "Run", "kind": "easy"}).json()
    assert clean["detail"]["segments"]
    alerts = client.get(f"/api/users/{uid}/alerts").json()
    assert any(a["workout_id"] == body["workout"]["workout_id"] for a in alerts)
