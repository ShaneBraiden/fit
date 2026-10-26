"""Request and response models. The account endpoints are fully typed so the
web and phone apps can generate TypeScript types from /openapi.json; the admin
model endpoints return the pipeline's report dictionaries."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Activity = Literal["Run", "Walk", "Cycle", "Swim", "Strength", "HIIT", "Yoga"]


# ----------------------------------------------------------------------------- accounts

class SignupRequest(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(min_length=1, max_length=80)
    gender: Literal["F", "M"]
    age: int = Field(ge=13, le=100)
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=30, le=250)
    resting_hr: float | None = Field(None, ge=30, le=120, description="optional, bpm")
    vo2max: float | None = Field(None, ge=15, le=90, description="optional, from a watch or a lab test")


class LoginRequest(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class ProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    gender: Literal["F", "M"] | None = None
    age: int | None = Field(None, ge=13, le=100)
    height_cm: float | None = Field(None, ge=120, le=230)
    weight_kg: float | None = Field(None, ge=30, le=250)
    resting_hr: float | None = Field(None, ge=30, le=120)
    vo2max: float | None = Field(None, ge=15, le=90)


class Account(BaseModel):
    user_id: int
    email: str
    name: str
    gender: str
    age: int
    height_cm: float
    weight_kg: float
    bmi: float
    resting_hr: float | None
    vo2max: float | None
    signup_date: str
    is_admin: bool


class AuthResult(BaseModel):
    token: str
    account: Account


# ----------------------------------------------------------------------------- the user's own data

class Level(BaseModel):
    value: str
    source: str
    predicted: str
    probabilities: dict[str, float]


class Persona(BaseModel):
    name: str
    cluster: int
    distances: dict[str, float]


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
    weekly: list[WeekRollup]
    routines: list[Routine]
    stats: dict[str, float | None]
    workouts_counted: int = Field(description="workouts in the last 8 weeks that the predictions use")
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
    workout_id: int
    title: str
    detail: str
    start_time: str


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


class TrackPoint(BaseModel):
    t: float = Field(description="milliseconds since the epoch")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(None, description="metres")


class RecordRequest(BaseModel):
    activity: Activity
    start_time: datetime | None = Field(None, description="local time the workout started; default now")
    duration_min: float = Field(gt=0, le=600, description="moving time")
    kind: Literal["push", "pull", "legs"] | None = Field(None, description="strength split, if known")
    distance_km: float | None = Field(None, ge=0, le=400, description="for workouts without a GPS track")
    avg_hr: float | None = Field(None, ge=30, le=230)
    max_hr: float | None = Field(None, ge=30, le=240)
    calories: float | None = Field(None, ge=0, le=6000)
    exercises: list[str] = Field(default_factory=list, max_length=40)
    title: str | None = Field(None, max_length=60)
    track: list[TrackPoint] | None = Field(None, max_length=40000, description="phone GPS fixes")


class Verdict(BaseModel):
    flagged: bool
    reasons: list[str]


class RecordResult(BaseModel):
    workout: WorkoutItem
    verdict: Verdict
    detail: WorkoutDetail
    level_before: str
    level_after: str
    persona_before: str
    persona_after: str
    recommendations: list[Recommendation]


class Catalog(BaseModel):
    activities: list[str]
    gps_activities: list[str]
    exercises: dict[str, list[str]] = Field(description="exercises offered when logging each activity")
