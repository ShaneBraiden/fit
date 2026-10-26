"""GSP sequential patterns, trajectory primitives and OLAP operations."""
import numpy as np
import pytest

from fitmine.algorithms import trajectory as T
from fitmine.algorithms.gsp import contains, gsp

DB = [
    [(1, ["a"]), (2, ["b"]), (10, ["c"])],
    [(1, ["a"]), (3, ["c"])],
    [(1, ["a", "b"]), (2, ["c"])],
    [(1, ["b"]), (2, ["c"])],
]


def test_gsp_small_textbook_db():
    pats, _ = gsp(DB, 0.5)
    got = {p: round(s * 4) for p, s in pats.items()}
    assert got[(("a",), ("c",))] == 3
    assert got[(("b",), ("c",))] == 3
    assert (("a",), ("b",)) not in got  # only sequence 1 has a strictly before b
    assert (("a", "b"),) not in got


def test_gsp_max_gap():
    pats, _ = gsp(DB, 0.5, max_gap=5)
    assert round(pats[(("a",), ("c",))] * 4) == 2  # a@1 .. c@10 exceeds the gap in sequence 1


def _all_patterns(items, max_items):
    """Every pattern with up to max_items items (elements are sorted itemsets)."""
    out = set()

    def grow(p, k):
        if k == max_items:
            return
        for i in items:
            q = p + ((i,),)
            out.add(q)
            grow(q, k + 1)
            if p and i > p[-1][-1]:
                q2 = p[:-1] + (p[-1] + (i,),)
                out.add(q2)
                grow(q2, k + 1)
    grow((), 0)
    return out


def test_gsp_complete_against_brute_force():
    rng = np.random.default_rng(0)
    items = ["a", "b", "c", "d"]
    db = []
    for _ in range(40):
        t, seq = 0, []
        for _ in range(rng.integers(2, 6)):
            t += int(rng.integers(1, 4))
            seq.append((t, sorted(set(rng.choice(items, size=rng.integers(1, 3)).tolist()))))
        db.append(seq)
    for max_gap in (None, 3):
        pats, _ = gsp(db, 0.15, max_gap=max_gap, max_len=3)
        sdb = [[(t, frozenset(s)) for t, s in seq] for seq in db]
        brute = {}
        for p in _all_patterns(items, 3):
            c = sum(contains(s, p, max_gap) for s in sdb)
            if c >= 0.15 * len(db):
                brute[p] = c / len(db)
        assert set(pats) == set(brute), max_gap


def test_binary_segmentation_recovers_change_points():
    rng = np.random.default_rng(1)
    x = np.r_[np.full(40, 2.0), np.full(30, 3.5), np.full(50, 2.2)] + rng.normal(0, 0.15, 120)
    cps = T.binary_segmentation(x, penalty=4 * 0.0225 * np.log(120))
    assert len(cps) == 2 and abs(cps[0] - 40) <= 1 and abs(cps[1] - 70) <= 1
    assert T.boundary_f1(cps, [40, 70])[2] == 1.0


def test_hausdorff_matrix_symmetric_and_resample():
    a = T.resample(np.array([[0, 0], [100, 0]], float), 11)
    assert np.allclose(np.diff(a[:, 0]), 10)
    tracks = np.stack([a, a + [0, 30], a[::-1]])
    H = T.hausdorff_matrix(tracks)
    assert H[0, 2] == pytest.approx(0) and H[0, 1] == pytest.approx(30)
    assert np.allclose(H, H.T)
