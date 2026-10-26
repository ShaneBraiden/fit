"""Apriori (Agrawal & Srikant 1994): level-wise frequent itemset mining.

Each level k: join frequent (k-1)-itemsets that share their first k-2 items,
prune any candidate with an infrequent (k-1)-subset (the Apriori property),
then scan the database once, counting every candidate contained in a
transaction (via a hash table of candidates, as in DHP/hash-tree counting).
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations


def apriori(transactions, min_support: float, max_len: int | None = None):
    """transactions: iterable of item collections. min_support: fraction in (0, 1].

    Returns (itemsets, stats): itemsets maps frozenset -> support fraction;
    stats has one dict per level with candidate/prune/frequent counts."""
    tx = [frozenset(t) for t in transactions]
    n = len(tx)
    min_count = min_support * n
    stats = []

    counts = Counter(i for t in tx for i in t)
    L = {(i,): c for i, c in counts.items() if c >= min_count}
    stats.append({"k": 1, "candidates": len(counts), "pruned": 0, "counted": len(counts), "frequent": len(L)})
    result = {frozenset(k): c / n for k, c in L.items()}
    frequent_items = {k[0] for k in L}
    k = 2
    while L and (max_len is None or k <= max_len):
        prev = sorted(L)
        prev_set = set(prev)
        joined = []
        for i in range(len(prev)):
            for j in range(i + 1, len(prev)):
                a, b = prev[i], prev[j]
                if a[:-1] != b[:-1]:
                    break  # sorted, so no later b shares the prefix either
                joined.append(a + (b[-1],))
        cands = [c for c in joined if all(s in prev_set for s in combinations(c, k - 1))]
        stats_k = {"k": k, "candidates": len(joined), "pruned": len(joined) - len(cands), "counted": len(cands)}
        if not cands:
            stats_k["frequent"] = 0
            stats.append(stats_k)
            break
        cand_set = set(cands)
        cnt: Counter = Counter()
        for t in tx:
            items = sorted(i for i in t if i in frequent_items)
            if len(items) < k:
                continue
            for s in combinations(items, k):
                if s in cand_set:
                    cnt[s] += 1
        L = {c: v for c, v in cnt.items() if v >= min_count}
        stats_k["frequent"] = len(L)
        stats.append(stats_k)
        result.update({frozenset(c): v / n for c, v in L.items()})
        k += 1
    return result, stats
