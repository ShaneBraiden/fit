"""Request and response models. The account endpoints are fully typed so the
web and phone apps can generate TypeScript types from /openapi.json; the admin
model endpoints return the pipeline's report dictionaries."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class ExerciseLoad(BaseModel):
    exercise: str
    sets: int | None = Field(None, ge=1, le=30)
    reps: int | None = Field(None, ge=1, le=200)
    weight_kg: float | None = Field(None, ge=0, le=600)


class WorkoutDetail(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
    workout: WorkoutItem
    exercises: list[str]
    loads: list[ExerciseLoad] = Field(default_factory=list, description="sets, reps and weight where they were logged")
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
    plan_day: str | None = Field(None, max_length=30, description="the day of the user's plan this workout was")
    distance_km: float | None = Field(None, ge=0, le=400, description="for workouts without a GPS track")
    avg_hr: float | None = Field(None, ge=30, le=230)
    max_hr: float | None = Field(None, ge=30, le=240)
    calories: float | None = Field(None, ge=0, le=6000)
    exercises: list[str] = Field(default_factory=list, max_length=40)
    loads: list[ExerciseLoad] = Field(default_factory=list, max_length=40,
                                      description="optional sets / reps / kg per exercise")
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


class ExerciseMuscles(BaseModel):
    primary: list[str]
    secondary: list[str]


class PlanDay(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)  # always sent in responses
    label: str = Field(max_length=30)
    activity: Literal["Run", "Walk", "Cycle", "Swim", "Strength", "HIIT", "Yoga", "Rest"]
    focus: list[str] = Field(default_factory=list, max_length=10, description="muscles this day trains")
    exercises: list[str] = Field(default_factory=list, max_length=20)


class PlanTemplate(BaseModel):
    key: str
    name: str
    days: list[PlanDay]


class Catalog(BaseModel):
    activities: list[str]
    gps_activities: list[str]
    exercises: dict[str, list[str]] = Field(description="exercises offered when logging each activity")
    muscles: list[str]
    muscle_groups: dict[str, str]
    exercise_muscles: dict[str, ExerciseMuscles]
    plan_templates: list[PlanTemplate]


# ----------------------------------------------------------------------------- plans, streak, muscles

class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    days: list[PlanDay] = Field(min_length=7, max_length=7, description="Monday to Sunday")


class Plan(PlanIn):
    updated_at: str


class PlanWeekDay(BaseModel):
    date: str
    weekday: int = Field(description="0 = Monday")
    day: PlanDay | None
    today: bool
    done: bool
    workouts: list[int]


class PlanWeek(BaseModel):
    plan: Plan | None
    week: list[PlanWeekDay]
    planned: int
    done: int
    today: PlanDay | None


class StreakDay(BaseModel):
    date: str
    workouts: int
    minutes: float


class StreakWeekDay(BaseModel):
    date: str
    status: Literal["done", "rest", "today", "upcoming", "missed"]


class Streak(BaseModel):
    current: int
    longest: int
    today_done: bool
    at_risk: bool = Field(description="a streak is running but nothing is logged today yet")
    rest_weekdays: list[int]
    week: list[StreakWeekDay]
    this_week_sessions: int = Field(description="days trained this week")
    weekly_goal: int | None
    active_days_total: int
    days: list[StreakDay] = Field(description="every day trained in the last 400 days")


class MuscleWeek(BaseModel):
    week: str = Field(description="the Monday of the week")
    sets: float
    volume_kg: float
    sessions: int


class LiftPoint(BaseModel):
    date: str
    e1rm: float
    weight_kg: float
    reps: int


class ExerciseProgress(BaseModel):
    exercise: str
    sessions: int
    best_e1rm: float | None
    first_e1rm: float | None
    latest_e1rm: float | None
    change_pct: float | None
    history: list[LiftPoint]


class MuscleProgress(BaseModel):
    muscle: str
    group: str
    sets_this_week: float
    sets_avg: float
    target_low: int
    target_high: int
    volume_status: Literal["low", "on_target", "high"]
    trend_pct: float | None = Field(description="sets in the last 4 weeks vs the 4 before")
    last_trained: str | None
    days_since: int | None
    status: Literal["not_trained", "recovering", "ready", "overdue"]
    weekly: list[MuscleWeek]
    exercises: list[ExerciseProgress]


class MuscleReport(BaseModel):
    weeks: list[str]
    muscles: list[MuscleProgress]
    total_sets_this_week: float
    sets_target: list[int]


# ----------------------------------------------------------------------------- friends

class FriendRequestIn(BaseModel):
    handle: str = Field(min_length=3, max_length=200, description="their email or friend code")


class FriendSummary(BaseModel):
    user_id: int
    name: str
    streak: int
    longest_streak: int
    today_done: bool
    week_sessions: int
    week_minutes: float
    four_week_minutes: float
    last_workout: str | None


class PendingFriend(BaseModel):
    user_id: int
    name: str
    since: str


class Friends(BaseModel):
    code: str
    me: FriendSummary
    friends: list[FriendSummary]
    incoming: list[PendingFriend]
    outgoing: list[PendingFriend]
    leaderboard: list[int] = Field(description="user ids, most minutes this week first (you included)")


class FriendRequestResult(BaseModel):
    status: Literal["pending", "accepted"]


class WeekTotal(BaseModel):
    week: str
    minutes: float
    sessions: int


class Snapshot(FriendSummary):
    level: str
    persona: str
    stats: dict[str, float | None]
    weekly: list[WeekTotal]
    muscle_sets: dict[str, float] = Field(description="average sets per week over the last 4 weeks")


class Comparison(BaseModel):
    me: Snapshot
    friend: Snapshot
