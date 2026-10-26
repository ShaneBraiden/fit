"""Exercise suggestions: which exercises are done together.

Each workout is a basket of the exercises logged in it. FP-Growth mines the
frequent itemsets from an FP-tree (no candidate generation), and rules A => B
with support, confidence and lift come from those itemsets. The app suggests B
when a user's recent workout contained A but not B.
"""
from __future__ import annotations

import time

import numpy as np

from ..algorithms.fpgrowth import fpgrowth
from ..algorithms.rules import closed_and_maximal, generate_rules
from ..data import store

MIN_SUPPORT = 0.02
MIN_CONFIDENCE = 0.6


def baskets(con) -> list[list[str]]:
    w = store.read("workouts", con)
    ex = store.read("exercises", con)
    ex = ex[ex.workout_id.isin(w.workout_id)]
    return ex.groupby("workout_id").exercise.apply(sorted).tolist()


def planted_recovery(rules: list[dict], planted: list[dict]) -> list[dict]:
    index = {(tuple(r["antecedent"]), tuple(r["consequent"])): (i, r) for i, r in enumerate(rules)}
    out = []
    for p in planted:
        key = (tuple(sorted(p["antecedent"])), tuple(sorted(p["consequent"])))
        hit = index.get(key)
        out.append({"antecedent": p["antecedent"], "consequent": p["consequent"], "found": hit is not None,
                    "rank": hit[0] + 1 if hit else None, "confidence": hit[1]["confidence"] if hit else None,
                    "lift": hit[1]["lift"] if hit else None, "support": hit[1]["support"] if hit else None})
    return out


def run(con) -> tuple[dict, list[dict]]:
    planted = store.planted(con)["rules"]
    tx = baskets(con)
    t0 = time.perf_counter()
    itemsets, stats = fpgrowth(tx, MIN_SUPPORT)
    ms_mine = (time.perf_counter() - t0) * 1000
    rules = generate_rules(itemsets, MIN_CONFIDENCE, 1.0)
    closed, maximal = closed_and_maximal(itemsets)
    items = sorted(((next(iter(k)), v) for k, v in itemsets.items() if len(k) == 1), key=lambda kv: -kv[1])
    rec = planted_recovery(rules, planted)
    report = {
        "params": {"algorithm": "fpgrowth", "min_support": MIN_SUPPORT, "min_confidence": MIN_CONFIDENCE},
        "n_transactions": len(tx), "avg_basket": float(np.mean([len(t) for t in tx])),
        "n_items": len(items), "n_itemsets": len(itemsets), "n_closed": len(closed), "n_maximal": len(maximal),
        "n_rules": len(rules), "ms_mine": round(ms_mine, 1), "fp_tree": stats,
        "items": [{"item": i, "support": s} for i, s in items],
        "rules": rules[:200],
        "planted": {"rules": rec, "recovered": sum(x["found"] for x in rec), "total": len(rec)},
    }
    return report, rules
