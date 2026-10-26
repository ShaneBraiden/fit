"""Decision tree induction: ID3, C4.5 and CART in one learner.

  id3   information gain, multiway splits, categorical attributes only
  c45   gain ratio; multiway on categorical, binary threshold on numeric
  cart  Gini index, binary splits everywhere (numeric threshold, or one-vs-rest category)

Stopping (pre-pruning): max_depth, min_samples_split, min_gain.
Post-pruning: reduced-error pruning against a held-out validation set.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _entropy(counts: np.ndarray) -> np.ndarray:
    tot = counts.sum(-1, keepdims=True)
    p = np.divide(counts, tot, out=np.zeros(counts.shape), where=tot > 0)
    return -(p * np.log2(p, out=np.zeros(p.shape), where=p > 0)).sum(-1)


def _gini(counts: np.ndarray) -> np.ndarray:
    tot = counts.sum(-1, keepdims=True)
    p = np.divide(counts, tot, out=np.zeros(counts.shape), where=tot > 0)
    return 1 - (p ** 2).sum(-1)


class DecisionTree:
    def __init__(self, algorithm: str = "c45", max_depth: int = 6, min_samples_split: int = 10,
                 min_gain: float = 1e-4):
        assert algorithm in ("id3", "c45", "cart")
        self.algorithm = algorithm
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.min_gain = min_gain

    # ---------------------------------------------------------------- fitting
    def fit(self, X: pd.DataFrame, y):
        self.features = list(X.columns)
        self.numeric = {c: pd.api.types.is_numeric_dtype(X[c]) for c in self.features}
        if self.algorithm == "id3" and any(self.numeric.values()):
            raise ValueError("ID3 needs categorical attributes; discretise numeric columns first")
        self.classes_ = np.array(sorted(pd.unique(np.asarray(y))))
        yi = np.searchsorted(self.classes_, np.asarray(y))
        self._cols = {c: (X[c].to_numpy(dtype=float) if self.numeric[c] else X[c].astype(str).to_numpy())
                      for c in self.features}
        self.importance_ = dict.fromkeys(self.features, 0.0)
        self.n_ = len(yi)
        self.root = self._grow(np.arange(len(yi)), yi, depth=0)
        total = sum(self.importance_.values()) or 1.0
        self.feature_importances_ = {k: v / total for k, v in self.importance_.items()}
        return self

    def _impurity(self, counts):
        return _gini(counts) if self.algorithm == "cart" else _entropy(counts)

    def _counts(self, yi):
        return np.bincount(yi, minlength=len(self.classes_)).astype(float)

    def _leaf(self, idx, yi):
        c = self._counts(yi[idx])
        return {"leaf": True, "n": int(len(idx)), "dist": c.tolist(), "cls": int(c.argmax())}

    def _grow(self, idx, yi, depth):
        node = self._leaf(idx, yi)
        counts = np.array(node["dist"])
        if depth >= self.max_depth or len(idx) < self.min_samples_split or (counts > 0).sum() == 1:
            return node
        parent = float(self._impurity(counts))
        best = None
        for f in self.features:
            cand = self._best_split(f, idx, yi, parent)
            if cand and (best is None or cand["score"] > best["score"]):
                best = cand
        if best is None or best["gain"] < self.min_gain:
            return node
        self.importance_[best["feature"]] += best["gain"] * len(idx) / self.n_
        node.update(leaf=False, feature=best["feature"], kind=best["kind"], gain=best["gain"],
                    score=best["score"])
        if best["kind"] == "threshold":
            node["threshold"] = best["threshold"]
            col = self._cols[best["feature"]][idx]
            left, right = idx[col <= best["threshold"]], idx[~(col <= best["threshold"])]
            node["children"] = [("<= %.4g" % best["threshold"], self._grow(left, yi, depth + 1)),
                                ("> %.4g" % best["threshold"], self._grow(right, yi, depth + 1))]
        elif best["kind"] == "category":  # CART one-vs-rest
            node["value"] = best["value"]
            col = self._cols[best["feature"]][idx]
            node["children"] = [(f"= {best['value']}", self._grow(idx[col == best["value"]], yi, depth + 1)),
                                (f"!= {best['value']}", self._grow(idx[col != best["value"]], yi, depth + 1))]
        else:  # multiway
            col = self._cols[best["feature"]][idx]
            node["children"] = [(f"= {v}", self._grow(idx[col == v], yi, depth + 1)) for v in best["values"]]
        return node

    def _best_split(self, f, idx, yi, parent):
        col = self._cols[f][idx]
        y = yi[idx]
        n = len(idx)
        k = len(self.classes_)
        if self.numeric[f]:
            ok = ~np.isnan(col)
            if ok.sum() < 2:
                return None
            order = np.argsort(col[ok], kind="stable")
            xs, ys = col[ok][order], y[ok][order]
            cum = np.cumsum(np.eye(k)[ys], axis=0)
            left = cum[:-1]
            right = cum[-1] - left
            valid = xs[1:] != xs[:-1]
            if not valid.any():
                return None
            nl = np.arange(1, len(xs))
            m = len(xs)
            child = (nl * self._impurity(left) + (m - nl) * self._impurity(right)) / m
            gain = parent - child
            gain = np.where(valid, gain, -np.inf)
            j = int(np.argmax(gain))
            g = float(gain[j]) * m / n  # rows with missing values give no information
            score = g
            if self.algorithm == "c45":
                p = np.array([nl[j], m - nl[j]]) / m
                split_info = float(-(p * np.log2(p)).sum())
                score = g / split_info if split_info > 0 else 0.0
            return {"feature": f, "kind": "threshold", "threshold": float((xs[j] + xs[j + 1]) / 2),
                    "gain": g, "score": score}
        values = np.unique(col)
        if len(values) < 2:
            return None
        counts = np.array([np.bincount(y[col == v], minlength=k) for v in values], dtype=float)
        sizes = counts.sum(1)
        if self.algorithm == "cart":
            best = None
            for i, v in enumerate(values):
                l, r = counts[i], counts.sum(0) - counts[i]
                child = (sizes[i] * self._impurity(l) + (n - sizes[i]) * self._impurity(r)) / n
                g = parent - float(child)
                if best is None or g > best["gain"]:
                    best = {"feature": f, "kind": "category", "value": str(v), "gain": g, "score": g}
            return best
        child = float((sizes * self._impurity(counts)).sum() / n)
        g = parent - child
        score = g
        if self.algorithm == "c45":
            p = sizes / n
            split_info = float(-(p * np.log2(p)).sum())
            score = g / split_info if split_info > 0 else 0.0
        return {"feature": f, "kind": "multiway", "values": [str(v) for v in values], "gain": g, "score": score}

    # ---------------------------------------------------------------- prediction
    def _route(self, node, row):
        while not node["leaf"]:
            v = row[node["feature"]]
            if node["kind"] == "threshold":
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    # missing value: follow the bigger branch
                    node = max((c for _, c in node["children"]), key=lambda c: c["n"])
                else:
                    node = node["children"][0][1] if v <= node["threshold"] else node["children"][1][1]
            elif node["kind"] == "category":
                node = node["children"][0][1] if str(v) == node["value"] else node["children"][1][1]
            else:
                nxt = next((c for lab, c in node["children"] if lab == f"= {v}"), None)
                if nxt is None:  # unseen category: stop here
                    return node
                node = nxt
        return node

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        out = []
        for row in X.to_dict("records"):
            d = np.array(self._route(self.root, row)["dist"])
            out.append(d / d.sum())
        return np.array(out)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.classes_[self.predict_proba(X).argmax(1)]

    # ---------------------------------------------------------------- post-pruning
    def prune(self, X_val: pd.DataFrame, y_val) -> int:
        """Reduced-error pruning: bottom-up, replace a subtree by a leaf whenever that does
        not increase validation errors. Returns the number of subtrees pruned."""
        yv = np.searchsorted(self.classes_, np.asarray(y_val))
        rows = X_val.to_dict("records")
        pruned = [0]

        def errors_as_leaf(node, idx):
            return int((yv[idx] != node["cls"]).sum())

        def walk(node, idx):
            if node["leaf"]:
                return int((yv[idx] != node["cls"]).sum())
            groups = {i: [] for i in range(len(node["children"]))}
            for i in idx:
                child = self._route_one(node, rows[i])
                if child is not None:
                    groups[child].append(i)
            sub_err = sum(walk(c, np.array(groups[i], dtype=int)) for i, (_, c) in enumerate(node["children"]))
            leaf_err = errors_as_leaf(node, idx)
            if leaf_err <= sub_err:
                for key in ("feature", "kind", "threshold", "value", "values", "children", "gain", "score"):
                    node.pop(key, None)
                node["leaf"] = True
                pruned[0] += 1
                return leaf_err
            return sub_err

        walk(self.root, np.arange(len(rows)))
        return pruned[0]

    def _route_one(self, node, row):
        v = row[node["feature"]]
        if node["kind"] == "threshold":
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return int(np.argmax([c["n"] for _, c in node["children"]]))
            return 0 if v <= node["threshold"] else 1
        if node["kind"] == "category":
            return 0 if str(v) == node["value"] else 1
        for i, (lab, _) in enumerate(node["children"]):
            if lab == f"= {v}":
                return i
        return None

    # ---------------------------------------------------------------- export
    def to_dict(self, max_depth: int | None = None) -> dict:
        def conv(node, label, depth):
            d = {"name": label, "n": node["n"], "dist": dict(zip(self.classes_.tolist(), node["dist"])),
                 "class": str(self.classes_[node["cls"]])}
            if not node["leaf"]:
                d["split"] = node["feature"]
                d["gain"] = round(node["gain"], 4)
                if max_depth is None or depth < max_depth:
                    d["children"] = [conv(c, lab, depth + 1) for lab, c in node["children"]]
                else:
                    d["truncated"] = True
            return d
        return conv(self.root, "root", 0)

    def rules(self) -> list[dict]:
        """IF-THEN rules, one per leaf (rule-based classification from a tree)."""
        out = []

        def walk(node, conds):
            if node["leaf"]:
                d = np.array(node["dist"])
                out.append({"if": conds, "then": str(self.classes_[node["cls"]]), "n": node["n"],
                            "confidence": float(d.max() / d.sum()) if d.sum() else 0.0})
                return
            for lab, c in node["children"]:
                walk(c, conds + [f"{node['feature']} {lab}"])
        walk(self.root, [])
        return sorted(out, key=lambda r: -r["n"])

    def stats(self) -> dict:
        def walk(node, depth):
            if node["leaf"]:
                return 1, 1, depth
            res = [walk(c, depth + 1) for _, c in node["children"]]
            return 1 + sum(r[0] for r in res), sum(r[1] for r in res), max(r[2] for r in res)
        nodes, leaves, depth = walk(self.root, 0)
        return {"nodes": nodes, "leaves": leaves, "depth": depth}
