"""Apriori, FP-Growth and rule generation: Han & Kamber's AllElectronics example
(Table 6.1, min support count 2) and parity with mlxtend."""
import numpy as np
import pandas as pd
import pytest
from mlxtend.frequent_patterns import association_rules as mx_rules
from mlxtend.frequent_patterns import fpgrowth as mx_fpgrowth

from fitmine.algorithms.fpgrowth import fpgrowth
from fitmine.algorithms.rules import closed_and_maximal, generate_rules

ALL_ELECTRONICS = [
    ["I1", "I2", "I5"], ["I2", "I4"], ["I2", "I3"], ["I1", "I2", "I4"], ["I1", "I3"],
    ["I2", "I3"], ["I1", "I3"], ["I1", "I2", "I3", "I5"], ["I1", "I2", "I3"],
]
EXPECTED_COUNTS = {
    ("I1",): 6, ("I2",): 7, ("I3",): 6, ("I4",): 2, ("I5",): 2,
    ("I1", "I2"): 4, ("I1", "I3"): 4, ("I1", "I5"): 2, ("I2", "I3"): 4, ("I2", "I4"): 2, ("I2", "I5"): 2,
    ("I1", "I2", "I3"): 2, ("I1", "I2", "I5"): 2,
}


def test_textbook_itemsets():
    itemsets, _ = fpgrowth(ALL_ELECTRONICS, 2 / 9)
    got = {tuple(sorted(k)): round(v * 9) for k, v in itemsets.items()}
    assert got == EXPECTED_COUNTS


def test_rule_confidence_textbook():
    itemsets, _ = fpgrowth(ALL_ELECTRONICS, 2 / 9)
    rules = generate_rules(itemsets, 0.7)
    found = {(tuple(r["antecedent"]), tuple(r["consequent"])): r["confidence"] for r in rules}
    # {I1,I5} -> I2, {I2,I5} -> I1 and I5 -> {I1,I2} all have 100% confidence (H&K Example 6.4)
    assert found[(("I1", "I5"), ("I2",))] == pytest.approx(1.0)
    assert found[(("I2", "I5"), ("I1",))] == pytest.approx(1.0)
    assert found[(("I5",), ("I1", "I2"))] == pytest.approx(1.0)
    assert (("I1", "I2"), ("I5",)) not in found  # 50% < 70%


def _random_baskets(seed=1, n=600):
    rng = np.random.default_rng(seed)
    items = [f"x{i}" for i in range(12)]
    out = []
    for _ in range(n):
        t = set(rng.choice(items, size=rng.integers(1, 6), replace=False).tolist())
        if "x1" in t and rng.random() < 0.8:
            t.add("x2")
        out.append(sorted(t))
    return out


def _onehot(tx):
    items = sorted({i for t in tx for i in t})
    return pd.DataFrame([[i in t for i in items] for t in tx], columns=items)


def test_parity_with_mlxtend():
    tx = _random_baskets()
    mine, _ = fpgrowth(tx, 0.05)
    ref = mx_fpgrowth(_onehot(tx), min_support=0.05, use_colnames=True)
    ref = {frozenset(r.itemsets): r.support for r in ref.itertuples()}
    assert set(mine) == set(ref)
    for k in ref:
        assert mine[k] == pytest.approx(ref[k])


def test_rules_parity_with_mlxtend():
    tx = _random_baskets()
    itemsets, _ = fpgrowth(tx, 0.05)
    mine = {(frozenset(r["antecedent"]), frozenset(r["consequent"])): r for r in generate_rules(itemsets, 0.3)}
    ref_sets = mx_fpgrowth(_onehot(tx), min_support=0.05, use_colnames=True)
    ref = mx_rules(ref_sets, metric="confidence", min_threshold=0.3)
    assert len(mine) == len(ref)
    for r in ref.itertuples():
        m = mine[(frozenset(r.antecedents), frozenset(r.consequents))]
        assert m["lift"] == pytest.approx(r.lift)
        assert m["leverage"] == pytest.approx(r.leverage)


def test_closed_and_maximal():
    itemsets, _ = fpgrowth(ALL_ELECTRONICS, 2 / 9)
    closed, maximal = closed_and_maximal(itemsets)
    assert frozenset({"I1", "I2", "I5"}) in maximal
    assert frozenset({"I5"}) not in closed  # {I1,I2,I5} has the same support (2)
    assert maximal <= closed
