"""Analyst endpoints: one group per syllabus unit. GET returns the pipeline's
cached report; POST re-runs the mining with new parameters."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException

from fitmine.analyses import u3_association as U3
from fitmine.analyses import u4_classification as U4
from fitmine.analyses import u5_clustering as U5
from fitmine.analyses import u6_outliers as U6
from fitmine.analyses import u7_sequences_trajectories as U7
from fitmine.analyses.common import jsonable
from fitmine.data import store

from .. import state
from ..schemas import (AssociationRun, ClassifyRun, ClusterRun, HotspotRun, OlapQuery, OutlierRun, RouteRun,
                       SequenceRun)

router = APIRouter(prefix="/api")

SYLLABUS = [
    {"unit": "U1", "title": "Data preprocessing", "page": "preprocess",
     "mining": "Quality profile, label/unit cleaning, duplicate removal, imputation, smoothing, normalisation, "
               "discretisation, correlation, chi-square, PCA, sampling"},
    {"unit": "U2", "title": "Data warehouse & OLAP", "page": "olap",
     "mining": "Star schema, concept hierarchies, roll-up / drill-down / slice / dice / pivot, cuboid lattice"},
    {"unit": "U3", "title": "Association rules", "page": "association",
     "mining": "Apriori vs FP-Growth on exercise baskets; support, confidence, lift, leverage, conviction"},
    {"unit": "U4", "title": "Classification", "page": "classification",
     "mining": "Fitness level with ID3, C4.5, CART, Naive Bayes, k-NN; k-fold CV, confusion matrix, ROC"},
    {"unit": "U5", "title": "Clustering", "page": "clustering",
     "mining": "User personas with k-means, k-medoids, agglomerative, DBSCAN; elbow, silhouette, dendrogram"},
    {"unit": "U6", "title": "Outlier detection", "page": "outliers",
     "mining": "Faulty sensors and spoofed profiles with z-score, IQR, LOF, Isolation Forest, rules, ensemble"},
    {"unit": "U7", "title": "Sequences & trajectories", "page": "sequences",
     "mining": "GSP weekly routines, GPS hotspots, route clustering (Hausdorff + DBSCAN), run segmentation"},
]


@router.get("/health")
def health():
    return {"ok": True, "ready": state.ready()}


@router.get("/summary")
def summary():
    return {**state.report("summary"), "syllabus": SYLLABUS}


@router.get("/dataset/summary")
def dataset_summary(con=Depends(state.con)):
    tables = {}
    for t in ("users_raw", "workouts_raw", "exercises", "streams", "users", "workouts", "fact_workout", "dim_date",
              "dim_time", "dim_activity", "dim_location", "dim_user", "workout_features", "workout_flags",
              "user_insights", "workout_routes"):
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            tables[t] = {"rows": n, "columns": cols}
        except Exception:  # table not built yet
            continue
    u1 = state.report("u1")
    return {"tables": tables, "profile": u1["profile"], "raw": u1["raw"], "clean": u1["clean"],
            "planted": store.planted(con)}


# ----------------------------------------------------------------------------- U1

@router.get("/preprocess/report")
def preprocess_report():
    return state.report("u1")


# ----------------------------------------------------------------------------- U2

@router.get("/olap/meta")
def olap_meta():
    r = state.report("u2")
    return {k: r[k] for k in ("schema", "hierarchies", "measures", "default_spec", "lattice", "facts")}


@router.get("/olap/examples")
def olap_examples():
    return state.report("u2")["examples"]


@router.post("/olap/query")
def olap_query(q: OlapQuery):
    cube = state.cube()
    try:
        spec = cube.apply(q.spec, q.op)
        return jsonable(cube.query(spec))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"bad OLAP query: {e}")


# ----------------------------------------------------------------------------- U3

@router.get("/association/report")
def association_report():
    return state.report("u3")


@router.post("/association/run")
def association_run(p: AssociationRun, con=Depends(state.con)):
    tx = state.session_baskets()[p.basket]
    if p.algorithm == "apriori" and p.min_support < 0.003:
        raise HTTPException(400, "min_support below 0.003 makes Apriori too slow for a live request")
    planted = store.planted(con)["rules"] if p.basket == "session" else None
    return jsonable(U3.report(tx, p.algorithm, p.min_support, p.min_confidence, p.min_lift, planted))


# ----------------------------------------------------------------------------- U4

@router.get("/classify/report")
def classify_report():
    return state.report("u4")


@router.post("/classify/run")
def classify_run(p: ClassifyRun):
    feats = state.classification_data()
    params = {"max_depth": p.max_depth, "min_samples_split": p.min_samples_split, "prune": p.prune, "k": p.k,
              "weights": p.weights}
    out = U4.evaluate(feats, p.model, params, p.folds)
    final = U4.fit_final(feats, p.model, params)
    out["hidden_truth"] = U4.hidden_truth(feats, final)
    if p.model in ("id3", "c45", "cart"):
        t = final.tree
        out["tree"] = {"algorithm": p.model, "tree": t.to_dict(max_depth=6), "rules": t.rules()[:15],
                       "stats": t.stats(),
                       "importance": sorted(({"feature": k, "importance": v} for k, v in t.feature_importances_.items()),
                                            key=lambda d: -d["importance"])}
        if p.prune:
            out["tree"]["pruned_subtrees"] = getattr(final, "pruned_", 0)
    return jsonable(out)


# ----------------------------------------------------------------------------- U5

@router.get("/cluster/report")
def cluster_report():
    return state.report("u5")


@router.post("/cluster/run")
def cluster_run(p: ClusterRun):
    feats, Z, proj = state.clustering_data()
    params = p.model_dump(exclude={"algorithm"})
    res, _ = U5.run_algorithm(feats, Z, proj, p.algorithm, params)
    return jsonable(res)


# ----------------------------------------------------------------------------- U6

@router.get("/outliers/report")
def outliers_report():
    return state.report("u6")


@router.post("/outliers/run")
def outliers_run(p: OutlierRun):
    F, truth = state.outlier_data()
    params = {"z": p.z, "iqr_k": p.k, "lof_k": p.lof_k, "contamination": p.contamination, "n_trees": p.n_trees}
    ev, _, _ = U6.run_method(F, truth, p.method, params)
    return jsonable(ev)


@router.get("/outliers/workout/{workout_id}")
def outlier_workout(workout_id: int, con=Depends(state.con)):
    s = store.load_stream(con, workout_id)
    if s is None:
        raise HTTPException(404, "no such workout")
    w = store.read("workouts", con, "WHERE workout_id=?", (workout_id,))
    f = store.read("workout_features", con, "WHERE workout_id=?", (workout_id,))
    fl = store.read("workout_flags", con, "WHERE workout_id=?", (workout_id,))
    gt = store.read("gt_workouts", con, "WHERE workout_id=?", (workout_id,))
    return jsonable({"workout": w.to_dict("records")[0] if len(w) else None,
                     "features": f.drop(columns=["fingerprint"], errors="ignore").to_dict("records")[0] if len(f) else None,
                     "flag": fl.to_dict("records")[0] if len(fl) else None,
                     "truth": gt.fault_type.iat[0] if len(gt) else None,
                     "hr": s["hr"].astype(int).tolist(),
                     "lat": None if s["lat"] is None else np.round(s["lat"], 6).tolist(),
                     "lon": None if s["lon"] is None else np.round(s["lon"], 6).tolist()})


# ----------------------------------------------------------------------------- U7

@router.get("/sequences/report")
def sequences_report():
    return state.report("u7")["sequences"]


@router.post("/sequences/run")
def sequences_run(p: SequenceRun):
    (seqs, _), planted = state.sequence_data()
    if p.min_support < 0.01:
        raise HTTPException(400, "min_support below 0.01 explodes the candidate space for a live request")
    return jsonable(U7.sequences_report(seqs, p.min_support, p.max_gap, planted))


@router.get("/trajectories/report")
def trajectories_report():
    r = state.report("u7")
    return {k: v for k, v in r.items() if k != "sequences"}


@router.post("/trajectories/routes")
def trajectories_routes(p: RouteRun):
    w, streams, gt_route, rs = state.track_data()
    rep, _ = U7.route_clusters(w, streams, gt_route, eps=p.eps, min_samples=p.min_samples, H=rs["H"], ids=rs["ids"])
    return jsonable(rep)


@router.post("/trajectories/hotspots")
def trajectories_hotspots(p: HotspotRun):
    w, streams, _, _ = state.track_data()
    return jsonable(U7.hotspots(w, streams, eps=p.eps, min_samples=p.min_samples))


@router.get("/trajectories/{workout_id}/segments")
def trajectory_segments(workout_id: int, beta: float = 1.0, con=Depends(state.con)):
    r = U7.segments_for(con, workout_id, beta)
    if r is None:
        raise HTTPException(404, "workout has no GPS track")
    return jsonable(r)


# ----------------------------------------------------------------------------- verification

@router.get("/verify")
def verify_report():
    return state.report("verify")
