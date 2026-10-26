"""Agglomerative hierarchical clustering with the Lance-Williams update.

Linkages: single, complete, average (UPGMA) and Ward. The output linkage
matrix uses SciPy's layout so it can be checked against scipy.cluster.hierarchy:
row i = [cluster a, cluster b, merge distance, new cluster size], new id n+i.
"""
from __future__ import annotations

import numpy as np

from .knn import pairwise_sq


def linkage(X: np.ndarray, method: str = "average") -> np.ndarray:
    X = np.asarray(X, float)
    n = len(X)
    D = pairwise_sq(X, X)
    if method != "ward":
        D = np.sqrt(D)
    # Ward works on squared distances internally and reports sqrt at the end.
    np.fill_diagonal(D, np.inf)
    size = np.ones(n)
    ids = np.arange(n)  # cluster id currently stored in each row
    Z = np.zeros((n - 1, 4))
    for step in range(n - 1):
        flat = int(np.argmin(D))
        i, j = divmod(flat, n)
        if i > j:
            i, j = j, i
        d_ij = D[i, j]
        si, sj = size[i], size[j]
        # Lance-Williams: distance from the merged cluster (stored in row i) to every other k.
        di, dj = D[i], D[j]
        if method == "single":
            new = np.minimum(di, dj)
        elif method == "complete":
            new = np.maximum(di, dj)
        elif method == "average":
            new = (si * di + sj * dj) / (si + sj)
        elif method == "ward":
            sk = size
            new = ((si + sk) * di + (sj + sk) * dj - sk * d_ij) / (si + sj + sk)
        else:
            raise ValueError(method)
        a, b = sorted((ids[i], ids[j]))
        Z[step] = [a, b, np.sqrt(d_ij) if method == "ward" else d_ij, si + sj]
        D[i, :], D[:, i] = new, new
        D[i, i] = np.inf
        D[j, :], D[:, j] = np.inf, np.inf  # row j is retired; inf propagates through every linkage
        size[i] = si + sj
        ids[i] = n + step
    return Z


def fcluster(Z: np.ndarray, k: int) -> np.ndarray:
    """Cut the dendrogram into k flat clusters (labels 0..k-1, ordered by first appearance)."""
    n = len(Z) + 1
    parent = np.arange(2 * n - 1)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for step in range(n - k):
        a, b = int(Z[step, 0]), int(Z[step, 1])
        parent[find(a)] = n + step
        parent[find(b)] = n + step
    roots = np.array([find(i) for i in range(n)])
    _, labels = np.unique(roots, return_inverse=True)
    first = {}
    for lab in labels:
        first.setdefault(lab, len(first))
    return np.array([first[lab] for lab in labels])


def dendrogram(Z: np.ndarray, p: int = 30) -> dict:
    """Layout of the last p merges (SciPy's truncate_mode='lastp'): U-shaped links as
    icoord/dcoord lists plus the leaf labels (cluster sizes)."""
    n = len(Z) + 1
    p = min(p, n)
    top = set(range(2 * n - 1 - (p - 1), 2 * n - 1))  # the last p-1 merge ids
    sizes = {i: 1 for i in range(n)}
    for s in range(n - 1):
        sizes[n + s] = int(Z[s, 3])
    icoord, dcoord, leaves = [], [], []

    def place(c):
        if c not in top:
            x = 5 + 10 * len(leaves)
            leaves.append({"id": int(c), "size": sizes[c], "x": x})
            return x, 0.0
        a, b, h = int(Z[c - n, 0]), int(Z[c - n, 1]), float(Z[c - n, 2])
        xa, ha = place(a)
        xb, hb = place(b)
        icoord.append([xa, xa, xb, xb])
        dcoord.append([ha, h, h, hb])
        return (xa + xb) / 2, h

    place(2 * n - 2)
    return {"icoord": icoord, "dcoord": dcoord, "leaves": leaves}


def cophenetic_matrix(Z: np.ndarray) -> np.ndarray:
    n = len(Z) + 1
    members = {i: [i] for i in range(n)}
    C = np.zeros((n, n))
    for s in range(n - 1):
        a, b, h = int(Z[s, 0]), int(Z[s, 1]), Z[s, 2]
        ma, mb = members.pop(a), members.pop(b)
        C[np.ix_(ma, mb)] = h
        C[np.ix_(mb, ma)] = h
        members[n + s] = ma + mb
    return C
