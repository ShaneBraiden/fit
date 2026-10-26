import { useEffect, useMemo, useState } from 'react';
import { api, useGet } from '../api/client';
import { Card, ChartCard, ErrorBox, Loading, PageHead, Select, SectionTitle } from '../components/ui';
import { axisStyle, base, fmt, usePalette } from '../theme/chart';

interface Axis { dim: string; level: string }
interface Filter { dim: string; level: string; values: string[] }
interface Spec { rows: Axis[]; cols: Axis[]; measure: string; agg: string; filters: Filter[] }
interface Result {
  spec: Spec; row_headers: string[][]; col_headers: string[][]; row_levels: string[]; col_levels: string[];
  values: (number | null)[][]; row_totals: (number | null)[]; col_totals: (number | null)[]; grand_total: number | null;
  n_facts: number; n_cells: number; sql: string;
}
interface Meta {
  schema: Record<string, { rows: number; columns: string[] }>; hierarchies: Record<string, string[]>;
  measures: string[]; default_spec: Spec; lattice: { dims: string[]; levels: string[]; cells: number; k: number }[];
  facts: number;
}
interface Example extends Result { title: string }

const AGGS = ['sum', 'avg', 'count', 'min', 'max'];
const DIM_LABEL: Record<string, string> = { date: 'Date', time: 'Time of day', activity: 'Activity', location: 'Location',
  gender: 'Gender', age_group: 'Age group', level: 'Fitness level', device: 'Device', weekday: 'Weekday' };

