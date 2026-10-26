"""Run the whole mining pipeline.

    python -m fitmine.pipeline run [--seed 42] [--users 1000] [--regenerate] [--skip-verify]

generate -> clean -> exercise suggestions -> fitness level -> personas -> data checks
-> routines & routes -> per-user insights -> verification.
Reports go to server/artifacts/*.json, trained models to server/artifacts/models.pkl.
Accounts and their own (live) workouts are kept in separate tables that this never touches.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from . import config as C
from .analyses import cleaning, data_checks, fitness_level, personas, routines_routes, suggestions, verify
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
    with _step("data cleaning", timings):
        r_clean = cleaning.run(con)
        save_json("cleaning", r_clean)
    with _step("exercise suggestions (FP-Growth)", timings):
        r_sugg, rules = suggestions.run(con)
        save_json("suggestions", r_sugg)
    with _step("fitness level (C4.5)", timings):
        r_level, classifier, feats = fitness_level.run(con)
        save_json("fitness_level", r_level)
    with _step("personas (k-means++)", timings):
        r_pers, cluster_model, user_personas = personas.run(con)
        save_json("personas", r_pers)
    with _step("data checks", timings):
        r_checks, flags, user_flags, check_model = data_checks.run(con)
        save_json("data_checks", r_checks)
    with _step("routines & routes", timings):
        r_rr, rr_model, rr_extra = routines_routes.run(con)
        save_json("routines_routes", r_rr)
        save_pickle("route_state", rr_extra["route_state"])
        store.write(pd.DataFrame([{"workout_id": wid, "route_cluster": None if r is None else r[0],
                                   "route_name": None if r is None else r[1],
                                   "hausdorff_m": None if r is None else round(r[2], 1)}
                                  for wid, r in rr_extra["route_of"].items()]), "workout_routes", con)
    with _step("per-user insights", timings):
        insights = build_insights(feats, classifier, user_personas, user_flags, flags, rr_extra)
        store.write(insights, "user_insights", con)
    save_pickle("models", {
        "classifier": classifier, "cluster": cluster_model, "outliers": check_model,
        "routes": rr_model["routes"], "patterns": rr_model["patterns"], "session_rules": rules,
    })
    if not skip_verify:
        with _step("verification vs libraries", timings):
            rv = verify.run(con)
            save_json("verify", rv)
    summary = build_summary(r_clean, r_sugg, r_level, r_pers, r_checks, r_rr, timings, None if skip_verify else rv)
    save_json("summary", summary)
    con.close()
    print(json.dumps(jsonable(summary["recovery"]), indent=2))
    return summary


def build_insights(feats, classifier, user_personas, user_flags, flags, rr_extra) -> pd.DataFrame:
    proba = classifier.predict_proba(feats)
    pred = classifier.classes_[proba.argmax(1)]
    fl = flags.merge(store.read("workouts")[["workout_id", "user_id"]], on="workout_id")
    n_flag = fl[fl.flagged.astype(bool)].groupby("user_id").size()
    uf = user_flags.set_index("user_id")
    p = user_personas.set_index("user_id")
    rows = []
    for i, r in enumerate(feats.itertuples()):
        uid = int(r.user_id)
        assessed = r.assessed_level if isinstance(r.assessed_level, str) else None
        rows.append({
            "user_id": uid, "level": assessed or str(pred[i]), "level_source": "assessed" if assessed else "predicted",
            "predicted_level": str(pred[i]),
            "level_proba": json.dumps({str(c): round(float(v), 4) for c, v in zip(classifier.classes_, proba[i])}),
            "cluster": int(p.cluster[uid]), "persona": p.persona[uid],
            "routines": json.dumps(jsonable(rr_extra["routines"].get(uid, []))),
            "spoof_flag": bool(uf.flagged.get(uid, False)), "spoof_reasons": json.dumps(uf.reasons.get(uid, [])),
            "flagged_workouts": int(n_flag.get(uid, 0)),
        })
    return pd.DataFrame(rows)


def build_summary(r_clean, r_sugg, r_level, r_pers, r_checks, r_rr, timings, rv) -> dict:
    ens = r_checks["methods"]["ensemble"]
    return {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "timings_s": timings,
        "dataset": {"users": r_clean["clean"]["users"], "workouts": r_clean["clean"]["workouts"],
                    "raw_workouts": r_clean["raw"]["workouts"]},
        "recovery": {
            "Cleaning: duplicate removal (precision/recall)": [r_clean["duplicates"]["precision"],
                                                               r_clean["duplicates"]["recall"]],
            "Cleaning: avg HR imputation RMSE (kNN / mean baseline)": [
                r_clean["imputation"][0]["methods"][0]["rmse"], r_clean["imputation"][0]["methods"][1]["rmse"]],
            "Suggestions: planted exercise rules recovered": f"{r_sugg['planted']['recovered']}/"
                                                             f"{r_sugg['planted']['total']}",
            "Fitness level: C4.5 CV accuracy / macro-F1": [r_level["cv"]["accuracy"], r_level["cv"]["macro"]["f1"]],
            "Fitness level: accuracy on unassessed users vs hidden level": r_level["hidden_truth"]["accuracy"],
            "Personas: k-means ARI vs planted personas": r_pers["external"]["ari"],
            "Data checks: faulty workouts (precision/recall)": [ens["precision"], ens["recall"]],
            "Data checks: spoofed profiles (precision/recall)": [r_checks["users"]["evaluation"]["precision"],
                                                                 r_checks["users"]["evaluation"]["recall"]],
            "Routines: planted weekly routines found": f"{sum(p['found'] for p in r_rr['sequences']['planted'])}/"
                                                       f"{len(r_rr['sequences']['planted'])}",
            "Routes: popular routes found": f"{r_rr['routes']['evaluation']['routes_found']}/"
                                            f"{r_rr['routes']['evaluation']['planted_routes']}",
            "Run phases: segmentation boundary F1": r_rr["segmentation"]["boundary_f1"],
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
