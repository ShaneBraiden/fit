import { Card, ChartCard, DataTable, PageHead, Recovery, Tile } from '../../components/ui';
import { axisStyle, base, fmt, usePalette } from '../../theme/chart';
import { heatmapOption, Report } from './shared';

interface Personas {
  features: string[]; n_users: number; k: number; iterations: number;
  k_sweep: { k: number; sse: number; silhouette: number }[]; names: Record<string, string>;
  internal: { sse: number; silhouette: number }; external: { ari: number; nmi: number; purity: number };
  contingency: { clusters: number[]; personas: string[]; counts: number[][] };
  profiles: Record<string, number | string>[];
}

export default function PersonasPage() {
  const p = usePalette();
  return (
    <Report<Personas> name="personas">{(r) => {
      const rows = r.contingency.clusters.map((c) => r.names[String(c)] ?? `cluster ${c}`);
      return (
        <>
          <PageHead title="Training style: k-means++">
            Users are grouped by how they train ({r.features.length} z-scored features: share of each activity, sessions per week,
            session length, intensity) with k-means and k-means++ seeding. Each cluster is named after its dominant activity. A user in the
            app gets the nearest cluster centre, recomputed from their own last 8 weeks.
          </PageHead>
          <div className="grid g4">
            <Tile label="Clusters" value={r.k} sub={`converged in ${r.iterations} iterations`} />
            <Tile label="Silhouette" value={r.internal.silhouette.toFixed(3)} sub="cohesion vs separation" />
            <Tile label="ARI vs planted personas" value={r.external.ari.toFixed(3)} sub={`NMI ${r.external.nmi.toFixed(3)}`} />
            <Tile label="Purity" value={fmt.pct(r.external.purity)} sub="users in their cluster's main persona" />
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <ChartCard title="Choosing k" sub="SSE elbow and silhouette peak" height={280}
              table={r.k_sweep} cols={[{ key: 'k', label: 'k', num: true }, { key: 'sse', label: 'SSE', num: true },
                { key: 'silhouette', label: 'Silhouette', num: true, digits: 3 }]}
              option={{
                ...base(p), legend: { ...base(p).legend, data: ['SSE', 'silhouette'] }, grid: { left: 60, right: 50, top: 34, bottom: 34 },
                xAxis: { type: 'category', data: r.k_sweep.map((x) => x.k), ...axisStyle(p), name: 'k', nameLocation: 'middle', nameGap: 22 },
                yAxis: [{ type: 'value', ...axisStyle(p), name: 'SSE' }, { type: 'value', ...axisStyle(p), name: 'silhouette', splitLine: { show: false } }],
                tooltip: { ...base(p).tooltip, trigger: 'axis' },
                series: [
                  { name: 'SSE', type: 'line', data: r.k_sweep.map((x) => x.sse), lineStyle: { color: p.series[0] }, itemStyle: { color: p.series[0] } },
                  { name: 'silhouette', type: 'line', yAxisIndex: 1, data: r.k_sweep.map((x) => x.silhouette), lineStyle: { color: p.series[1] }, itemStyle: { color: p.series[1] } },
                ],
              }} />
            <ChartCard title="Clusters vs planted personas" sub="users in each cell" height={280}
              option={heatmapOption(p, r.contingency.counts, rows, r.contingency.personas, { left: 150 })} />
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <Card title="Cluster profiles" sub="mean of each feature">
              <DataTable rows={r.profiles} cols={[{ key: 'name', label: 'Style' }, { key: 'size', label: 'Users', num: true },
                ...r.features.map((f) => ({ key: f, label: f.replace('share_', '% ').replace(/_/g, ' '), num: true,
                  ...(f.startsWith('share_') || f === 'avg_intensity' ? { pct: true, digits: 0 } : { digits: 1 }) }))]} />
            </Card>
            <Recovery items={[
              { label: 'Agreement with the 5 planted personas (ARI)', value: r.external.ari.toFixed(3), ok: r.external.ari > 0.8 },
              { label: 'Purity', value: fmt.pct(r.external.purity), ok: r.external.purity > 0.9 },
            ]} />
          </div>
        </>
      );
    }}</Report>
  );
}
