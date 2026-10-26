"""U2 OLAP over a star schema: a cube with concept hierarchies and the classic
operations (roll-up, drill-down, slice, dice, pivot) plus the cuboid lattice.

A query *spec* is a plain dict, so a UI can hold it and apply operations to it:
  {"rows": [{"dim": "date", "level": "month"}], "cols": [{"dim": "activity", "level": "activity"}],
   "measure": "calories", "agg": "sum", "filters": [{"dim": "user", "level": "gender", "values": ["F"]}]}
"""
from __future__ import annotations

import copy
from itertools import combinations

import pandas as pd

AGGS = {"sum": "sum", "avg": "mean", "count": "count", "min": "min", "max": "max"}


class Cube:
    def __init__(self, base: pd.DataFrame, hierarchies: dict[str, list[str]], measures: list[str],
                 orders: dict[str, list] | None = None, tables: dict[str, str] | None = None):
        """base: fact rows already joined with their dimension attributes.
        hierarchies: dim -> levels from finest to coarsest (column names in base).
        orders: optional display order of a level's members.
        tables: dim -> dimension table name, only used to render the equivalent SQL."""
        self.base = base
        self.h = hierarchies
        self.measures = measures
        self.orders = orders or {}
        self.tables = tables or {}

    # ---- evaluation
    def query(self, spec: dict) -> dict:
        df = self.base
        for f in spec.get("filters", []):
            df = df[df[f["level"]].astype(str).isin([str(v) for v in f["values"]])]
        rows = [a["level"] for a in spec.get("rows", [])]
        cols = [a["level"] for a in spec.get("cols", [])]
        m, agg = spec["measure"], AGGS[spec.get("agg", "sum")]
        keys = rows + cols
        if keys:
            g = df.groupby(keys, observed=True)[m].agg(agg).reset_index()
        else:
            g = pd.DataFrame({m: [df[m].agg(agg)]})
        row_keys = self._members(g, rows)
        col_keys = self._members(g, cols)
        lookup = {tuple(str(r[k]) for k in keys): r[m] for _, r in g.iterrows()} if keys else {(): g[m].iat[0]}
        values = [[_num(lookup.get(rk + ck)) for ck in col_keys] for rk in row_keys]

        def total(fr: pd.DataFrame, by: list[str], members: list[tuple]):
            if not by:
                return [_num(fr[m].agg(agg))]
            t = fr.groupby(by, observed=True)[m].agg(agg)
            t.index = [tuple(str(v) for v in (i if isinstance(i, tuple) else (i,))) for i in t.index]
            return [_num(t.get(k)) for k in members]

        return {
            "spec": spec,
            "row_headers": [list(k) for k in row_keys], "col_headers": [list(k) for k in col_keys],
            "row_levels": rows, "col_levels": cols,
            "values": values,
            "row_totals": total(df, rows, row_keys), "col_totals": total(df, cols, col_keys),
            "grand_total": _num(df[m].agg(agg)) if len(df) else None,
            "n_facts": int(len(df)), "n_cells": int(len(g)),
            "sql": self.sql(spec),
        }

    def _members(self, g: pd.DataFrame, levels: list[str]) -> list[tuple]:
        if not levels:
            return [()]
        combos = g[levels].astype(str).drop_duplicates()
        keyfn = []
        for lv in levels:
            order = self.orders.get(lv)
            keyfn.append((lambda v, o=order: (o.index(v) if v in o else len(o), v)) if order else (lambda v: (0, v)))
        tuples = [tuple(r) for r in combos.itertuples(index=False)]
        return sorted(tuples, key=lambda t: tuple(f(v) for f, v in zip(keyfn, t)))

    # ---- operations on a spec
    def _axis_of(self, spec, dim):
        for axis in ("rows", "cols"):
            for i, a in enumerate(spec[axis]):
                if a["dim"] == dim:
                    return axis, i
        return None, None

    def rollup(self, spec: dict, dim: str) -> dict:
        """Climb one level up the dimension's hierarchy; past the top the dimension is removed."""
        s = copy.deepcopy(spec)
        axis, i = self._axis_of(s, dim)
        if axis is None:
            return s
        levels = self.h[dim]
        li = levels.index(s[axis][i]["level"])
        if li + 1 < len(levels):
            s[axis][i]["level"] = levels[li + 1]
        else:
            s[axis].pop(i)
        return s

    def drilldown(self, spec: dict, dim: str, axis: str = "rows") -> dict:
        """Step one level down the hierarchy; adds the dimension at its top level if absent."""
        s = copy.deepcopy(spec)
        ax, i = self._axis_of(s, dim)
        levels = self.h[dim]
        if ax is None:
            s[axis].append({"dim": dim, "level": levels[-1]})
            return s
        li = levels.index(s[ax][i]["level"])
        if li > 0:
            s[ax][i]["level"] = levels[li - 1]
        return s

    def slice(self, spec: dict, dim: str, level: str, value) -> dict:
        """Fix one dimension to a single member; that dimension leaves the axes."""
        s = copy.deepcopy(spec)
        axis, i = self._axis_of(s, dim)
        if axis is not None:
            s[axis].pop(i)
        s["filters"] = [f for f in s.get("filters", []) if f["dim"] != dim] + \
            [{"dim": dim, "level": level, "values": [value]}]
        return s

    def dice(self, spec: dict, selections: list[dict]) -> dict:
        """Select a sub-cube: several member values on one or more dimensions."""
        s = copy.deepcopy(spec)
        dims = {sel["dim"] for sel in selections}
        s["filters"] = [f for f in s.get("filters", []) if f["dim"] not in dims] + selections
        return s

    def pivot(self, spec: dict) -> dict:
        s = copy.deepcopy(spec)
        s["rows"], s["cols"] = s["cols"], s["rows"]
        return s

    def apply(self, spec: dict, op: dict | None) -> dict:
        if not op:
            return spec
        t = op["type"]
        if t == "rollup":
            return self.rollup(spec, op["dim"])
        if t == "drilldown":
            return self.drilldown(spec, op["dim"], op.get("axis", "rows"))
        if t == "slice":
            return self.slice(spec, op["dim"], op["level"], op["value"])
        if t == "dice":
            return self.dice(spec, op["selections"])
        if t == "pivot":
            return self.pivot(spec)
        if t == "clear_filters":
            return {**copy.deepcopy(spec), "filters": []}
        raise ValueError(f"unknown OLAP operation {t}")

    # ---- lattice and SQL
    def lattice(self, dims: list[tuple[str, str]], measure: str) -> list[dict]:
        """All 2^n cuboids over the chosen (dim, level) pairs, from apex to base, with
        the number of non-empty cells each would materialise."""
        out = []
        for r in range(len(dims) + 1):
            for combo in combinations(dims, r):
                levels = [lv for _, lv in combo]
                cells = int(self.base.groupby(levels, observed=True).ngroups) if levels else 1
                out.append({"dims": [d for d, _ in combo], "levels": levels, "cells": cells, "k": r})
        return out

    def sql(self, spec: dict) -> str:
        levels = [a["level"] for a in spec.get("rows", []) + spec.get("cols", [])]
        dims = {a["dim"] for a in spec.get("rows", []) + spec.get("cols", [])} | \
            {f["dim"] for f in spec.get("filters", [])}
        agg = spec.get("agg", "sum").upper()
        sel = ", ".join(levels + [f"{agg}(f.{spec['measure']}) AS {spec['measure']}_{agg.lower()}"])
        joins = "".join(f"\n  JOIN {self.tables.get(d, 'dim_' + d)} USING ({d}_key)" for d in sorted(dims))
        where = " AND ".join(
            f"{f['level']} IN ({', '.join(repr(str(v)) for v in f['values'])})" for f in spec.get("filters", []))
        q = f"SELECT {sel}\nFROM fact_workout f{joins}"
        if where:
            q += f"\nWHERE {where}"
        if levels:
            q += f"\nGROUP BY {', '.join(levels)}"
        return q


def _num(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    return round(float(v), 2)
