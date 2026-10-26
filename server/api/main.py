"""FitMine API.

    uvicorn api.main:app --host 0.0.0.0 --port 8000      (run from server/)

/api/*            analyst endpoints, one group per syllabus unit (web dashboard)
/api/users/*      mobile endpoints that apply the mined models to one user
/docs             interactive OpenAPI documentation
"""
from __future__ import annotations

import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import analyst, users

np.seterr(all="ignore")

app = FastAPI(title="FitMine API", version="1.0.0",
              description="Data mining over smart-fitness workout logs: preprocessing, OLAP, association rules, "
                          "classification, clustering, outlier detection, sequential and trajectory mining.")
# The dashboard (Vite dev server) and the phone app on the LAN call this API directly.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(analyst.router)
app.include_router(users.router)
