"""GSP: Generalized Sequential Patterns (Srikant & Agrawal 1996).

A data sequence is a time-ordered list of elements (itemsets). A pattern
<e1 e2 ... em> is contained in it if there are elements, in order, that are
supersets of e1..em, with consecutive matched elements at most max_gap apart.

Level-wise like Apriori: join (k-1)-patterns whose overlap matches, prune any
candidate with an infrequent contiguous (k-1)-subsequence, then count.
"""
from __future__ import annotations

from functools import reduce

Pattern = tuple  # tuple of sorted tuples of items


def _drop_first(p: Pattern) -> Pattern:
    first = p[0][1:]
    return ((first,) if first else ()) + p[1:]


def _drop_last(p: Pattern) -> Pattern:
    last = p[-1][:-1]
    return p[:-1] + ((last,) if last else ())


def _size(p: Pattern) -> int:
    return sum(len(e) for e in p)


def _contiguous_subsequences(p: Pattern):
    """All (k-1)-subsequences obtained by dropping one item from the first or last
    element, or from any element that has at least two items."""
    out = set()
    for i, e in enumerate(p):
        if len(e) >= 2 or i in (0, len(p) - 1):
            for j in range(len(e)):
                ne = e[:j] + e[j + 1:]
                q = p[:i] + ((ne,) if ne else ()) + p[i + 1:]
                if q:
                    out.add(q)
    return out


def contains(seq, pattern: Pattern, max_gap=None, min_gap: float = 0) -> bool:
    """seq: list of (time, frozenset). Depth-first search for an embedding."""
    n = len(seq)

    def dfs(j, start, prev_t):
        if j == len(pattern):
            return True
        e = pattern[j]
        for i in range(start, n):
            t, items = seq[i]
            if prev_t is not None:
                gap = t - prev_t
                if gap <= min_gap:
                    continue
                if max_gap is not None and gap > max_gap:
                    break
            if items.issuperset(e) and dfs(j + 1, i + 1, t):
                return True
        return False

    return dfs(0, 0, None)


def gsp(sequences, min_support: float, max_gap=None, min_gap: float = 0, max_len: int = 6):
    """sequences: list of lists of (time, iterable of items).

    Returns (patterns, stats): patterns maps Pattern -> support fraction."""
    db = [[(t, frozenset(items)) for t, items in s] for s in sequences]
    n = len(db)
    min_count = min_support * n
    sids_by_item: dict = {}
    for sid, s in enumerate(db):
        for _, items in s:
            for i in items:
                sids_by_item.setdefault(i, set()).add(sid)

    L = {((i,),): len(s) for i, s in sids_by_item.items() if len(s) >= min_count}
    stats = [{"k": 1, "candidates": len(sids_by_item), "pruned": 0, "frequent": len(L)}]
    result = {p: c / n for p, c in L.items()}
    items1 = sorted(p[0][0] for p in L)

    def count(cands):
        out = {}
        for c in cands:
            flat = {i for e in c for i in e}
            sids = reduce(set.intersection, (sids_by_item[i] for i in flat))
            if len(sids) < min_count:
                continue
            cnt = sum(1 for sid in sids if contains(db[sid], c, max_gap, min_gap))
            if cnt >= min_count:
                out[c] = cnt
        return out

    k = 2
    while L and k <= max_len:
        if k == 2:
            cands = [((a,), (b,)) for a in items1 for b in items1] + \
                    [((a, b),) for i, a in enumerate(items1) for b in items1[i + 1:]]
            joined, pruned = len(cands), 0
        else:
            prev = list(L)
            by_head: dict = {}
            for p in prev:
                by_head.setdefault(_drop_last(p), []).append(p)
            raw = set()
            for s1 in prev:
                for s2 in by_head.get(_drop_first(s1), []):
                    last = s2[-1][-1]
                    if len(s2[-1]) == 1:
                        raw.add(s1 + ((last,),))
                    elif last > s1[-1][-1]:
                        raw.add(s1[:-1] + (s1[-1] + (last,),))
            prev_set = set(prev)
            cands = [c for c in raw if all(q in prev_set for q in _contiguous_subsequences(c))]
            joined, pruned = len(raw), len(raw) - len(cands)
        L = count(cands)
        stats.append({"k": k, "candidates": joined, "pruned": pruned, "frequent": len(L)})
        result.update({p: c / n for p, c in L.items()})
        k += 1
    return result, stats


def fmt(p: Pattern) -> str:
    return "<" + " ".join("(" + ", ".join(e) + ")" if len(e) > 1 else e[0] for e in p) + ">"
