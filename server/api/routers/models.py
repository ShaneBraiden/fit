"""Model pages for admins: how each app feature's model was trained and how well it
recovers the planted truth. Reports are written by the pipeline (artifacts/*.json)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import state
from .account import admin_user

router = APIRouter(prefix="/api/models", tags=["models"], dependencies=[Depends(admin_user)])

REPORTS = ("summary", "cleaning", "suggestions", "fitness_level", "personas", "data_checks", "routines_routes",
           "verify")


@router.get("/{name}")
def model_report(name: str):
    if name not in REPORTS:
        raise HTTPException(404, f"no model report '{name}'")
    return state.report(name)
