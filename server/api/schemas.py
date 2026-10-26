"""Request and response models. Analyst endpoints return report dictionaries
(documented on the dashboard); the mobile endpoints are fully typed so the app
can generate TypeScript types from /openapi.json."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------------- analyst requests

class OlapQuery(BaseModel):
    spec: dict[str, Any]
    op: dict[str, Any] | None = Field(None, description="rollup | drilldown | slice | dice | pivot | clear_filters")


class AssociationRun(BaseModel):
    algorithm: Literal["apriori", "fpgrowth"] = "fpgrowth"
    basket: Literal["session", "user_week"] = "session"
    min_support: float = Field(0.02, gt=0, le=1)
    min_confidence: float = Field(0.6, ge=0, le=1)
    min_lift: float = Field(1.0, ge=0)


class ClassifyRun(BaseModel):
    model: Literal["id3", "c45", "cart", "nb", "knn"] = "c45"
    max_depth: int = Field(6, ge=1, le=20)
    min_samples_split: int = Field(10, ge=2, le=200)
    prune: bool = False
    k: int = Field(7, ge=1, le=75)
    weights: Literal["uniform", "distance"] = "distance"
    folds: int = Field(5, ge=2, le=10)


class ClusterRun(BaseModel):
    algorithm: Literal["kmeans", "kmedoids", "agglomerative", "dbscan"] = "kmeans"
    k: int = Field(5, ge=2, le=15)
    linkage: Literal["single", "complete", "average", "ward"] = "ward"
    method: Literal["pam", "clara"] = "pam"
    eps: float = Field(1.2, gt=0)
    min_samples: int = Field(10, ge=2)
    n_init: int = Field(5, ge=1, le=20)


class OutlierRun(BaseModel):
    method: Literal["zscore", "iqr", "lof", "iforest", "rules", "duplicates", "ensemble"] = "ensemble"
    z: float = Field(4.0, gt=0)
    k: float = Field(3.0, gt=0, description="IQR fence multiplier")
    contamination: float = Field(0.03, gt=0, lt=0.5)
    lof_k: int = Field(20, ge=2, le=100)
    n_trees: int = Field(100, ge=10, le=500)


class SequenceRun(BaseModel):
    min_support: float = Field(0.025, gt=0, le=1)
    max_gap: int | None = Field(4, ge=1, le=6)


class RouteRun(BaseModel):
    eps: float = Field(150, gt=0, description="metres")
    min_samples: int = Field(8, ge=2)


class HotspotRun(BaseModel):
    eps: float = Field(100, gt=0, description="metres")
    min_samples: int = Field(60, ge=2)


# ----------------------------------------------------------------------------- mobile

class UserSummary(BaseModel):
    user_id: int
    name: str
    gender: str
    age: int
    home_zone: str
    level: str
    level_source: str
    persona: str
    flagged: bool


class Level(BaseModel):
    value: str
    source: str
    predicted: str
    probabilities: dict[str, float]


class Persona(BaseModel):
    name: str
    cluster: int
    distances: dict[str, float]


class SimilarUser(BaseModel):
    user_id: int
    name: str
    persona: str


class WeekRollup(BaseModel):
    week: str
    minutes: dict[str, float]
    sessions: int
    calories: float


class Routine(BaseModel):
    text: str
    pattern: list[list[str]]
    weeks: float


class Profile(BaseModel):
    user: dict[str, Any]
    level: Level
    persona: Persona
    similar: list[SimilarUser]
    weekly: list[WeekRollup]
    routines: list[Routine]
    stats: dict[str, float | None]
    spoof_flag: bool
    spoof_reasons: list[str]
    flagged_workouts: int


class WorkoutItem(BaseModel):
    workout_id: int
    activity: str
    session_type: str
    title: str
    start_time: str
    duration_min: float
    distance_km: float | None
    avg_hr: float | None
    max_hr: float | None
    calories: float | None
    has_gps: bool
    flagged: bool
    reasons: str
    route_name: str | None
    source: str


class Recommendation(BaseModel):
    exercise: str
    because: list[str]
    confidence: float
    lift: float
    support: float


class Alert(BaseModel):
    kind: Literal["workout", "profile"]
    workout_id: int | None
    title: str
    detail: str
    start_time: str | None


class Segment(BaseModel):
    start: int
    end: int
    mean_speed: float
    phase: str


class WorkoutDetail(BaseModel):
    workout: WorkoutItem
    exercises: list[str]
    hr: list[int]
    dt: int
    lat: list[float] | None
    lon: list[float] | None
    speed_kmh: list[float] | None
    segments: list[Segment] | None
    run_kind: str | None
    route: dict[str, Any] | None


class RouteSummary(BaseModel):
    cluster: int
    name: str
    size: int
    track: list[list[float]]


class UserRoutes(BaseModel):
    popular: list[RouteSummary]
    workouts: list[WorkoutItem]


class UploadRequest(BaseModel):
    activity: Literal["Run", "Walk", "Cycle", "Swim", "Strength", "HIIT", "Yoga"] = "Run"
    kind: Literal["easy", "intervals", "tempo", "long", "push", "pull", "legs"] = "easy"
    route: Literal["popular", "personal"] = "popular"
    faults: list[Literal["hr_spike", "hr_flatline", "hr_dropout", "gps_teleport", "car_speed",
                         "calorie_mismatch"]] = []
    exercises: list[str] | None = None
    title: str | None = None


class Verdict(BaseModel):
    flagged: bool
    reasons: list[str]
    detectors: dict[str, bool]
    scores: dict[str, float]
    features: dict[str, float | None]


class UploadResult(BaseModel):
    workout: WorkoutItem
    verdict: Verdict
    detail: WorkoutDetail
    level_before: str
    level_after: str
    persona_before: str
    persona_after: str
    recommendations: list[Recommendation]
