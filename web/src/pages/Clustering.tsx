import { useState } from 'react';
import { useGet, useRun } from '../api/client';
import { Card, ChartCard, DataTable, ErrorBox, Loading, PageHead, Recovery, SectionTitle, Select, Slider, Tile } from '../components/ui';
import { axisStyle, base, fmt, SYMBOLS, usePalette } from '../theme/chart';

interface Profile { cluster: number; name: string; size: number; [k: string]: number | string }
interface Result {
  algorithm: string; params: Record<string, unknown>; ms: number; n_clusters: number; names: Record<string, string>;
  sizes: Record<string, number>; internal: { sse: number; silhouette: number; davies_bouldin: number };
  external: { ari: number; nmi: number; purity: number };
  contingency: { clusters: number[]; personas: string[]; counts: number[][] };
  profiles: Profile[]; points: { x: number; y: number; c: number; user_id: number }[];
  dendrogram?: { icoord: number[][]; dcoord: number[][]; leaves: { id: number; size: number; x: number }[] };
  medoids?: number[]; n_noise?: number; iterations?: number;
}
interface U5 {
  features: string[]; n_users: number; pca_variance: number[];
  k_sweep: { k: number; sse: number; silhouette: number; davies_bouldin: number }[]; k_distance: number[];
  results: Record<string, Result>;
  comparison: { algorithm: string; n_clusters: number; silhouette: number; davies_bouldin: number; ari: number; nmi: number;
    purity: number; ms: number }[];
}
interface Params { algorithm: string; k: number; linkage: string; method: string; eps: number; min_samples: number }

const SHARES = ['share_run', 'share_cycle', 'share_walk', 'share_swim', 'share_strength', 'share_hiit', 'share_yoga'];
const ALGOS = [{ value: 'kmeans', label: 'k-means (k-means++)' }, { value: 'kmedoids', label: 'k-medoids (PAM / CLARA)' },
  { value: 'agglomerative', label: 'Agglomerative' }, { value: 'dbscan', label: 'DBSCAN' }];

