"""Association rules from frequent itemsets, with interestingness measures,
plus closed and maximal itemset filters."""
from __future__ import annotations

import math
from itertools import combinations


def generate_rules(itemsets: dict, min_confidence: float, min_lift: float = 0.0) -> list[dict]:
    """itemsets: frozenset -> support (must be downward closed, as Apriori/FP-Growth return)."""
    rules = []
    for items, sup in itemsets.items():
        if len(items) < 2:
            continue
        for r in range(1, len(items)):
            for ante in combinations(sorted(items), r):
                a = frozenset(ante)
                c = items - a
                sa, sc = itemsets[a], itemsets[c]
                conf = sup / sa
                if conf < min_confidence:
                    continue
                lift = conf / sc
                if lift < min_lift:
                    continue
                rules.append({
                    "antecedent": sorted(a), "consequent": sorted(c),
                    "support": sup, "confidence": conf, "lift": lift,
                    "leverage": sup - sa * sc,
                    "conviction": math.inf if conf >= 1 else (1 - sc) / (1 - conf),
                })
    rules.sort(key=lambda r: (-r["lift"], -r["confidence"], r["antecedent"], r["consequent"]))
    return rules


def closed_and_maximal(itemsets: dict) -> tuple[set, set]:
    """Closed: no proper superset with the same support. Maximal: no frequent proper superset."""
    by_size: dict[int, list] = {}
    for s in itemsets:
        by_size.setdefault(len(s), []).append(s)
    closed, maximal = set(), set()
    for s, sup in itemsets.items():
        supers = [t for t in by_size.get(len(s) + 1, []) if s < t]
        if not supers:
            maximal.add(s)
            closed.add(s)
        elif all(abs(itemsets[t] - sup) > 1e-12 for t in supers):
            closed.add(s)
    return closed, maximal
