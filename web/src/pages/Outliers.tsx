import { useState } from 'react';
import { useGet, useRun } from '../api/client';
import MapView from '../components/MapView';
import { Card, Chart, ChartCard, DataTable, ErrorBox, Loading, PageHead, Pill, Recovery, SectionTitle, Select, Slider, Tile } from '../components/ui';
import { axisStyle, barItem, base, fmt, usePalette, valueLabel } from '../theme/chart';

interface MethodEval {
  method: string; flagged: number; tp: number; fp: number; fn: number; precision: number; recall: number; f1: number; ms: number;
  per_type: Record<string, { n: number; detected: number; recall: number }>; score_hist: number[];
  top: { workout_id: number; activity: string; score: number; reasons: string[]; truth: string | null }[];
}
interface Example { fault: string; workout_id: number; activity: string; reasons: string[]; hr: number[]; lat: number[] | null; lon: number[] | null }
interface UserEval { flagged: number; tp: number; precision: number; recall: number; per_type: Record<string, { n: number; detected: number }> }
interface U6 {
  n_workouts: number; features: string[]; n_true_faults: number; fault_counts: Record<string, number>;
  methods: Record<string, MethodEval>; comparison: { method: string; flagged: number; precision: number; recall: number; f1: number; ms: number }[];
  recall_matrix: Record<string, Record<string, number>>; examples: Example[];
  users: { evaluation: Record<string, UserEval>; flagged: { user_id: number; reasons: string[]; lof: number; iforest: number }[];
    scatter: { user_id: number; lof: number; iforest: number; flagged: boolean }[] };
}
interface Params { method: string; z: number; k: number; contamination: number; lof_k: number; n_trees: number }

const METHODS = [
  { value: 'ensemble', label: 'Ensemble (rules ∪ duplicates ∪ 2-of-3 statistical)' }, { value: 'rules', label: 'Domain rules' },
  { value: 'zscore', label: 'z-score (per feature)' }, { value: 'iqr', label: 'IQR fences (per feature)' },
  { value: 'lof', label: 'Local Outlier Factor' }, { value: 'iforest', label: 'Isolation Forest' },
  { value: 'duplicates', label: 'Duplicate stream fingerprints' },
];
const FAULT_LABEL: Record<string, string> = {
  hr_spike: 'HR spikes', hr_flatline: 'HR flat-line', hr_dropout: 'HR drop-outs', gps_teleport: 'GPS teleport',
  car_speed: 'Car-speed "run"', gps_replay: 'Replayed GPS file', calorie_mismatch: 'Calorie mismatch',
  copied_workout: 'Cloned-account copy',
};

