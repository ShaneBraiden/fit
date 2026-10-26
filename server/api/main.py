"""FitMine API.

    uvicorn api.main:app --host 0.0.0.0 --port 8000      (run from server/)

/api/auth/*, /api/me/*   sign-up / sign-in, and the signed-in user's workouts and predictions
/api/catalog             activities and exercises the apps offer when logging a workout
/api/models/*            how each feature's model was trained (admins only)
/docs                    interactive OpenAPI documentation
"""
from __future__ import annotations

import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import state
from .routers import account, models

np.seterr(all="ignore")

app = FastAPI(title="FitMine API", version="2.0.0",
              description="Fitness tracking with predictions from data mining: fitness level, training persona, "
                          "exercise suggestions, data checks, weekly routines and popular routes.")
# The web app and the phone app call this API directly; auth uses bearer tokens, not cookies.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(account.router)
app.include_router(models.router)


@app.get("/api/health", tags=["account"])
def health():
    return {"ok": True, "ready": state.ready()}
