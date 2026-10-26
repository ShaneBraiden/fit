/* Helpers for the admin model pages: loading a report, heatmaps, simple bar charts. */
import type { EChartsOption } from 'echarts';
import { ReactNode } from 'react';
import { useGet } from '../../api/client';
import { ErrorBox, Loading } from '../../components/ui';
import { axisStyle, barItem, base, fmt, Palette, valueLabel } from '../../theme/chart';

/** Loads /api/models/<name> and renders children once it arrives. */
export function Report<T>({ name, children }: { name: string; children: (r: T) => ReactNode }) {
  const r = useGet<T>(`/api/models/${name}`);
  if (r.error) return <ErrorBox error={r.error} />;
  if (!r.data) return <Loading />;
  return <>{children(r.data)}</>;
}

export function heatmapOption(p: Palette, M: number[][], rows: string[], cols: string[], opts: {
  xName?: string; yName?: string; left?: number; pct?: boolean; tip?: (r: string, c: string, v: number) => string;
} = {}): EChartsOption {
  const data: [number, number, number][] = [];
  M.forEach((r, i) => r.forEach((v, j) => data.push([j, i, v])));
  const max = Math.max(...M.flat(), 1e-9);
  return {
    ...base(p), grid: { left: opts.left ?? 110, right: 16, top: 10, bottom: 56 },
    xAxis: { type: 'category', data: cols, ...axisStyle(p), name: opts.xName, nameLocation: 'middle', nameGap: 40,
      axisLabel: { color: p.text2, interval: 0, rotate: cols.some((c) => c.length > 10) ? 25 : 0 } },
    yAxis: { type: 'category', data: rows, inverse: true, ...axisStyle(p), name: opts.yName, axisLabel: { color: p.text2 } },
    visualMap: { min: 0, max, show: false, inRange: { color: [p.seq[0], p.seq[6]] } },
    tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
      const v = (x as { value: [number, number, number] }).value;
      return opts.tip ? opts.tip(rows[v[1]], cols[v[0]], v[2]) : `${rows[v[1]]} · ${cols[v[0]]}: <b>${opts.pct ? fmt.pct(v[2]) : v[2]}</b>`;
    } },
    series: [{ type: 'heatmap', data, itemStyle: { borderColor: p.surface, borderWidth: 2 },
      label: { show: true, color: p.text, textBorderColor: p.surface, textBorderWidth: 2,
        formatter: (x: unknown) => { const v = (x as { value: number[] }).value[2]; return opts.pct ? fmt.pct(v, 0) : String(v); } } }],
  };
}

export function hbarOption(p: Palette, labels: string[], values: number[], opts: { pct?: boolean; left?: number; highlight?: number } = {}): EChartsOption {
  const f = (n: number) => (opts.pct ? fmt.pct(n) : fmt.n(n, n < 10 ? 3 : 0));
  return {
    ...base(p), grid: { left: opts.left ?? 140, right: 56, top: 6, bottom: 24 },
    xAxis: { type: 'value', ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => (opts.pct ? fmt.pct(v, 0) : String(v)) } },
    yAxis: { type: 'category', inverse: true, data: labels, ...axisStyle(p), axisLabel: { color: p.text2 } },
    tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => f(v as number) },
    series: [{ type: 'bar', barMaxWidth: 14, data: values.map((v, i) => ({ value: v,
      itemStyle: barItem(opts.highlight == null || opts.highlight === i ? p.series[0] : p.axis, true) })),
      label: { show: true, position: 'right', color: p.text2, formatter: valueLabel(f) } }],
  };
}
