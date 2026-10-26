import { useEffect, useState } from 'react';
import type { EChartsOption } from 'echarts';
import { useGet, useRun } from '../api/client';
import MapView from '../components/MapView';
import { Card, Chart, ChartCard, DataTable, ErrorBox, Legend, Loading, PageHead, Recovery, SectionTitle, Slider, Tile } from '../components/ui';
import { axisStyle, barItem, base, fmt, Palette, usePalette } from '../theme/chart';

interface Level { k: number; candidates: number; pruned: number; frequent: number }
interface Seq {
  params: { min_support: number; max_gap: number | null }; n_sequences: number; avg_elements: number; n_patterns: number; ms: number;
  stats: Level[]; patterns: { text: string; length: number; elements: number; support: number }[];
  singletons: { text: string; support: number }[];
  planted?: { text: string; support: number | null; found: boolean }[];
}
interface Hot { params: { eps_m: number; min_samples: number; spacing_m: number }; n_points: number; n_tracks: number; n_clusters: number;
  noise_points: number; ms: number; clusters: { cluster: number; points: number; landmark: string; sample: number[][] }[]; noise_sample: number[][] }
interface Routes { params: { eps_m: number; min_samples: number }; n_tracks: number; n_clusters: number; noise: number;
  ms_hausdorff: number; ms_dbscan: number;
  clusters: { cluster: number; size: number; landmark: string; medoid_workout: number; track: number[][];
    activities: Record<string, number>; majority_route: number; purity: number }[];
  evaluation: { planted_routes: number; routes_found: number; purity: number; popular_recall: number; personal_as_noise: number;
    route_names: Record<string, string> } }
interface SegEval { n_runs: number; beta: number; boundary_precision: number; boundary_recall: number; boundary_f1: number;
  phase_accuracy: number; interval_detection_accuracy: number; ms_per_run: number;
  beta_sweep: { beta: number; boundary_precision: number; boundary_recall: number; boundary_f1: number }[] }
interface U7Rest { hotspots: Hot; routes: Routes; segmentation: SegEval; compression: { epsilon_m: number; mean_kept: number; tracks: number };
  example_workout: number }
interface Segments { workout_id: number; speed_kmh: number[]; hr: number[]; lat: number[]; lon: number[];
  segments: { start: number; end: number; mean_speed: number; phase: string }[]; change_points: number[]; kind: string;
  ref_speed_kmh: number; dt: number; simplified: { points: number; of: number; epsilon_m: number; lat: number[]; lon: number[] };
  truth: { start_idx: number; end_idx: number; phase: string }[] }

const PHASES = ['warmup', 'steady', 'fast', 'recovery', 'cooldown', 'stop'];
const phaseColor = (p: Palette, ph: string) => (ph === 'stop' ? p.muted : p.series[[0, 1, 2, 3, 6][PHASES.indexOf(ph)] ?? 0]);
const COARSE: Record<string, string> = { warmup: 'warmup', steady: 'steady', long: 'steady', tempo: 'steady', stop: 'stop',
  interval_fast: 'fast', interval_recovery: 'recovery', cooldown: 'cooldown' };

