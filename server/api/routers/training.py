"""The signed-in user's weekly plan, streak and muscle progress.

`today` (YYYY-MM-DD, the phone's or browser's local date) decides which day is "today",
so the streak and the week match the user's calendar rather than the server's time zone.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from fitmine import training as TR

from ..schemas import MuscleReport, PlanIn, PlanWeek, Streak
from .account import current_user, db

router = APIRouter(prefix="/api/me", tags=["account"])


@router.get("/plan", response_model=PlanWeek)
def plan(today: str | None = None, uid: int = Depends(current_user), con=Depends(db)):
    return TR.plan_week(con, uid, TR.parse_today(today))


@router.put("/plan", response_model=PlanWeek)
def save_plan(req: PlanIn, today: str | None = None, uid: int = Depends(current_user), con=Depends(db)):
    TR.save_plan(con, uid, req.model_dump())
    return TR.plan_week(con, uid, TR.parse_today(today))


@router.delete("/plan", status_code=204)
def delete_plan(uid: int = Depends(current_user), con=Depends(db)):
    TR.delete_plan(con, uid)
    return Response(status_code=204)


@router.get("/streak", response_model=Streak)
def streak(today: str | None = None, uid: int = Depends(current_user), con=Depends(db)):
    return TR.streak(con, uid, TR.parse_today(today))


@router.get("/muscles", response_model=MuscleReport)
def muscles(today: str | None = None, weeks: int = 8, uid: int = Depends(current_user), con=Depends(db)):
    return TR.muscles(con, uid, TR.parse_today(today), weeks=max(2, min(weeks, 26)))