export default function Olap() {
  const p = usePalette();
  const meta = useGet<Meta>('/api/olap/meta');
  const examples = useGet<Example[]>('/api/olap/examples');
  const [res, setRes] = useState<Result | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [diceDim, setDiceDim] = useState<string>('');
  const [diceVals, setDiceVals] = useState<string[]>([]);

  const run = (spec: Spec, op?: Record<string, unknown>, label?: string) => {
    setBusy(true);
    api<Result>('/api/olap/query', { spec, op: op ?? null })
      .then((r) => { setRes(r); setErr(null); if (label) setLog((l) => [label, ...l].slice(0, 12)); })
      .catch((e: Error) => setErr(e.message)).finally(() => setBusy(false));
  };
  useEffect(() => { if (meta.data && !res) run(meta.data.default_spec); }, [meta.data]); // eslint-disable-line

  const spec = res?.spec;
  const h = meta.data?.hierarchies ?? {};
  const axisDims = spec ? [...spec.rows, ...spec.cols].map((a) => a.dim) : [];
  const flat = useMemo(() => (res ? res.values.flat().filter((v): v is number => v != null) : []), [res]);
  const vmax = flat.length ? Math.max(...flat) : 1;
  const vmin = flat.length ? Math.min(...flat) : 0;

  if (meta.error) return <ErrorBox error={meta.error} />;
  if (!meta.data || !spec || !res) return <Loading what="Building the cube" />;

  const setAxis = (axis: 'rows' | 'cols', dim: string) => {
    const next: Spec = { ...spec, [axis]: dim ? [{ dim, level: dim === 'date' ? 'month' : h[dim][0] }] : [] };
    run(next, undefined, `${axis === 'rows' ? 'Rows' : 'Columns'} → ${dim ? DIM_LABEL[dim] : 'none'}`);
  };
  const levelIdx = (a: Axis) => h[a.dim].indexOf(a.level);
  const membersOf = (dim: string): string[] => {
    const ri = spec.rows.findIndex((a) => a.dim === dim);
    if (ri >= 0) return res.row_headers.map((x) => x[ri]);
    const ci = spec.cols.findIndex((a) => a.dim === dim);
    return ci >= 0 ? res.col_headers.map((x) => x[ci]) : [];
  };
  const axisControl = (axis: 'rows' | 'cols') => {
    const a = spec[axis][0];
    return (
      <div className="field">
        <span>{axis === 'rows' ? 'Rows' : 'Columns'}</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <select value={a?.dim ?? ''} onChange={(e) => setAxis(axis, e.target.value)}>
            {axis === 'cols' && <option value="">(none)</option>}
            {Object.keys(h).map((d) => <option key={d} value={d}>{DIM_LABEL[d] ?? d}</option>)}
          </select>
          {a && <>
            <span className="chip mono">{a.level}</span>
            <button className="btn small" title="Roll up: climb the concept hierarchy" disabled={busy}
              onClick={() => run(spec, { type: 'rollup', dim: a.dim }, `ROLL-UP ${a.dim}: ${a.level} → ${h[a.dim][levelIdx(a) + 1] ?? '(all)'}`)}>
              ▲ roll up</button>
            <button className="btn small" title="Drill down: one level finer" disabled={busy || levelIdx(a) === 0}
              onClick={() => run(spec, { type: 'drilldown', dim: a.dim }, `DRILL-DOWN ${a.dim}: ${a.level} → ${h[a.dim][levelIdx(a) - 1]}`)}>
              ▼ drill down</button>
          </>}
        </div>
      </div>
    );
  };

  const heat: [number, number, number | null][] = [];
  res.values.forEach((row, i) => row.forEach((v, j) => heat.push([j, i, v])));
  const rowLab = res.row_headers.map((x) => x.join(' · ') || 'all');
  const colLab = res.col_headers.map((x) => x.join(' · ') || spec.measure);
  const shade = (v: number | null) => {
    if (v == null || vmax === vmin) return undefined;
    const t = (v - vmin) / (vmax - vmin);
    return `color-mix(in srgb, ${p.seq[4]} ${Math.round(8 + t * 42)}%, transparent)`;
  };

  return (
    <>
      <PageHead code="U2" title="Data warehouse & OLAP">
        Clean workouts are loaded into a star schema (one fact table, five dimensions with concept hierarchies).
        The cube below evaluates every operation on the server and shows the equivalent SQL.
      </PageHead>

      <div className="controls">
        {axisControl('rows')}
        {axisControl('cols')}
        <Select label="Measure" value={spec.measure} options={meta.data.measures.map((m) => ({ value: m, label: m }))}
          onChange={(m) => run({ ...spec, measure: m }, undefined, `Measure → ${m}`)} />
        <Select label="Aggregate" value={spec.agg} options={AGGS.map((a) => ({ value: a, label: a.toUpperCase() }))}
          onChange={(a) => run({ ...spec, agg: a }, undefined, `Aggregate → ${a}`)} />
        <button className="btn" disabled={busy} onClick={() => run(spec, { type: 'pivot' }, 'PIVOT rows ↔ columns')}>⇄ Pivot</button>
        <button className="btn" disabled={busy || !spec.filters.length}
          onClick={() => run(spec, { type: 'clear_filters' }, 'Clear slice / dice')}>Clear filters</button>
      </div>

      <div className="grid g3">
        <Card className="span2" title={`${spec.agg.toUpperCase()}(${spec.measure})`}
          sub={<>{fmt.n(res.n_facts)} facts · {res.n_cells} non-empty cells · grand total <b>{fmt.n(res.grand_total, 1)}</b>
            {' '}· click a row header to <b>slice</b> on it</>}>
          {spec.filters.length > 0 && (
            <div className="chips" style={{ marginBottom: 10 }}>
              {spec.filters.map((f) => <span key={f.dim} className="chip">{f.level} ∈ {'{'}{f.values.join(', ')}{'}'}</span>)}
            </div>
          )}
          <div className={`table-wrap ${busy ? 'stale' : ''}`} style={{ maxHeight: 420 }}>
            <table>
              <thead>
                <tr>
                  <th>{res.row_levels.join(' · ') || ''}</th>
                  {colLab.map((c) => <th key={c} className="num">{c}</th>)}
                  {res.col_levels.length > 0 && <th className="num">Total</th>}
                </tr>
              </thead>
              <tbody>
                {res.values.map((row, i) => (
                  <tr key={rowLab[i]}>
                    <th style={{ position: 'static', background: 'transparent', cursor: spec.rows.length ? 'pointer' : 'default' }}
                      title={spec.rows.length ? 'Slice on this member' : undefined}
                      onClick={() => spec.rows.length === 1 && run(spec, { type: 'slice', dim: spec.rows[0].dim,
                        level: spec.rows[0].level, value: res.row_headers[i][0] }, `SLICE ${spec.rows[0].level} = ${res.row_headers[i][0]}`)}>
                      {rowLab[i]}
                    </th>
                    {row.map((v, j) => <td key={j} className="num" style={{ background: shade(v) }}>{fmt.n(v, spec.agg === 'avg' ? 1 : 0)}</td>)}
                    {res.col_levels.length > 0 && <td className="num"><b>{fmt.n(res.row_totals[i], 0)}</b></td>}
                  </tr>
                ))}
                {res.row_levels.length > 0 && (
                  <tr>
                    <th style={{ position: 'static' }}>Total</th>
                    {res.col_totals.map((v, j) => <td key={j} className="num"><b>{fmt.n(v, 0)}</b></td>)}
                    {res.col_levels.length > 0 && <td className="num"><b>{fmt.n(res.grand_total, 0)}</b></td>}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <h3 style={{ margin: '14px 0 6px' }}>Equivalent SQL on the star schema</h3>
          <pre className="sql mono">{res.sql}</pre>
          {err && <div className="error" style={{ marginTop: 10 }}>{err}</div>}
        </Card>

        <div className="stack">
          <Card title="Dice" sub="keep several members of one dimension">
            <div className="field">
              <span>Dimension on an axis</span>
              <select value={diceDim} onChange={(e) => { setDiceDim(e.target.value); setDiceVals([]); }}>
                <option value="">choose…</option>
                {axisDims.map((d) => <option key={d} value={d}>{DIM_LABEL[d]}</option>)}
              </select>
            </div>
            {diceDim && (
              <div className="chips" style={{ margin: '10px 0' }}>
                {membersOf(diceDim).map((m) => (
                  <label key={m} className="check chip">
                    <input type="checkbox" checked={diceVals.includes(m)}
                      onChange={(e) => setDiceVals((v) => e.target.checked ? [...v, m] : v.filter((x) => x !== m))} />{m}
                  </label>
                ))}
              </div>
            )}
            <button className="btn primary" disabled={!diceDim || !diceVals.length || busy} onClick={() => {
              const a = [...spec.rows, ...spec.cols].find((x) => x.dim === diceDim)!;
              run(spec, { type: 'dice', selections: [{ dim: diceDim, level: a.level, values: diceVals }] },
                `DICE ${a.level} ∈ {${diceVals.join(', ')}}`);
            }}>Apply dice</button>
          </Card>
          <Card title="Operation log" sub="most recent first">
            {log.length ? <ol style={{ margin: 0, paddingLeft: 18 }} className="note">{log.map((l, i) => <li key={i}><code>{l}</code></li>)}</ol>
              : <div className="muted">Use roll-up, drill-down, slice, dice or pivot.</div>}
          </Card>
          <Card title="Saved queries">
            <div className="stack" style={{ gap: 8 }}>
              {(examples.data ?? []).map((e) => (
                <button key={e.title} className="btn" style={{ textAlign: 'left' }}
                  onClick={() => run(e.spec, undefined, `Load "${e.title}"`)}>{e.title}</button>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {res.row_headers.length > 1 && res.col_headers.length > 0 && (
        <ChartCard title="Cube slice as a heatmap" sub="darker = larger value (single blue ramp)" height={Math.max(220, 26 * rowLab.length + 70)}
          option={{
            ...base(p), grid: { left: 140, right: 20, top: 10, bottom: 60 },
            xAxis: { type: 'category', data: colLab, ...axisStyle(p), axisLabel: { color: p.text2, rotate: colLab.length > 6 ? 30 : 0 } },
            yAxis: { type: 'category', data: rowLab, inverse: true, ...axisStyle(p), axisLabel: { color: p.text2 } },
            visualMap: { min: vmin, max: vmax, show: false, inRange: { color: [p.seq[0], p.seq[6]] } },
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const v = (x as { value: [number, number, number] }).value;
              return `${rowLab[v[1]]} · ${colLab[v[0]]}<br/><b>${fmt.n(v[2], 1)}</b>`;
            } },
            series: [{ type: 'heatmap', data: heat.filter((d) => d[2] != null), itemStyle: { borderColor: p.surface, borderWidth: 2 } }],
          }} />
      )}

      <SectionTitle title="Star schema" sub={`${fmt.n(meta.data.facts)} facts`} />
      <div className="grid g3">
        {Object.entries(meta.data.schema).map(([t, v]) => (
          <Card key={t} title={<code>{t}</code>} sub={`${fmt.n(v.rows)} rows`}
            className={t === 'fact_workout' ? 'span2' : ''}>
            <div className="chips">{v.columns.map((c) => <span key={c} className="chip mono">{c}</span>)}</div>
          </Card>
        ))}
        <Card title="Concept hierarchies" sub="roll-up climbs left → right">
          {Object.entries(h).map(([d, lv]) => (
            <div key={d} className="note"><b>{DIM_LABEL[d]}</b>: {lv.join(' → ')} → all</div>
          ))}
        </Card>
      </div>

      <SectionTitle title="Cuboid lattice" sub="date(month) × activity × zone × gender: 2⁴ = 16 group-bys, apex to base, with cells each would store" />
      <Card>
        <div className="stack" style={{ gap: 10 }}>
          {[0, 1, 2, 3, 4].map((k) => (
            <div key={k} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
              {meta.data!.lattice.filter((c) => c.k === k).map((c) => (
                <div key={c.dims.join()} className="chip" style={{ padding: '6px 10px', textAlign: 'center' }}>
                  <div style={{ fontWeight: 600 }}>{c.dims.length ? c.dims.join(' × ') : 'apex (all)'}</div>
                  <div className="muted num">{fmt.n(c.cells)} cells</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