export default function Sequences() {
  const p = usePalette();
  const seqRep = useGet<Seq>('/api/sequences/report');
  const rest = useGet<U7Rest>('/api/trajectories/report');
  const seqLive = useRun<{ min_support: number; max_gap: number | null }, Seq>('/api/sequences/run');
  const routeLive = useRun<{ eps: number; min_samples: number }, Routes>('/api/trajectories/routes');
  const [sp, setSp] = useState({ min_support: 0.025, max_gap: 4 });
  const [rp, setRp] = useState({ eps: 150, min_samples: 8 });
  const [wid, setWid] = useState<number | null>(null);
  const [beta, setBeta] = useState(1.0);
  const [showTruth, setShowTruth] = useState(false);
  useEffect(() => { if (rest.data && wid == null) setWid(rest.data.example_workout); }, [rest.data, wid]);
  const seg = useGet<Segments>(wid != null ? `/api/trajectories/${wid}/segments?beta=${beta}` : null);

  if (seqRep.error || rest.error) return <ErrorBox error={(seqRep.error ?? rest.error)!} />;
  if (!seqRep.data || !rest.data) return <Loading />;
  const s = seqLive.data ?? seqRep.data;
  const routes = routeLive.data ?? rest.data.routes;
  const hs = rest.data.hotspots;
  const se = rest.data.segmentation;
  const sd = seg.data;
  const vTop = sd ? Math.max(...sd.speed_kmh) : 1;

  return (
    <>
      <PageHead code="U7" title="Sequential patterns & trajectory mining">
        Two kinds of ordered data. Weekly training logs are sequences of session types, mined with GSP. GPS
        tracks are trajectories: dense areas (hotspots), recurring routes (clusters of similar tracks) and the
        phases inside a run (change points in speed).
      </PageHead>

      <SectionTitle title="Weekly routines (GSP)" sub="one sequence per user-week; elements are the sessions of one day" />
      <div className="controls">
        <Slider label="min support" value={sp.min_support} min={0.01} max={0.2} step={0.005}
          onChange={(v) => setSp({ ...sp, min_support: v })} format={(v) => fmt.pct(v, 1)} />
        <Slider label="max gap (days)" value={sp.max_gap} min={1} max={6} step={1} onChange={(v) => setSp({ ...sp, max_gap: v })} />
        <button className="btn primary" disabled={seqLive.loading} onClick={() => seqLive.run(sp)}>{seqLive.loading ? 'Mining…' : 'Run GSP'}</button>
      </div>
      {seqLive.error && <div className="error" style={{ marginBottom: 16 }}>{seqLive.error}</div>}
      <div className={`grid g4 ${seqLive.loading ? 'stale' : ''}`}>
        <Tile label="Sequences (user-weeks)" value={fmt.n(s.n_sequences)} sub={`avg ${s.avg_elements.toFixed(1)} training days`} />
        <Tile label="Frequent patterns" value={fmt.n(s.n_patterns)} sub={`min support ${fmt.pct(s.params.min_support, 1)}, max gap ${s.params.max_gap ?? '∞'} d`} />
        <Tile label="Longest pattern" value={Math.max(...s.patterns.map((x) => x.length), 1)} sub="items" />
        <Tile label="GSP time" value={`${fmt.n(s.ms)} ms`} sub={`${s.stats.length} levels`} />
      </div>
      <div className={`grid g3 ${seqLive.loading ? 'stale' : ''}`} style={{ marginTop: 16 }}>
        <Card className="span2" title="Frequent sequential patterns" sub="⟨A B⟩ = A, then B on a later day of the same week (within the max gap)">
          <DataTable rows={s.patterns as unknown as Record<string, unknown>[]} height={320} cols={[
            { key: 'text', label: 'Pattern', render: (x) => <code>{x.text as string}</code> },
            { key: 'length', label: 'Items', num: true }, { key: 'support', label: 'Support', num: true, pct: true }]} />
        </Card>
        <div className="stack">
          <ChartCard title="GSP level by level" height={200}
            option={{
              ...base(p), legend: { ...base(p).legend, data: ['candidates', 'pruned', 'frequent'] },
              xAxis: { type: 'category', data: s.stats.map((l) => `k=${l.k}`), ...axisStyle(p) },
              yAxis: { type: 'value', ...axisStyle(p) },
              tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
              series: (['candidates', 'pruned', 'frequent'] as const).map((k, i) => ({ name: k, type: 'bar', barMaxWidth: 12,
                data: s.stats.map((l) => l[k]), itemStyle: barItem(p.series[i]) })),
            }}
            table={s.stats as unknown as Record<string, unknown>[]} cols={[{ key: 'k', label: 'k', num: true },
              { key: 'candidates', label: 'Candidates', num: true }, { key: 'pruned', label: 'Pruned', num: true },
              { key: 'frequent', label: 'Frequent', num: true }]} />
          {s.planted && <Recovery items={s.planted.map((x) => ({ label: x.text, ok: x.found,
            value: x.found ? fmt.pct(x.support!) : 'below threshold' }))} />}
        </div>
      </div>

      <SectionTitle title="GPS hotspots" sub={`DBSCAN over points resampled every ${hs.params.spacing_m} m along ${fmt.n(hs.n_tracks)} tracks (eps ${hs.params.eps_m} m, min ${hs.params.min_samples} points)`} />
      <div className="grid g3">
        <Card className="span2" title={`${hs.n_clusters} dense areas from ${fmt.n(hs.n_points)} points`}
          sub="each colour is one density-connected cluster; grey = noise (one-off personal routes)">
          <MapView height={420} dots={[
            ...hs.noise_sample.slice(0, 900).map(([la, lo]) => ({ lat: la, lon: lo, color: p.axis, r: 1.5 })),
            ...hs.clusters.slice(0, 8).flatMap((c, i) => c.sample.map(([la, lo]) => ({ lat: la, lon: lo, color: p.series[i], r: 2.5,
              label: `${c.landmark}: ${fmt.n(c.points)} points` }))),
          ]} />
          <Legend items={hs.clusters.slice(0, 8).map((c, i) => ({ label: `${c.landmark} (${fmt.n(c.points)})`, color: p.series[i] }))} />
        </Card>
        <Card title="Hotspots" sub={`clusters named after the nearest public landmark · ${fmt.n(hs.ms)} ms`}>
          <DataTable rows={hs.clusters.map((c) => ({ landmark: c.landmark, points: c.points }))} height={400} cols={[
            { key: 'landmark', label: 'Nearest landmark' }, { key: 'points', label: 'Points', num: true }]} />
        </Card>
      </div>

      <SectionTitle title="Popular routes" sub="tracks resampled to 20 points; Hausdorff distance between every pair; DBSCAN on that matrix" />
      <div className="controls">
        <Slider label="eps (m)" value={rp.eps} min={40} max={400} step={10} onChange={(v) => setRp({ ...rp, eps: v })} />
        <Slider label="min tracks" value={rp.min_samples} min={2} max={40} step={1} onChange={(v) => setRp({ ...rp, min_samples: v })} />
        <button className="btn primary" disabled={routeLive.loading} onClick={() => routeLive.run(rp)}>{routeLive.loading ? 'Clustering…' : 'Re-cluster'}</button>
        <span className="note">reuses the cached {fmt.n(routes.n_tracks)}×{fmt.n(routes.n_tracks)} Hausdorff matrix</span>
      </div>
      <div className={`grid g3 ${routeLive.loading ? 'stale' : ''}`}>
        <Card className="span2" title={`${routes.n_clusters} route clusters · ${routes.noise} tracks are noise`} sub="medoid track of each cluster (click a row to segment it below)">
          <MapView height={420} tracks={routes.clusters.slice(0, 8).map((c, i) => ({ id: c.cluster, points: c.track as [number, number][],
            color: p.series[i], weight: 4, label: `${c.landmark} · ${c.size} tracks` }))} />
          <Legend items={routes.clusters.slice(0, 8).map((c, i) => ({ label: `${c.landmark} (${c.size})`, color: p.series[i], line: true }))} />
        </Card>
        <div className="stack">
          <Card title="Clusters">
            <DataTable rows={routes.clusters.map((c) => ({ ...c, acts: Object.entries(c.activities).map(([k, v]) => `${k} ${v}`).join(', ') }))}
              height={250} cols={[
                { key: 'landmark', label: 'Route', render: (x) => <a href="#" onClick={(ev) => { ev.preventDefault(); setWid(x.medoid_workout as number); }}>{x.landmark as string}</a> },
                { key: 'size', label: 'Tracks', num: true }, { key: 'purity', label: 'Purity', num: true, pct: true, digits: 0 },
                { key: 'acts', label: 'Activities' }]} />
          </Card>
          <Recovery items={[
            { label: 'Planted popular routes found', value: `${routes.evaluation.routes_found} / ${routes.evaluation.planted_routes}`,
              ok: routes.evaluation.routes_found === routes.evaluation.planted_routes },
            { label: 'Cluster purity', value: fmt.pct(routes.evaluation.purity), ok: routes.evaluation.purity > 0.9 },
            { label: 'Popular-route tracks recovered', value: fmt.pct(routes.evaluation.popular_recall), ok: routes.evaluation.popular_recall > 0.8 },
            { label: 'Personal one-off routes left as noise', value: fmt.pct(routes.evaluation.personal_as_noise) },
          ]} />
        </div>
      </div>

      <SectionTitle title="Segmenting a run" sub="binary segmentation of the GPS speed profile, penalty β·σ²·log n; segments labelled by speed relative to the run's typical pace" />
      <div className="controls">
        <label className="field"><span>Workout id</span>
          <input type="number" value={wid ?? ''} onChange={(e) => setWid(Number(e.target.value) || null)} style={{ width: 110 }} /></label>
        <Slider label="β (penalty)" value={beta} min={0.3} max={5} step={0.1} onChange={setBeta} format={(v) => v.toFixed(1)} />
        <label className="check"><input type="checkbox" checked={showTruth} onChange={(e) => setShowTruth(e.target.checked)} />
          overlay planted phases</label>
        {sd && <span className="note">detected: <b>{sd.kind}</b> run · {sd.change_points.length} change points · typical pace {sd.ref_speed_kmh.toFixed(1)} km/h</span>}
      </div>
      {seg.error && <div className="error">{seg.error}</div>}
      {sd && (
        <div className={`grid g2 ${seg.loading ? 'stale' : ''}`}>
          <Card title="Speed profile with detected segments" sub={showTruth ? 'top band = planted phases, shaded = detected' : 'shaded by detected phase'}>
            <Chart height={300} option={{
              ...base(p),
              xAxis: { type: 'category', data: sd.speed_kmh.map((_, i) => `${Math.floor(i * sd.dt / 60)}′`), ...axisStyle(p),
                axisLabel: { ...axisStyle(p).axisLabel, interval: Math.max(1, Math.floor(sd.speed_kmh.length / 8)) } },
              yAxis: { type: 'value', ...axisStyle(p), name: 'km/h', max: showTruth ? Math.ceil(vTop * 1.15) : undefined },
              tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => `${(v as number).toFixed(1)} km/h` },
              series: [
                { type: 'line', data: sd.speed_kmh, showSymbol: false, lineStyle: { width: 1.5, color: p.text2 }, itemStyle: { color: p.text2 },
                  markArea: { silent: true, data: sd.segments.map((g) => [
                    { xAxis: g.start, itemStyle: { color: phaseColor(p, g.phase), opacity: 0.22 } }, { xAxis: Math.max(g.start, g.end - 1) }]) },
                  markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: p.text2, width: 1, type: 'solid' },
                    data: sd.change_points.map((c) => ({ xAxis: c })) } },
                ...(showTruth ? [{ type: 'line' as const, data: [], markArea: { silent: true, data: sd.truth.map((t) => [
                  { xAxis: t.start_idx, yAxis: vTop * 1.06, itemStyle: { color: phaseColor(p, COARSE[t.phase] ?? 'steady'), opacity: 0.9 } },
                  { xAxis: Math.max(t.start_idx, t.end_idx - 1), yAxis: vTop * 1.14 }]) } }] : []),
              ] as EChartsOption['series'],
            }} />
            <Legend items={PHASES.map((ph) => ({ label: ph, color: phaseColor(p, ph) }))} />
          </Card>
          <Card title="The same segments on the map" sub={`Douglas-Peucker keeps ${sd.simplified.points} of ${sd.simplified.of} points at ${sd.simplified.epsilon_m} m tolerance`}>
            <MapView height={330} tracks={sd.segments.map((g, i) => ({ id: i, color: phaseColor(p, g.phase), weight: 5,
              label: `${g.phase} · ${(g.mean_speed * 3.6).toFixed(1)} km/h`,
              points: sd.lat.slice(g.start, g.end + 1).map((la, j) => [la, sd.lon[g.start + j]] as [number, number]) }))} />
          </Card>
        </div>
      )}
      <div className="grid g2" style={{ marginTop: 16 }}>
        <ChartCard title="Choosing β" sub={`boundary precision / recall / F1 on ${se.beta_sweep.length ? 300 : 0} labelled runs (±2 samples)`} height={250}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['precision', 'recall', 'F1'] },
            xAxis: { type: 'category', data: se.beta_sweep.map((b) => b.beta), ...axisStyle(p), name: 'β', nameLocation: 'middle', nameGap: 24 },
            yAxis: { type: 'value', min: 0, max: 1, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => fmt.pct(v as number) },
            series: (['boundary_precision', 'boundary_recall', 'boundary_f1'] as const).map((k, i) => ({
              name: ['precision', 'recall', 'F1'][i], type: 'line', data: se.beta_sweep.map((b) => b[k]), symbolSize: 7,
              lineStyle: { width: 2, color: p.series[i] }, itemStyle: { color: p.series[i], borderColor: p.surface, borderWidth: 2 } })),
          }}
          table={se.beta_sweep} cols={[{ key: 'beta', label: 'β', num: true, digits: 1 },
            { key: 'boundary_precision', label: 'Precision', num: true, pct: true }, { key: 'boundary_recall', label: 'Recall', num: true, pct: true },
            { key: 'boundary_f1', label: 'F1', num: true, pct: true }]} />
        <Recovery items={[
          { label: `Change-point F1 (β = ${se.beta}, ${se.n_runs} runs)`, value: fmt.pct(se.boundary_f1), ok: se.boundary_f1 > 0.7,
            note: `precision ${fmt.pct(se.boundary_precision)}, recall ${fmt.pct(se.boundary_recall)}` },
          { label: 'Per-sample phase accuracy', value: fmt.pct(se.phase_accuracy), ok: se.phase_accuracy > 0.7 },
          { label: 'Interval sessions recognised', value: fmt.pct(se.interval_detection_accuracy), ok: se.interval_detection_accuracy > 0.75 },
          { label: 'Douglas-Peucker compression', value: `${fmt.pct(rest.data.compression.mean_kept)} of points kept`,
            note: `ε = ${rest.data.compression.epsilon_m} m over ${fmt.n(rest.data.compression.tracks)} tracks` },
        ]} />
      </div>
    </>
  );
}
