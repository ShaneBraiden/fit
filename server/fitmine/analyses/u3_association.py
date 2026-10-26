"""U3 Association rules: which exercises are done together.

Two basket definitions:
  session    the exercises logged in one workout (what is done *together*)
  user_week  the session types one user did in one week (how training is *combined*)
Apriori and FP-Growth must return the same itemsets; they differ in work done
(candidates per level vs FP-tree size) and runtime, which the report compares.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from ..algorithms.apriori import apriori
from ..algorithms.fpgrowth import fpgrowth, tree_preview
from ..algorithms.rules import closed_and_maximal, generate_rules
from ..data import store


def baskets(con, kind: str = "session") -> list[list[str]]:
    w = store.read("workouts", con)
    if kind == "session":
        ex = store.read("exercises", con)
        ex = ex[ex.workout_id.isin(w.workout_id)]
        return ex.groupby("workout_id").exercise.apply(sorted).tolist()
    w["start_time"] = pd.to_datetime(w.start_time)
    w["week"] = w.start_time.dt.strftime("%G-W%V")
    return w.groupby(["user_id", "week"]).session_type.apply(lambda s: sorted(set(s))).tolist()


def mine(tx, algorithm: str, min_support: float, min_confidence: float, min_lift: float = 1.0,
         max_len: int | None = None) -> dict:
    t0 = time.perf_counter()
    if algorithm == "apriori":
        itemsets, stats = apriori(tx, min_support, max_len)
    else:
        itemsets, stats = fpgrowth(tx, min_support, max_len)
    t_mine = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    rules = generate_rules(itemsets, min_confidence, min_lift)
    t_rules = (time.perf_counter() - t1) * 1000
    closed, maximal = closed_and_maximal(itemsets)
    by_size: dict[int, int] = {}
    for s in itemsets:
        by_size[len(s)] = by_size.get(len(s), 0) + 1
    return {"itemsets": itemsets, "rules": rules, "stats": stats, "ms_mine": round(t_mine, 1),
            "ms_rules": round(t_rules, 1), "n_closed": len(closed), "n_maximal": len(maximal),
            "by_size": by_size}


def rule_graph(rules: list[dict], top: int = 30) -> dict:
    """Bipartite item/rule graph of the strongest rules (arules-style 'graph' plot)."""
    nodes, links = {}, []
    for i, r in enumerate(rules[:top]):
        rid = f"R{i + 1}"
        nodes[rid] = {"id": rid, "kind": "rule", "lift": r["lift"], "confidence": r["confidence"],
                      "support": r["support"]}
        for it in r["antecedent"]:
            nodes.setdefault(it, {"id": it, "kind": "item"})
            links.append({"source": it, "target": rid})
        for it in r["consequent"]:
            nodes.setdefault(it, {"id": it, "kind": "item"})
            links.append({"source": rid, "target": it})
    return {"nodes": list(nodes.values()), "links": links}


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


def report(tx, algorithm="fpgrowth", min_support=0.02, min_confidence=0.6, min_lift=1.0, planted=None,
           max_rules: int = 300) -> dict:
    r = mine(tx, algorithm, min_support, min_confidence, min_lift)
    items = sorted(((next(iter(k)), v) for k, v in r["itemsets"].items() if len(k) == 1), key=lambda kv: -kv[1])
    top_sets = sorted(((sorted(k), v) for k, v in r["itemsets"].items() if len(k) > 1), key=lambda kv: -kv[1])[:60]
    out = {
        "params": {"algorithm": algorithm, "min_support": min_support, "min_confidence": min_confidence,
                   "min_lift": min_lift},
        "n_transactions": len(tx), "avg_basket": float(np.mean([len(t) for t in tx])),
        "n_itemsets": len(r["itemsets"]), "by_size": r["by_size"], "n_closed": r["n_closed"],
        "n_maximal": r["n_maximal"], "n_rules": len(r["rules"]), "ms_mine": r["ms_mine"], "ms_rules": r["ms_rules"],
        "stats": r["stats"], "items": [{"item": i, "support": s} for i, s in items],
        "itemsets": [{"items": i, "support": s} for i, s in top_sets],
        "rules": r["rules"][:max_rules], "graph": rule_graph(r["rules"]),
    }
    if planted is not None:
        rec = planted_recovery(r["rules"], planted)
        out["planted"] = {"rules": rec, "recovered": sum(x["found"] for x in rec), "total": len(rec)}
    return out


def run(con) -> dict:
    planted = store.planted(con)["rules"]
    tx = baskets(con, "session")
    session = report(tx, "fpgrowth", 0.02, 0.6, 1.0, planted)
    apr = mine(tx, "apriori", 0.02, 0.6)
    same = set(apr["itemsets"]) == set(fpgrowth(tx, 0.02)[0])
    scaling = []
    for ms in (0.2, 0.1, 0.05, 0.03, 0.02, 0.01, 0.005):
        a = mine(tx, "apriori", ms, 1.1)
        f = mine(tx, "fpgrowth", ms, 1.1)
        scaling.append({"min_support": ms, "itemsets": len(f["itemsets"]), "apriori_ms": a["ms_mine"],
                        "fpgrowth_ms": f["ms_mine"],
                        "apriori_candidates": sum(s["candidates"] for s in a["stats"]),
                        "fp_tree_nodes": f["stats"]["tree_nodes"],
                        "conditional_trees": f["stats"]["conditional_trees"]})
    week = report(baskets(con, "user_week"), "fpgrowth", 0.05, 0.6, 1.0)
    return {
        "session": session, "user_week": week,
        "comparison": {"same_itemsets": same, "apriori_levels": apr["stats"], "scaling": scaling},
        "fp_tree": tree_preview(tx, 0.05, 80),
    }
