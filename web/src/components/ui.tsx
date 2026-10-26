import { ReactNode, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { fmt } from '../theme/chart';

export function Card({ title, sub, actions, children, className = '' }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div>{title && <h3>{title}</h3>}{sub && <p>{sub}</p>}</div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Tile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="card tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function PageHead({ code, title, children, actions }: {
  code?: string; title: string; children?: ReactNode; actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {code && <div className="mono muted">{code}</div>}
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {actions}
    </div>
  );
}

export function SectionTitle({ title, sub }: { title: string; sub?: string }) {
  return <h2 className="section-title">{title}{sub && <span>{sub}</span>}</h2>;
}

export function Status({ ok, yes = 'Pass', no = 'Fail' }: { ok: boolean; yes?: string; no?: string }) {
  return <span className={`pill ${ok ? 'good' : 'bad'}`}><span className="dot" />{ok ? `✓ ${yes}` : `✕ ${no}`}</span>;
}

export function Pill({ kind, children }: { kind: 'good' | 'bad' | 'warn' | 'neutral'; children: ReactNode }) {
  return <span className={`pill ${kind}`}><span className="dot" />{children}</span>;
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="error">
      <strong>Couldn't load this.</strong> {error}
    </div>
  );
}

export function Loading({ what = 'Loading' }: { what?: string }) {
  return <div className="loading">{what}…</div>;
}

export function Chart({ option, height = 280, onEvents }: {
  option: EChartsOption; height?: number; onEvents?: Record<string, (e: unknown) => void>;
}) {
  return <ReactECharts option={option} style={{ height, width: '100%' }} notMerge lazyUpdate onEvents={onEvents} />;
}

export interface Col<T> {
  key: string; label: string; num?: boolean; digits?: number; pct?: boolean; wrap?: boolean;
  render?: (row: T) => ReactNode; sort?: (row: T) => number | string;
}

export function DataTable<T extends Record<string, unknown>>({ rows, cols, max = 500, height }: {
  rows: T[]; cols: Col<T>[]; max?: number; height?: number;
}) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const c = cols.find((x) => x.key === sort.key);
    const get = (r: T) => (c?.sort ? c.sort(r) : (r[sort.key] as number | string));
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b);
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    });
  }, [rows, cols, sort]);
  return (
    <div className="table-wrap" style={height ? { maxHeight: height } : undefined}>
      <table>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} className={`${c.num ? 'num' : ''} sortable`}
                onClick={() => setSort((s) => ({ key: c.key, dir: s?.key === c.key && s.dir === -1 ? 1 : -1 }))}>
                {c.label}{sort?.key === c.key ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, max).map((r, i) => (
            <tr key={i}>
              {cols.map((c) => {
                const v = r[c.key];
                let content: ReactNode;
                if (c.render) content = c.render(r);
                else if (typeof v === 'number') content = c.pct ? fmt.pct(v, c.digits ?? 1) : fmt.n(v, c.digits ?? 0);
                else if (Array.isArray(v)) content = v.join(', ');
                else if (typeof v === 'boolean') content = v ? 'yes' : 'no';
                else content = v == null ? '–' : String(v);
                return <td key={c.key} className={`${c.num ? 'num' : ''} ${c.wrap ? 'wrap-cell' : ''}`}>{content}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > max && <div className="note" style={{ padding: 8 }}>Showing {max} of {rows.length} rows.</div>}
    </div>
  );
}

/** A chart with a table-view twin (every value reachable without hovering). */
export function ChartCard<T extends Record<string, unknown>>({ title, sub, option, height = 280, table, cols, extra,
  className, onEvents }: {
  title: ReactNode; sub?: ReactNode; option: EChartsOption; height?: number; table?: T[]; cols?: Col<T>[];
  extra?: ReactNode; className?: string; onEvents?: Record<string, (e: unknown) => void>;
}) {
  const [view, setView] = useState<'chart' | 'table'>('chart');
  return (
    <Card title={title} sub={sub} className={className} actions={table && cols ? (
      <div className="seg" role="tablist">
        <button className={view === 'chart' ? 'on' : ''} onClick={() => setView('chart')}>Chart</button>
        <button className={view === 'table' ? 'on' : ''} onClick={() => setView('table')}>Table</button>
      </div>
    ) : undefined}>
      {view === 'chart' || !table || !cols ? <Chart option={option} height={height} onEvents={onEvents} />
        : <DataTable rows={table} cols={cols} height={height + 20} />}
      {extra}
    </Card>
  );
}

export function Slider({ label, value, min, max, step, onChange, format }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void;
  format?: (v: number) => string;
}) {
  return (
    <label className="field">
      <span>{label} <span className="val">{format ? format(value) : value}</span></span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

export function Select<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function Legend({ items }: { items: { label: string; color: string; line?: boolean }[] }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span key={it.label}><i className={it.line ? 'line' : ''} style={{ background: it.color }} />{it.label}</span>
      ))}
    </div>
  );
}

/** "How much did mining recover" panel: rows of planted-truth checks. */
export function Recovery({ items }: { items: { label: string; value: ReactNode; ok?: boolean; note?: string }[] }) {
  return (
    <Card title="Recovered vs planted ground truth"
      sub="The synthetic data has known answers; this is how close the mining got to them.">
      <div className="table-wrap" style={{ maxHeight: 'none' }}>
        <table>
          <tbody>
            {items.map((it) => (
              <tr key={it.label}>
                <td className="wrap-cell">{it.label}{it.note && <div className="muted" style={{ fontSize: 12 }}>{it.note}</div>}</td>
                <td className="num" style={{ fontWeight: 600 }}>{it.value}</td>
                <td style={{ width: 90 }}>{it.ok === undefined ? null : <Status ok={it.ok} yes="Recovered" no="Missed" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
