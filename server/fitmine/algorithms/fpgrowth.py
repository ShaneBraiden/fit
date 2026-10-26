"""FP-Growth (Han, Pei & Yin 2000): frequent itemsets without candidate generation.

Two database scans build an FP-tree (items in descending support order, shared
prefixes merged, a header table linking every node of the same item). Mining
walks the header table bottom-up: for each item, collect its conditional
pattern base (prefix paths), build a conditional FP-tree from it, and recurse.
"""
from __future__ import annotations

from collections import Counter


class _Node:
    __slots__ = ("item", "count", "parent", "children", "link")

    def __init__(self, item, parent):
        self.item, self.count, self.parent = item, 0, parent
        self.children: dict = {}
        self.link = None


class FPTree:
    def __init__(self, weighted_paths, min_count: float, order: dict | None = None):
        """weighted_paths: list of (items, count). Items below min_count are dropped."""
        freq = Counter()
        for items, c in weighted_paths:
            for i in items:
                freq[i] += c
        self.freq = {i: c for i, c in freq.items() if c >= min_count}
        # Global rank: descending support, ties broken by item name for determinism.
        self.rank = order or {i: r for r, (i, _) in enumerate(sorted(self.freq.items(), key=lambda kv: (-kv[1], kv[0])))}
        self.root = _Node(None, None)
        self.header: dict = {}
        self.tail: dict = {}
        self.n_nodes = 0
        for items, c in weighted_paths:
            path = sorted((i for i in set(items) if i in self.freq), key=self.rank.__getitem__)
            self._insert(path, c)

    def _insert(self, path, count):
        node = self.root
        for item in path:
            child = node.children.get(item)
            if child is None:
                child = _Node(item, node)
                node.children[item] = child
                self.n_nodes += 1
                if item in self.tail:
                    self.tail[item].link = child
                else:
                    self.header[item] = child
                self.tail[item] = child
            child.count += count
            node = child

    def nodes(self, item):
        n = self.header.get(item)
        while n is not None:
            yield n
            n = n.link

    def prefix_paths(self, item):
        """Conditional pattern base of `item`: the path above each of its nodes."""
        base = []
        for node in self.nodes(item):
            path, p = [], node.parent
            while p is not None and p.item is not None:
                path.append(p.item)
                p = p.parent
            if path:
                base.append((path[::-1], node.count))
        return base

    def single_path(self):
        path, node = [], self.root
        while node.children:
            if len(node.children) > 1:
                return None
            node = next(iter(node.children.values()))
            path.append((node.item, node.count))
        return path


def fpgrowth(transactions, min_support: float, max_len: int | None = None):
    """Returns (itemsets, stats): itemsets maps frozenset -> support fraction."""
    tx = [list(set(t)) for t in transactions]
    n = len(tx)
    min_count = min_support * n
    tree = FPTree([(t, 1) for t in tx], min_count)
    out: dict = {}
    stats = {"tree_nodes": tree.n_nodes, "frequent_items": len(tree.freq), "conditional_trees": 0,
             "max_depth": 0}

    def mine(t: FPTree, suffix: tuple, depth: int):
        stats["max_depth"] = max(stats["max_depth"], depth)
        # Items processed from least to most frequent (bottom of the header table up).
        for item in sorted(t.freq, key=lambda i: t.rank[i], reverse=True):
            itemset = suffix + (item,)
            out[frozenset(itemset)] = t.freq[item]
            if max_len is not None and len(itemset) >= max_len:
                continue
            base = t.prefix_paths(item)
            if not base:
                continue
            cond = FPTree(base, min_count, order=t.rank)
            if not cond.freq:
                continue
            stats["conditional_trees"] += 1
            mine(cond, itemset, depth + 1)

    mine(tree, (), 0)
    return {k: v / n for k, v in out.items()}, stats


def tree_preview(transactions, min_support: float, max_nodes: int = 120) -> dict:
    """The FP-tree as nested dicts (for drawing), truncated to max_nodes."""
    tx = [list(set(t)) for t in transactions]
    tree = FPTree([(t, 1) for t in tx], min_support * len(tx))
    budget = [max_nodes]

    def walk(node):
        kids = sorted(node.children.values(), key=lambda c: -c.count)
        out = []
        for c in kids:
            if budget[0] <= 0:
                break
            budget[0] -= 1
            out.append({"name": f"{c.item}:{c.count}", "value": c.count, "children": walk(c)})
        return out

    return {"name": "null", "children": walk(tree.root), "nodes": tree.n_nodes,
            "header": [{"item": i, "support_count": c} for i, c in
                       sorted(tree.freq.items(), key=lambda kv: tree.rank[kv[0]])]}