export default function Clustering() {
  const p = usePalette();
  const rep = useGet<U5>('/api/cluster/report');
  const live = useRun<Params, Result>('/api/cluster/run');
  const [prm, setPrm] = useState<Params>({ algorithm: 'kmeans', k: 5, linkage: 'ward', method: 'pam', eps: 1.2, min_samples: 10 });
  const [shown, setShown] = useState('kmeans');
  if (rep.error) return <ErrorBox error={rep.error} />;
  if (!rep.data) return <Loading />;
  const r = rep.data;
  const res = live.data ?? r.results[shown];
  const clusters = Object.keys(res.sizes).map(Number).sort((a, b) => a - b);
  const name = (c: number) => (c === -1 ? 'Noise' : `${c}: ${res.names[String(c)] ?? ''}`);
  const colorOf = (c: number) => (c === -1 ? p.axis : p.series[c % 8]);
  const real = clusters.filter((c) => c !== -1);

  return (
    <>
      <PageHead code="U5" title="Clustering: user personas">
        Users are clustered on behaviour only (activity mix, sessions per week, duration, intensity; z-scored).
        No labels are used; afterwards the clusters are compared with the five personas the generator planted.
      </PageHead>

      <div className="controls">
        <Select label="Algorithm" value={prm.algorithm} options={ALGOS} onChange={(v) => setPrm({ ...prm, algorithm: v })} />
        {prm.algorithm !== 'dbscan' && <Slider label="k" value={prm.k} min={2} max={10} step={1} onChange={(v) => setPrm({ ...prm, k: v })} />}
        {prm.algorithm === 'agglomerative' && <Select label="Linkage" value={prm.linkage} onChange={(v) => setPrm({ ...prm, linkage: v })}
          options={['ward', 'average', 'complete', 'single'].map((x) => ({ value: x, label: x }))} />}
        {prm.algorithm === 'kmedoids' && <Select label="Method" value={prm.method} onChange={(v) => setPrm({ ...prm, method: v })}
          options={[{ value: 'pam', label: 'PAM (all users)' }, { value: 'clara', label: 'CLARA (samples of 400)' }]} />}
        {prm.algorithm === 'dbscan' && <>
          <Slider label="eps" value={prm.eps} min={0.4} max={3} step={0.05} onChange={(v) => setPrm({ ...prm, eps: v })} />
          <Slider label="min samples" value={prm.min_samples} min={3} max={40} step={1} onChange={(v) => setPrm({ ...prm, min_samples: v })} />
        </>}
        <button className="btn primary" disabled={live.loading} onClick={() => live.run(prm)}>{live.loading ? 'Clustering…' : 'Run'}</button>
        <span className="note">or view a pipeline result:</span>
        <div className="seg">
          {Object.keys(r.results).map((a) => (
            <button key={a} className={!live.data && shown === a ? 'on' : ''} onClick={() => { live.setData(null); setShown(a); }}>{a}</button>
          ))}
        </div>
      </div>
      {live.error && <div className="error" style={{ marginBottom: 16 }}>{live.error}</div>}

      <div className={`grid g4 ${live.loading ? 'stale' : ''}`}>
        <Tile label="Clusters" value={res.n_clusters} sub={`${res.algorithm}${res.n_noise != null ? ` · ${res.n_noise} noise users` : ''} · ${fmt.n(res.ms)} ms`} />
        <Tile label="Silhouette" value={res.internal.silhouette.toFixed(3)} sub="−1 … 1, higher is better" />
        <Tile label="Davies-Bouldin" value={res.internal.davies_bouldin.toFixed(3)} sub="lower is better" />
        <Tile label="ARI vs planted personas" value={res.external.ari.toFixed(3)}
          sub={`NMI ${res.external.nmi.toFixed(3)} · purity ${fmt.pct(res.external.purity)}`} />
      </div>

      <div className={`grid g2 ${live.loading ? 'stale' : ''}`} style={{ marginTop: 16 }}>
        <ChartCard title="Users in PCA space" sub={`PC1 × PC2 (${fmt.pct(r.pca_variance[0] + r.pca_variance[1], 0)} of variance); colour and marker shape = cluster`}
          height={360}
          option={{
            ...base(p), legend: { ...base(p).legend, data: clusters.map(name), type: 'scroll' },
            grid: { left: 40, right: 12, top: 40, bottom: 30 },
            xAxis: { type: 'value', ...axisStyle(p), name: 'PC1', nameLocation: 'middle', nameGap: 20 },
            yAxis: { type: 'value', ...axisStyle(p), name: 'PC2' },
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const d = x as { seriesName: string; value: number[] };
              return `user ${d.value[2]}<br/>${d.seriesName}`;
            } },
            series: clusters.map((c) => ({
              name: name(c), type: 'scatter', symbol: c === -1 ? 'circle' : SYMBOLS[c % SYMBOLS.length], symbolSize: c === -1 ? 5 : 8,
              data: res.points.filter((pt) => pt.c === c).map((pt) => [pt.x, pt.y, pt.user_id]),
              itemStyle: { color: colorOf(c), borderColor: p.surface, borderWidth: 1, opacity: c === -1 ? 0.6 : 0.9 },
            })),
          }} />
        <ChartCard title="What each cluster does" sub="mean activity mix per cluster (stacked to 100%)" height={360}
          option={{
            ...base(p), legend: { ...base(p).legend, data: SHARES.map((s) => s.replace('share_', '')) },
            grid: { left: 170, right: 16, top: 34, bottom: 24 },
            xAxis: { type: 'value', max: 1, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            yAxis: { type: 'category', inverse: true, data: res.profiles.map((x) => `${name(x.cluster)} (${x.size})`), ...axisStyle(p), axisLabel: { color: p.text2 } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => fmt.pct(v as number) },
            series: SHARES.map((s, i) => ({
              name: s.replace('share_', ''), type: 'bar', stack: 'mix', barMaxWidth: 22,
              data: res.profiles.map((x) => x[s] as number),
              itemStyle: { color: p.series[i], borderColor: p.surface, borderWidth: 1 },
            })),
          }}
          table={res.profiles.map((x) => ({ ...x, cluster: name(x.cluster) }))}
          cols={[{ key: 'cluster', label: 'Cluster' }, { key: 'size', label: 'Users', num: true },
            ...SHARES.map((s) => ({ key: s, label: s.replace('share_', ''), num: true, pct: true, digits: 0 })),
            { key: 'sessions_per_week', label: 'Sessions/wk', num: true, digits: 1 },
            { key: 'avg_duration', label: 'Avg min', num: true }, { key: 'avg_intensity', label: 'Intensity', num: true, pct: true, digits: 0 },
            { key: 'age', label: 'Age', num: true }, { key: 'vo2max', label: 'VO2max', num: true, digits: 1 }]} />
      </div>

      <div className={`grid g2 ${live.loading ? 'stale' : ''}`} style={{ marginTop: 16 }}>
        <ChartCard title="Clusters × planted personas" sub="how users of each true persona were split; a clean diagonal = good recovery"
          height={280}
          option={{
            ...base(p), grid: { left: 150, right: 16, top: 10, bottom: 60 },
            xAxis: { type: 'category', data: res.contingency.personas, ...axisStyle(p), axisLabel: { color: p.text2, rotate: 20 } },
            yAxis: { type: 'category', inverse: true, data: res.contingency.clusters.map(name), ...axisStyle(p), axisLabel: { color: p.text2 } },
            visualMap: { min: 0, max: Math.max(...res.contingency.counts.flat()), show: false, inRange: { color: [p.seq[0], p.seq[6]] } },
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const v = (x as { value: number[] }).value;
              return `${name(res.contingency.clusters[v[1]])} · ${res.contingency.personas[v[0]]}<br/><b>${v[2]}</b> users`;
            } },
            series: [{ type: 'heatmap', data: res.contingency.counts.flatMap((row, i) => row.map((v, j) => [j, i, v])),
              itemStyle: { borderColor: p.surface, borderWidth: 2 },
              label: { show: true, color: p.text, textBorderColor: p.surface, textBorderWidth: 2,
                formatter: (x: unknown) => String((x as { value: number[] }).value[2]) } }],
          }} />
        {res.dendrogram ? (
          <ChartCard title="Dendrogram (last 30 merges)" sub="leaf labels are sub-cluster sizes; cut height gives the k clusters" height={280}
            option={{
              ...base(p), grid: { left: 50, right: 12, top: 10, bottom: 30 },
              xAxis: { type: 'value', min: 0, max: res.dendrogram.leaves.length * 10, show: false },
              yAxis: { type: 'value', ...axisStyle(p), name: 'merge distance', min: 0,
                max: Math.ceil(Math.max(...res.dendrogram.dcoord.flat()) * 1.05) },
              tooltip: { show: false },
              series: [
                { type: 'lines', coordinateSystem: 'cartesian2d', polyline: true, silent: true,
                  lineStyle: { color: p.series[0], width: 1.5 },
                  data: res.dendrogram.icoord.map((xs, i) => ({ coords: xs.map((x, j) => [x, res.dendrogram!.dcoord[i][j]]) })) },
                { type: 'scatter', symbolSize: 1, data: res.dendrogram.leaves.map((l) => [l.x, 0, l.size]),
                  label: { show: true, position: 'bottom', color: p.muted, fontSize: 10,
                    formatter: (x: unknown) => String((x as { value: number[] }).value[2]) } },
              ],
            }} />
        ) : (
          <Card title="Cluster sizes">
            <DataTable rows={clusters.map((c) => ({ cluster: name(c), users: res.sizes[String(c)] }))}
              cols={[{ key: 'cluster', label: 'Cluster' }, { key: 'users', label: 'Users', num: true }]} />
            {res.medoids && <div className="note" style={{ marginTop: 10 }}>Medoids are real users (representative members):{' '}
              {res.medoids.map((m) => <code key={m}>#{res.points[m]?.user_id} </code>)}</div>}
          </Card>
        )}
      </div>

      <SectionTitle title="Choosing k and eps" sub="k-means over k = 2…10, and the k-distance plot for DBSCAN" />
      <div className="grid g3">
        <ChartCard title="Elbow: SSE vs k" height={240}
          option={{
            ...base(p), xAxis: { type: 'category', data: r.k_sweep.map((s) => s.k), ...axisStyle(p), name: 'k', nameLocation: 'middle', nameGap: 24 },
            yAxis: { type: 'value', ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.compact(v) } },
            tooltip: { ...base(p).tooltip, trigger: 'axis' },
            series: [{ type: 'line', data: r.k_sweep.map((s) => s.sse), symbolSize: 8, lineStyle: { width: 2, color: p.series[0] },
              itemStyle: { color: p.series[0], borderColor: p.surface, borderWidth: 2 } }],
          }}
          table={r.k_sweep} cols={[{ key: 'k', label: 'k', num: true }, { key: 'sse', label: 'SSE', num: true },
            { key: 'silhouette', label: 'Silhouette', num: true, digits: 3 }, { key: 'davies_bouldin', label: 'DB', num: true, digits: 3 }]} />
        <ChartCard title="Silhouette vs k" sub={`peaks at k = ${r.k_sweep.reduce((a, b) => (b.silhouette > a.silhouette ? b : a)).k}`} height={240}
          option={{
            ...base(p), xAxis: { type: 'category', data: r.k_sweep.map((s) => s.k), ...axisStyle(p), name: 'k', nameLocation: 'middle', nameGap: 24 },
            yAxis: { type: 'value', ...axisStyle(p) },
            tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => (v as number).toFixed(3) },
            series: [{ type: 'line', data: r.k_sweep.map((s) => s.silhouette), symbolSize: 8, lineStyle: { width: 2, color: p.series[0] },
              itemStyle: { color: p.series[0], borderColor: p.surface, borderWidth: 2 } }],
          }} />
        <ChartCard title="Sorted 9-distance (DBSCAN eps)" sub="the knee suggests eps; density varies, so one eps can't fit all personas" height={240}
          option={{
            ...base(p), xAxis: { type: 'value', ...axisStyle(p), name: 'users (sorted)', nameLocation: 'middle', nameGap: 24 },
            yAxis: { type: 'value', ...axisStyle(p), name: 'distance' },
            tooltip: { ...base(p).tooltip, trigger: 'axis' },
            series: [{ type: 'line', showSymbol: false, data: r.k_distance.map((d, i) => [i, d]), lineStyle: { width: 2, color: p.series[0] } }],
          }} />
      </div>

      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Algorithm comparison" sub="pipeline defaults (k = 5, Ward linkage, eps = 1.2)">
          <DataTable rows={r.comparison as unknown as Record<string, unknown>[]} cols={[
            { key: 'algorithm', label: 'Algorithm' }, { key: 'n_clusters', label: 'Clusters', num: true },
            { key: 'silhouette', label: 'Silhouette', num: true, digits: 3 }, { key: 'davies_bouldin', label: 'DB', num: true, digits: 3 },
            { key: 'ari', label: 'ARI', num: true, digits: 3 }, { key: 'purity', label: 'Purity', num: true, pct: true },
            { key: 'ms', label: 'ms', num: true }]} />
        </Card>
        <Recovery items={r.comparison.map((c) => ({
          label: `${c.algorithm}: agreement with the 5 planted personas`, value: `ARI ${c.ari.toFixed(3)}`,
          ok: c.ari > 0.7, note: `${c.n_clusters} clusters, purity ${fmt.pct(c.purity)}`,
        }))} />
      </div>
      {real.length === 0 && <div className="note">No clusters found with these parameters.</div>}
    </>
  );
}
