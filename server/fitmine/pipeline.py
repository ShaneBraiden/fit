"""Run the whole mining pipeline.

    python -m fitmine.pipeline run [--seed 42] [--users 1000] [--regenerate] [--skip-verify]

generate -> U1 clean -> U2 warehouse -> U3 rules -> U4 classify -> U5 cluster
-> U6 outliers -> U7 sequences & trajectories -> per-user insights -> verification.
Reports go to server/artifacts/*.json, trained models to server/artifacts/models.pkl.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from . import config as C
from .analyses import (u1_preprocess, u2_warehouse, u3_association, u4_classification, u5_clustering,
                       u6_outliers, u7_sequences_trajectories, verify)
from .analyses.common import jsonable, save_json, save_pickle
from .data import generator, store


def _step(name: str, timings: dict):
    class _S:
        def __enter__(self):
            self.t = time.perf_counter()
            print(f"  {name} ...", end="", flush=True)

        def __exit__(self, *exc):
            timings[name] = round(time.perf_counter() - self.t, 1)
            print(f" {timings[name]}s", flush=True)
    return _S()


def run(seed: int = C.SEED, n_users: int = C.N_USERS, regenerate: bool = False, skip_verify: bool = False) -> dict:
    timings: dict = {}
    con = store.connect()
    print("FitMine pipeline")
    if regenerate or not store.exists("users_raw"):
        with _step("generate synthetic dataset", timings):
            store.save_dataset(generator.generate(seed, n_users), con)
    with _step("U1 preprocessing", timings):
        r1 = u1_preprocess.run(con)
        save_json("u1", r1)
    with _step("U2 warehouse / OLAP", timings):
        r2 = u2_warehouse.run(con)
        save_json("u2", r2)
    with _step("U3 association rules", timings):
        r3 = u3_association.run(con)
        save_json("u3", r3)
    with _step("U4 classification", timings):
        r4, classifier, feats = u4_classification.run(con)
        save_json("u4", r4)
    with _step("U5 clustering", timings):
        r5, cluster_model, personas = u5_clustering.run(con)
        save_json("u5", r5)
    with _step("U6 outlier detection", timings):
        r6, flags, user_flags, outlier_model = u6_outliers.run(con)
        save_json("u6", r6)
    with _step("U7 sequences & trajectories", timings):
        r7, u7_model, u7_extra = u7_sequences_trajectories.run(con)
        save_json("u7", r7)
        save_pickle("route_state", u7_extra["route_state"])
        store.write(pd.DataFrame([{"workout_id": wid, "route_cluster": None if r is None else r[0],
                                   "route_name": None if r is None else r[1],
                                   "hausdorff_m": None if r is None else round(r[2], 1)}
                                  for wid, r in u7_extra["route_of"].items()]), "workout_routes", con)
    with _step("per-user insights", timings):
        insights = build_insights(feats, classifier, personas, user_flags, flags, u7_extra)
        store.write(insights, "user_insights", con)
    save_pickle("models", {
        "classifier": classifier, "classifier_name": r4["best_model"], "cluster": cluster_model,
        "outliers": outlier_model, "routes": u7_model["routes"], "patterns": u7_model["patterns"],
        "session_rules": r3["session"]["rules"],
    })
    if not skip_verify:
        with _step("verification vs libraries", timings):
            rv = verify.run(con)
            save_json("verify", rv)
    summary = build_summary(r1, r3, r4, r5, r6, r7, timings, None if skip_verify else rv)
    save_json("summary", summary)
    con.close()
    print(json.dumps(jsonable(summary["recovery"]), indent=2))
    return summary


def build_insights(feats, classifier, personas, user_flags, flags, u7_extra) -> pd.DataFrame:
    proba = classifier.predict_proba(feats)
    pred = classifier.classes_[proba.argmax(1)]
    fl = flags.merge(store.read("workouts")[["workout_id", "user_id"]], on="workout_id")
    n_flag = fl[fl.flagged.astype(bool)].groupby("user_id").size()
    uf = user_flags.set_index("user_id")
    p = personas.set_index("user_id")
    rows = []
    for i, r in enumerate(feats.itertuples()):
        uid = int(r.user_id)
        assessed = r.assessed_level if isinstance(r.assessed_level, str) else None
        rows.append({
            "user_id": uid, "level": assessed or str(pred[i]), "level_source": "assessed" if assessed else "predicted",
            "predicted_level": str(pred[i]),
            "level_proba": json.dumps({str(c): round(float(v), 4) for c, v in zip(classifier.classes_, proba[i])}),
            "cluster": int(p.cluster[uid]), "persona": p.persona[uid], "similar": json.dumps(p.similar[uid]),
            "routines": json.dumps(jsonable(u7_extra["routines"].get(uid, []))),
            "spoof_flag": bool(uf.flagged.get(uid, False)), "spoof_reasons": json.dumps(uf.reasons.get(uid, [])),
            "flagged_workouts": int(n_flag.get(uid, 0)),
        })
    return pd.DataFrame(rows)


def build_summary(r1, r3, r4, r5, r6, r7, timings, rv) -> dict:
    km = r5["results"]["kmeans"]
    ens = r6["methods"]["ensemble"]
    return {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "timings_s": timings,
        "dataset": {"users": r1["clean"]["users"], "workouts": r1["clean"]["workouts"],
                    "raw_workouts": r1["raw"]["workouts"]},
        "recovery": {
            "U1 duplicate removal (precision/recall)": [r1["duplicates"]["precision"], r1["duplicates"]["recall"]],
            "U1 avg HR imputation RMSE (chosen / mean)": [
                min(m["rmse"] for m in r1["imputation"][0]["methods"]),
                next(m["rmse"] for m in r1["imputation"][0]["methods"] if m["method"] == "mean")],
            "U3 planted exercise rules recovered": f"{r3['session']['planted']['recovered']}/"
                                                   f"{r3['session']['planted']['total']}",
            "U4 best classifier / CV macro-F1": [r4["best_model"],
                                                 next(c["macro"]["f1"] for c in r4["comparison"]
                                                      if c["model"] == r4["best_model"])],
            "U4 accuracy on unlabelled users vs hidden level": r4["hidden_truth"]["accuracy"],
            "U5 k-means ARI vs planted personas": km["external"]["ari"],
            "U6 workout faults ensemble (precision/recall)": [ens["precision"], ens["recall"]],
            "U6 spoofed profiles (precision/recall)": [
                r6["users"]["evaluation"]["rules + consistency + clones"]["precision"],
                r6["users"]["evaluation"]["rules + consistency + clones"]["recall"]],
            "U7 planted weekly routines found": f"{sum(p['found'] for p in r7['sequences']['planted'])}/"
                                                f"{len(r7['sequences']['planted'])}",
            "U7 popular routes found": f"{r7['routes']['evaluation']['routes_found']}/"
                                       f"{r7['routes']['evaluation']['planted_routes']}",
            "U7 run segmentation boundary F1": r7["segmentation"]["boundary_f1"],
            "Verification checks passed": None if rv is None else f"{rv['passed']}/{rv['total']}",
        },
    }


def main():
    ap = argparse.ArgumentParser(prog="python -m fitmine.pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="generate data (if needed) and run every unit")
    r.add_argument("--seed", type=int, default=C.SEED)
    r.add_argument("--users", type=int, default=C.N_USERS)
    r.add_argument("--regenerate", action="store_true", help="rebuild the synthetic dataset")
    r.add_argument("--skip-verify", action="store_true")
    a = ap.parse_args()
    if a.cmd == "run":
        np.seterr(all="ignore")
        run(a.seed, a.users, a.regenerate, a.skip_verify)


if __name__ == "__main__":
    main()