export default function Outliers() {
  const p = usePalette();
  const rep = useGet<U6>('/api/outliers/report');
  const live = useRun<Params, MethodEval>('/api/outliers/run');
  const [prm, setPrm] = useState<Params>({ method: 'ensemble', z: 4, k: 3, contamination: 0.03, lof_k: 20, n_trees: 100 });
  const [ex, setEx] = useState(0);
  if (rep.error) return <ErrorBox error={rep.error} />;
  if (!rep.data) return <Loading />;
  const r = rep.data;
  const m = live.data ?? r.methods[prm.method] ?? r.methods.ensemble;
  const faults = Object.keys(FAULT_LABEL).filter((f) => r.fault_counts[f]);
  const methods = Object.keys(r.recall_matrix);
  const e = r.examples[ex];
  const ue = r.users.evaluation['rules + consistency + clones'];

  return (
    <>
      <PageHead code="U6" title="Outlier detection: faulty sensors & spoofing">
        Every workout is summarised from its HR and GPS streams (peak HR, flat-line share, drop-outs, max GPS step,
        speed, calories vs the MET formula…). Detectors run per activity, because a 25 km/h ride is normal and a
        25 km/h run is not. {fmt.n(r.n_true_faults)} of {fmt.n(r.n_workouts)} workouts carry a planted fault.
      </PageHead>

      <div className="controls">
        <Select label="Detector" value={prm.method} options={METHODS} onChange={(v) => { setPrm({ ...prm, method: v }); live.setData(null); }} />
        {prm.method === 'zscore' && <Slider label="|z| >" value={prm.z} min={2} max={8} step={0.5} onChange={(v) => setPrm({ ...prm, z: v })} />}
        {['iqr', 'ensemble'].includes(prm.method) && <Slider label="IQR fence k" value={prm.k} min={1} max={6} step={0.5} onChange={(v) => setPrm({ ...prm, k: v })} />}
        {['lof', 'iforest', 'ensemble'].includes(prm.method) && <Slider label="contamination" value={prm.contamination} min={0.005} max={0.15} step={0.005}
          onChange={(v) => setPrm({ ...prm, contamination: v })} format={(v) => fmt.pct(v, 1)} />}
        {['lof', 'ensemble'].includes(prm.method) && <Slider label="LOF neighbours" value={prm.lof_k} min={5} max={60} step={1} onChange={(v) => setPrm({ ...prm, lof_k: v })} />}
        {prm.method === 'iforest' && <Slider label="trees" value={prm.n_trees} min={20} max={300} step={10} onChange={(v) => setPrm({ ...prm, n_trees: v })} />}
        <button className="btn primary" disabled={live.loading} onClick={() => live.run(prm)}>{live.loading ? 'Detecting…' : 'Run'}</button>
      </div>
      {live.error && <div className="error" style={{ marginBottom: 16 }}>{live.error}</div>}

      <div className={`grid g4 ${live.loading ? 'stale' : ''}`}>
        <Tile label="Workouts flagged" value={fmt.n(m.flagged)} sub={`${m.tp} true faults · ${m.fp} false alarms`} />
        <Tile label="Precision" value={fmt.pct(m.precision)} sub="flagged workouts that are real faults" />
        <Tile label="Recall" value={fmt.pct(m.recall)} sub={`${m.fn} faults missed`} />
        <Tile label="F1" value={m.f1.toFixed(3)} sub={`${fmt.n(m.ms)} ms over ${fmt.n(r.n_workouts)} workouts`} />
      </div>

      <div className={`grid g2 ${live.loading ? 'stale' : ''}`} style={{ marginTop: 16 }}>
        <ChartCard title="Recall by fault type" sub="which kinds of fault this detector catches" height={280}
          option={{
            ...base(p), grid: { left: 150, right: 50, top: 6, bottom: 24 },
            xAxis: { type: 'value', max: 1, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            yAxis: { type: 'category', inverse: true, data: faults.map((f) => FAULT_LABEL[f]), ...axisStyle(p), axisLabel: { color: p.text2 } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => fmt.pct(v as number) },
            series: [{ type: 'bar', barMaxWidth: 14, data: faults.map((f) => m.per_type[f]?.recall ?? 0), itemStyle: barItem(p.series[0], true),
              label: { show: true, position: 'right', color: p.text2, formatter: valueLabel((n) => fmt.pct(n, 0)) } }],
          }}
          table={faults.map((f) => ({ fault: FAULT_LABEL[f], n: m.per_type[f]?.n ?? 0, detected: m.per_type[f]?.detected ?? 0,
            recall: m.per_type[f]?.recall ?? 0 }))}
          cols={[{ key: 'fault', label: 'Fault' }, { key: 'n', label: 'Planted', num: true }, { key: 'detected', label: 'Detected', num: true },
            { key: 'recall', label: 'Recall', num: true, pct: true }]} />
        <Card title="Highest-scoring workouts" sub="with the reason the detector gives and the planted truth">
          <DataTable rows={m.top.map((t) => ({ ...t, reasons: t.reasons.join(', ') }))} height={280} cols={[
            { key: 'workout_id', label: 'Workout', num: true }, { key: 'activity', label: 'Activity' },
            { key: 'score', label: 'Score', num: true, digits: 2 }, { key: 'reasons', label: 'Reason', wrap: true },
            { key: 'truth', label: 'Truth', render: (x) => x.truth ? <Pill kind="bad">{FAULT_LABEL[x.truth as string] ?? String(x.truth)}</Pill>
              : <Pill kind="neutral">clean</Pill> }]} />
        </Card>
      </div>

      <SectionTitle title="Every detector vs every fault" sub="recall per planted fault type; the ensemble combines their strengths" />
      <div className="grid g2">
        <ChartCard title="Recall matrix" sub="darker = more of that fault caught" height={300}
          option={{
            ...base(p), grid: { left: 90, right: 16, top: 10, bottom: 70 },
            xAxis: { type: 'category', data: faults.map((f) => FAULT_LABEL[f]), ...axisStyle(p), axisLabel: { color: p.text2, rotate: 30, fontSize: 11 } },
            yAxis: { type: 'category', inverse: true, data: methods, ...axisStyle(p), axisLabel: { color: p.text2 } },
            visualMap: { min: 0, max: 1, show: false, inRange: { color: [p.seq[0], p.seq[6]] } },
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const v = (x as { value: number[] }).value;
              return `${methods[v[1]]} · ${FAULT_LABEL[faults[v[0]]]}<br/>recall <b>${fmt.pct(v[2])}</b>`;
            } },
            series: [{ type: 'heatmap', itemStyle: { borderColor: p.surface, borderWidth: 2 },
              data: methods.flatMap((mm, i) => faults.map((f, j) => [j, i, r.recall_matrix[mm][f] ?? 0])),
              label: { show: true, fontSize: 10, color: p.text, textBorderColor: p.surface, textBorderWidth: 2,
                formatter: (x: unknown) => `${Math.round((x as { value: number[] }).value[2] * 100)}` } }],
          }} />
        <ChartCard title="Precision vs recall by detector" sub="pipeline defaults" height={300}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['precision', 'recall'] },
            grid: { left: 90, right: 16, top: 30, bottom: 24 },
            xAxis: { type: 'value', max: 1, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            yAxis: { type: 'category', inverse: true, data: r.comparison.map((c) => c.method), ...axisStyle(p), axisLabel: { color: p.text2 } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => fmt.pct(v as number) },
            series: (['precision', 'recall'] as const).map((k, i) => ({ name: k, type: 'bar', barMaxWidth: 10, barGap: '20%',
              data: r.comparison.map((c) => c[k]), itemStyle: barItem(p.series[i], true) })),
          }}
          table={r.comparison} cols={[{ key: 'method', label: 'Detector' }, { key: 'flagged', label: 'Flagged', num: true },
            { key: 'precision', label: 'Precision', num: true, pct: true }, { key: 'recall', label: 'Recall', num: true, pct: true },
            { key: 'f1', label: 'F1', num: true, digits: 3 }, { key: 'ms', label: 'ms', num: true }]} />
      </div>

      <SectionTitle title="What a fault looks like" sub="one detected example per fault type" />
      <div className="controls" style={{ marginBottom: 12 }}>
        <div className="seg">
          {r.examples.map((x, i) => <button key={x.fault} className={i === ex ? 'on' : ''} onClick={() => setEx(i)}>{FAULT_LABEL[x.fault]}</button>)}
        </div>
      </div>
      {e && (
        <div className="grid g2">
          <Card title={`Workout ${e.workout_id} · ${e.activity}`} sub={<>Flagged because: <b>{e.reasons.join(', ')}</b></>}>
            <Chart height={260} option={{
              ...base(p),
              xAxis: { type: 'category', data: e.hr.map((_, i) => `${Math.floor(i * 15 / 60)}′`), ...axisStyle(p),
                axisLabel: { ...axisStyle(p).axisLabel, interval: Math.max(1, Math.floor(e.hr.length / 8)) } },
              yAxis: { type: 'value', ...axisStyle(p), name: 'bpm' },
              tooltip: { ...base(p).tooltip, trigger: 'axis' },
              series: [{ type: 'line', data: e.hr, showSymbol: false, lineStyle: { width: 2, color: p.series[0] },
                markLine: { silent: true, symbol: 'none', lineStyle: { color: p.critical, type: 'solid', width: 1 },
                  label: { color: p.text2, formatter: '220 bpm' }, data: [{ yAxis: 220 }] } }],
            }} />
            <div className="note">Heart-rate stream (15 s samples). The red line marks 220 bpm, beyond any human maximum.</div>
          </Card>
          <Card title="GPS track" sub={e.lat ? 'teleports show as long straight jumps; replays overlay another user\'s file' : 'no GPS for this activity'}>
            {e.lat && e.lon ? (
              <MapView height={300} tracks={[{ id: e.workout_id, points: e.lat.map((la, i) => [la, e.lon![i]]), color: p.series[1] }]} />
            ) : <div className="muted" style={{ padding: 40, textAlign: 'center' }}>Indoor session: HR stream only.</div>}
          </Card>
        </div>
      )}

      <SectionTitle title="Spoofed profiles" sub="user-level checks: physiological limits, two consistency regressions, and cloned workout fingerprints" />
      <div className="grid g3">
        <ChartCard title="Users: LOF × Isolation Forest score" sub="red = flagged by the rule / consistency / clone checks" height={300}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['not flagged', 'flagged'] },
            grid: { left: 44, right: 14, top: 34, bottom: 36 },
            xAxis: { type: 'log', ...axisStyle(p), name: 'LOF', nameLocation: 'middle', nameGap: 22 },
            yAxis: { type: 'value', min: 0.3, ...axisStyle(p), name: 'iForest' },
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const v = (x as { value: number[] }).value;
              return `user ${v[2]}<br/>LOF ${v[0].toFixed(2)} · iForest ${v[1].toFixed(3)}`;
            } },
            series: [false, true].map((f) => ({
              name: f ? 'flagged' : 'not flagged', type: 'scatter', symbol: f ? 'diamond' : 'circle', symbolSize: f ? 11 : 6,
              data: r.users.scatter.filter((u) => u.flagged === f).map((u) => [u.lof, u.iforest, u.user_id]),
              itemStyle: { color: f ? p.critical : p.muted, borderColor: p.surface, borderWidth: 1, opacity: f ? 1 : 0.6 },
            })),
          }} />
        <Card className="span2" title={`${r.users.flagged.length} flagged accounts`} sub="every flag carries a human-readable reason">
          <DataTable rows={r.users.flagged.map((u) => ({ ...u, reasons: u.reasons.join(' · ') }))} height={300} cols={[
            { key: 'user_id', label: 'User', num: true }, { key: 'reasons', label: 'Why', wrap: true },
            { key: 'lof', label: 'LOF', num: true, digits: 2 }, { key: 'iforest', label: 'iForest', num: true, digits: 3 }]} />
        </Card>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Profile detectors compared" sub="against the 22 planted spoofed accounts">
          <DataTable rows={Object.entries(r.users.evaluation).map(([k, v]) => ({ detector: k, flagged: v.flagged, tp: v.tp,
            precision: v.precision, recall: v.recall }))} cols={[
            { key: 'detector', label: 'Detector' }, { key: 'flagged', label: 'Flagged', num: true }, { key: 'tp', label: 'True', num: true },
            { key: 'precision', label: 'Precision', num: true, pct: true }, { key: 'recall', label: 'Recall', num: true, pct: true }]} />
        </Card>
        <Recovery items={[
          { label: 'Workout faults: ensemble', value: `P ${fmt.pct(r.methods.ensemble.precision)} · R ${fmt.pct(r.methods.ensemble.recall)}`,
            ok: r.methods.ensemble.f1 > 0.8 },
          ...Object.entries(ue.per_type).map(([k, v]) => ({ label: `Spoof: ${k.replace('_', ' ')}`, value: `${v.detected} / ${v.n}`,
            ok: v.detected === v.n })),
          { label: 'False alarms among genuine users', value: String(ue.flagged - ue.tp), ok: ue.flagged - ue.tp === 0 },
        ]} />
      </div>
    </>
  );
}
