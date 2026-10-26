"""Weekly routines and GPS routes.

Routines   one data sequence per user-week; elements are the session types done on
           the same day (time = day of week). GSP with a max-gap constraint finds the
           orders people repeat; a user "follows" a routine in at least half their weeks.
Routes     tracks resampled to 20 points, pairwise Hausdorff distance, DBSCAN on the
           precomputed matrix; clusters named after the nearest public landmark.
Phases     binary segmentation of each run's GPS speed profile, labelled warm-up /
           steady / fast / recovery / stop / cool-down.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .. import config as C
from ..algorithms import trajectory as T
from ..algorithms.dbscan import DBSCAN
from ..algorithms.gsp import contains, fmt, gsp
from ..data import geo, store

DT = C.STREAM_INTERVAL_S
M_POINTS = 20
PHASE_COARSE = {"warmup": "warmup", "steady": "steady", "long": "steady", "tempo": "steady", "stop": "stop",
                "interval_fast": "fast", "interval_recovery": "recovery", "cooldown": "cooldown"}


# ----------------------------------------------------------------------------- sequences

def week_sequences(con) -> tuple[list, list]:
    w = store.read("workouts", con)
    flags = store.read("workout_flags", con) if store.exists("workout_flags") else None
    if flags is not None:
        w = w[~w.workout_id.isin(flags.workout_id[flags.flagged.astype(bool)])]
    return sequences_of(w)


def sequences_of(w: pd.DataFrame) -> tuple[list, list]:
    """One day-ordered sequence of session types per (user, ISO week)."""
    w = w.copy()
    w["start_time"] = pd.to_datetime(w.start_time)
    w["week"] = w.start_time.dt.strftime("%G-W%V")
    w["dow"] = w.start_time.dt.dayofweek
    seqs, keys = [], []
    for (uid, wk), g in w.groupby(["user_id", "week"]):
        seq = [(int(d), sorted(set(gg.session_type))) for d, gg in g.groupby("dow")]
        seqs.append(seq)
        keys.append((int(uid), wk))
    return seqs, keys


def sequences_report(seqs, min_support=0.025, max_gap=4, planted=None, max_len=5) -> dict:
    t = time.perf_counter()
    pats, stats = gsp(seqs, min_support, max_gap=max_gap, max_len=max_len)
    ms = (time.perf_counter() - t) * 1000
    rows = sorted(({"pattern": [list(e) for e in p], "text": fmt(p), "length": sum(len(e) for e in p),
                    "elements": len(p), "support": s} for p, s in pats.items()),
                  key=lambda r: (-r["length"], -r["support"]))
    out = {"params": {"min_support": min_support, "max_gap": max_gap}, "n_sequences": len(seqs),
           "avg_elements": float(np.mean([len(s) for s in seqs])), "n_patterns": len(pats), "ms": round(ms, 1),
           "stats": stats, "patterns": [r for r in rows if r["elements"] > 1][:150],
           "singletons": [r for r in rows if r["elements"] == 1]}
    if planted:
        out["planted"] = [{"pattern": p, "text": fmt(tuple((x,) for x in p)),
                           "support": pats.get(tuple((x,) for x in p)),
                           "found": tuple((x,) for x in p) in pats} for p in planted]
    return out


def user_routines(seqs, keys, patterns: list[dict], top: int = 3) -> dict[int, list]:
    """For each user: mined multi-element patterns they follow, with the share of their weeks."""
    cand = [tuple(tuple(e) for e in r["pattern"]) for r in patterns if r["elements"] >= 2][:60]
    by_user: dict[int, list] = {}
    for (uid, _), s in zip(keys, seqs):
        by_user.setdefault(uid, []).append([(t, frozenset(i)) for t, i in s])
    out = {}
    for uid, weeks in by_user.items():
        scored = []
        for p in cand:
            share = sum(contains(s, p, 4) for s in weeks) / len(weeks)
            if share >= 0.5:
                scored.append({"text": fmt(p), "pattern": [list(e) for e in p], "weeks": share})
        scored.sort(key=lambda r: (-len(r["pattern"]), -r["weeks"]))
        out[uid] = scored[:top]
    return out


# ----------------------------------------------------------------------------- trajectories

def gps_tracks(con, exclude_flagged=True) -> tuple[pd.DataFrame, dict]:
    w = store.read("workouts", con)
    w = w[w.has_gps.astype(bool)]
    if exclude_flagged and store.exists("workout_flags"):
        fl = store.read("workout_flags", con)
        w = w[~w.workout_id.isin(fl.workout_id[fl.flagged.astype(bool)])]
    streams = store.load_streams(con, w.workout_id)
    return w[w.workout_id.isin(list(streams))], streams


def resampled(streams, ids) -> np.ndarray:
    return np.stack([T.resample(T.xy(streams[i]["lat"], streams[i]["lon"]), M_POINTS) for i in ids]).astype(np.float32)


def route_clusters(w, streams, gt_route: pd.Series, max_tracks=1000, eps=150.0, min_samples=8, seed=0,
                   H=None, ids=None) -> tuple[dict, dict]:
    rng = np.random.default_rng(seed)
    if ids is None:
        ids = np.sort(rng.choice(w.workout_id.to_numpy(), min(max_tracks, len(w)), replace=False))
    tracks = resampled(streams, ids)
    t = time.perf_counter()
    if H is None:
        H = T.hausdorff_matrix(tracks)
    ms_h = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    labels = DBSCAN(eps, min_samples, "precomputed").fit(H).labels_
    ms_d = (time.perf_counter() - t) * 1000
    truth = gt_route.reindex(ids).to_numpy()
    acts = w.set_index("workout_id").activity.reindex(ids).to_numpy()
    clusters, medoids = [], []
    for c in sorted(set(labels.tolist()) - {-1}):
        members = np.where(labels == c)[0]
        med = members[H[np.ix_(members, members)].sum(1).argmin()]
        lat, lon = geo.to_latlon(tracks[med][:, 0], tracks[med][:, 1])
        name, dist = geo.nearest_landmark(float(lat.mean()), float(lon.mean()))
        maj = pd.Series(truth[members]).value_counts()
        clusters.append({"cluster": int(c), "size": int(len(members)), "landmark": name, "landmark_m": round(dist),
                         "medoid_workout": int(ids[med]), "track": np.c_[lat, lon].round(5).tolist(),
                         "activities": pd.Series(acts[members]).value_counts().to_dict(),
                         "majority_route": int(maj.index[0]), "purity": float(maj.iloc[0] / len(members))})
        medoids.append(tracks[med])
    popular = truth < 100
    in_cluster = labels != -1
    # A popular-route track is recovered when it lands in the cluster whose majority is its own route.
    maj_of = {c["cluster"]: c["majority_route"] for c in clusters}
    recovered = np.array([in_cluster[i] and maj_of.get(labels[i]) == truth[i] for i in range(len(ids))])
    names = {r["id"]: r["name"] for r in store.planted()["popular_routes"]}
    report = {
        "params": {"eps_m": eps, "min_samples": min_samples, "resample_points": M_POINTS},
        "n_tracks": int(len(ids)), "n_clusters": len(clusters), "noise": int((~in_cluster).sum()),
        "ms_hausdorff": round(ms_h, 1), "ms_dbscan": round(ms_d, 1),
        "clusters": sorted(clusters, key=lambda c: -c["size"]),
        "evaluation": {
            "planted_routes": len(names),
            "routes_found": len({c["majority_route"] for c in clusters if c["majority_route"] < 100}),
            "purity": float(np.mean([c["purity"] for c in clusters])) if clusters else 0.0,
            "popular_recall": float(recovered[popular].mean()) if popular.any() else 0.0,
            "personal_as_noise": float((~in_cluster[~popular]).mean()) if (~popular).any() else 0.0,
            "route_names": {int(k): v for k, v in names.items()},
        },
    }
    model = {"medoids": np.stack(medoids) if medoids else np.zeros((0, M_POINTS, 2)),
             "names": [c["landmark"] for c in sorted(clusters, key=lambda c: c["cluster"])],
             "clusters": [c["cluster"] for c in sorted(clusters, key=lambda c: c["cluster"])], "eps": eps}
    return report, {"model": model, "H": H, "ids": ids}


def assign_routes(model: dict, tracks: np.ndarray) -> list[tuple[int, str, float] | None]:
    if len(model["medoids"]) == 0:
        return [None] * len(tracks)
    H = T.hausdorff_matrix(tracks, model["medoids"])
    out = []
    for row in H:
        j = int(row.argmin())
        out.append((model["clusters"][j], model["names"][j], float(row[j]))
                   if row[j] <= 1.5 * model["eps"] else None)
    return out


def segment_one(s: dict, beta=1.0, min_size=2) -> dict:
    return T.segment_track(s["lat"], s["lon"], DT, beta, min_size)


def segmentation_eval(w, streams, gt_seg: pd.DataFrame, gt_w: pd.DataFrame, n=600, beta=1.0, seed=0) -> dict:
    rng = np.random.default_rng(seed)
    runs = w[w.activity == "Run"].workout_id.to_numpy()
    have_truth = set(gt_seg.workout_id)
    runs = [r for r in runs if r in have_truth]
    ids = rng.choice(runs, min(n, len(runs)), replace=False)
    seg_by = {k: g.sort_values("start_idx") for k, g in gt_seg[gt_seg.workout_id.isin(ids)].groupby("workout_id")}
    f1s, precs, recs, acc, kind_ok = [], [], [], [], []
    stype = gt_w.set_index("workout_id").session_type
    t = time.perf_counter()
    for wid in ids:
        r = segment_one(streams[wid], beta)
        g = seg_by[wid]
        truth_cps = g.start_idx.iloc[1:].tolist()
        p, rc, f = T.boundary_f1(r["change_points"], truth_cps, tol=2)
        precs.append(p), recs.append(rc), f1s.append(f)
        n_s = len(r["speed"])
        tl = np.empty(n_s, dtype=object)
        for a, b, ph in g[["start_idx", "end_idx", "phase"]].itertuples(index=False):
            tl[a:b] = PHASE_COARSE[ph]
        pl = np.empty(n_s, dtype=object)
        for sg in r["segments"]:
            pl[sg["start"]:sg["end"]] = sg["phase"]
        acc.append(float((tl == pl).mean()))
        kind_ok.append((r["kind"] == "intervals") == (stype.get(wid) == "IntervalRun"))
    ms = (time.perf_counter() - t) * 1000
    return {"n_runs": len(ids), "beta": beta, "boundary_precision": float(np.mean(precs)),
            "boundary_recall": float(np.mean(recs)), "boundary_f1": float(np.mean(f1s)),
            "phase_accuracy": float(np.mean(acc)), "interval_detection_accuracy": float(np.mean(kind_ok)),
            "ms_per_run": round(ms / len(ids), 2)}


def run(con) -> tuple[dict, dict, dict]:
    planted = store.planted(con)
    seqs, keys = week_sequences(con)
    seq = sequences_report(seqs, 0.025, 4, planted["sequences"])
    routines = user_routines(seqs, keys, seq["patterns"])
    w, streams = gps_tracks(con)
    gt_w = store.read("gt_workouts", con)
    gt_route = gt_w.set_index("workout_id").route_id
    routes, rstate = route_clusters(w, streams, gt_route)
    gt_seg = store.read("gt_segments", con)
    seg = segmentation_eval(w, streams, gt_seg, gt_w)
    # Route of every GPS workout for the app
    ids = w.workout_id.to_numpy()
    assigned = assign_routes(rstate["model"], resampled(streams, ids))
    route_of = {int(i): a for i, a in zip(ids, assigned)}
    example = int(w[(w.activity == "Run")].merge(gt_w[gt_w.session_type == "IntervalRun"], on="workout_id")
                  .workout_id.iloc[0])
    report = {"sequences": seq, "routes": routes, "segmentation": seg, "example_workout": example}
    return report, {"routes": rstate["model"], "patterns": seq["patterns"]}, {"routines": routines,
                                                                              "route_of": route_of,
                                                                              "route_state": rstate}
