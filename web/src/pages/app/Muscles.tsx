import { useState } from 'react';
import { Link } from 'react-router-dom';
import { MuscleProgress, MuscleReport, todayIso, useGet, when } from '../../api/client';
import { BodyMap, SetsScale, setsColor } from '../../components/body';
import { Card, Chart, ErrorBox, Loading, PageHead, Pill, Tile } from '../../components/ui';
import { axisStyle, barItem, base, fmt, usePalette } from '../../theme/chart';

const STATUS: Record<MuscleProgress['status'], { kind: 'good' | 'bad' | 'warn' | 'neutral'; label: string }> = {
  ready: { kind: 'good', label: 'Ready' },
  recovering: { kind: 'warn', label: 'Recovering' },
  overdue: { kind: 'bad', label: 'Overdue' },
  not_trained: { kind: 'neutral', label: 'Not trained' },
};
const VOLUME: Record<MuscleProgress['volume_status'], string> = { low: 'below target', on_target: 'on target', high: 'above target' };
const shortWeek = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });

export default function Muscles() {
  const p = usePalette();
  const r = useGet<MuscleReport>(`/api/me/muscles?today=${todayIso()}`);
  const [view, setView] = useState<'week' | 'avg'>('week');
  const [sel, setSel] = useState<string>('Chest');
  if (r.error) return <ErrorBox error={r.error} />;
  if (!r.data) return <Loading />;
  const d = r.data;
  const [lo, hi] = d.sets_target;
  const sets = Object.fromEntries(d.muscles.map((m) => [m.muscle, view === 'week' ? m.sets_this_week : m.sets_avg]));
  const m = d.muscles.find((x) => x.muscle === sel) ?? d.muscles[0];
  const empty = d.muscles.every((x) => x.sets_avg === 0);

  return (
    <>
      <PageHead title="Muscles">Hard sets per muscle each week, from the exercises you log. {lo}–{hi} sets a week is a common target for growth.</PageHead>
      {empty && (
        <Card title="No sets yet" sub="Log a strength or HIIT workout with its exercises. Add sets, reps and weight to track strength too.">
          <Link className="btn primary" to="/log" style={{ display: 'inline-block', textDecoration: 'none' }}>Log a workout</Link>
        </Card>
      )}
      <div className="grid g2" style={{ marginTop: empty ? 16 : 0 }}>
        <Card title="Your body this week" sub="Tap a muscle to see its progress" actions={
          <div className="seg">
            <button className={view === 'week' ? 'on' : ''} onClick={() => setView('week')}>This week</button>
            <button className={view === 'avg' ? 'on' : ''} onClick={() => setView('avg')}>8-week average</button>
          </div>}>
          <BodyMap p={p} sets={sets} selected={sel} onSelect={setSel} top={hi} />
          <SetsScale p={p} top={hi} />
          <div className="note" style={{ marginTop: 6 }}>{fmt.n(d.total_sets_this_week, 0)} sets in total this week. Secondary muscles count half a set.</div>
        </Card>
        <MuscleDetail m={m} weeks={d.weeks} />
      </div>
      <div style={{ marginTop: 16 }}>
        <Card title="Every muscle" sub="Sets this week against the target band">
          <div className="muscle-list">
            {d.muscles.map((x) => (
              <button key={x.muscle} className={`muscle-row ${x.muscle === sel ? 'on' : ''}`} onClick={() => setSel(x.muscle)}>
                <span className="name"><strong>{x.muscle}</strong><span className="muted"> · {x.group}</span></span>
                <span className="target-bar" aria-label={`${x.sets_this_week} sets`}>
                  <span className="band" style={{ left: `${(lo / (hi * 1.5)) * 100}%`, width: `${((hi - lo) / (hi * 1.5)) * 100}%` }} />
                  <i style={{ width: `${Math.min(100, (x.sets_this_week / (hi * 1.5)) * 100)}%`, background: setsColor(p, x.sets_this_week, hi) }} />
                </span>
                <span className="num">{fmt.n(x.sets_this_week, 1)}</span>
                <Pill kind={STATUS[x.status].kind}>{STATUS[x.status].label}</Pill>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}

function MuscleDetail({ m, weeks }: { m: MuscleProgress; weeks: string[] }) {
  const p = usePalette();
  const lifts = m.exercises.filter((e) => e.history.length > 0);
  return (
    <Card title={<>{m.muscle} <Pill kind={STATUS[m.status].kind}>{STATUS[m.status].label}</Pill></>}
      sub={m.last_trained ? `Last trained ${m.days_since === 0 ? 'today' : m.days_since === 1 ? 'yesterday' : `${m.days_since} days ago`} (${when.date(m.last_trained)})`
        : 'Not trained in the last 4 months'}>
      <div className="grid g3" style={{ gap: 10 }}>
        <Tile label="This week" value={`${fmt.n(m.sets_this_week, 1)} sets`} sub={VOLUME[m.volume_status]} />
        <Tile label="Weekly average" value={fmt.n(m.sets_avg, 1)} sub="last 8 weeks" />
        <Tile label="Trend" value={m.trend_pct == null ? '–' : `${m.trend_pct >= 0 ? '+' : ''}${fmt.pct(m.trend_pct, 0)}`} sub="last 4 weeks vs 4 before" />
      </div>
      <Chart height={190} option={{
        ...base(p), grid: { left: 36, right: 10, top: 16, bottom: 26 },
        xAxis: { type: 'category', data: weeks.map(shortWeek), ...axisStyle(p) },
        yAxis: { type: 'value', name: 'sets', min: 0, max: Math.ceil(Math.max(m.target_high + 4, ...m.weekly.map((w) => w.sets)) / 5) * 5, ...axisStyle(p) },
        tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => `${v} sets` },
        series: [{ type: 'bar', name: 'Sets', barMaxWidth: 26, data: m.weekly.map((w) => w.sets), itemStyle: barItem(p.series[0]),
          markArea: { silent: true, itemStyle: { color: p.good, opacity: 0.08 }, data: [[{ yAxis: m.target_low }, { yAxis: m.target_high }]] } }],
      }} />
      <div className="note">Shaded: the {m.target_low}–{m.target_high} sets target.</div>
      <h4 style={{ margin: '14px 0 6px' }}>Strength by exercise</h4>
      {m.exercises.length === 0 && <div className="note">No exercises for this muscle in the last 8 weeks.</div>}
      {m.exercises.map((e) => (
        <div key={e.exercise} className="lift-row">
          <span className="grow"><strong>{e.exercise}</strong><div className="muted" style={{ fontSize: 12 }}>{e.sessions} session{e.sessions === 1 ? '' : 's'}</div></span>
          {e.best_e1rm != null ? <span className="num" style={{ textAlign: 'right' }}>
            <strong>{fmt.n(e.latest_e1rm, 1)} kg</strong>
            <div className="muted" style={{ fontSize: 12 }}>est. 1-rep max{e.change_pct != null && e.history.length > 1 ? ` · ${e.change_pct >= 0 ? '+' : ''}${fmt.pct(e.change_pct, 0)}` : ''}</div>
          </span> : <span className="muted" style={{ fontSize: 12 }}>log weight & reps to track</span>}
        </div>
      ))}
      {lifts.length > 0 && <Chart height={200} option={{
        ...base(p), legend: { ...base(p).legend, data: lifts.map((e) => e.exercise) }, grid: { left: 40, right: 12, top: 34, bottom: 26 },
        xAxis: { type: 'time', ...axisStyle(p) }, yAxis: { type: 'value', name: 'kg', scale: true, ...axisStyle(p) },
        tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => `${fmt.n(v as number, 1)} kg` },
        series: lifts.map((e, i) => ({ type: 'line' as const, name: e.exercise, showSymbol: true, symbolSize: 6,
          data: e.history.map((h) => [h.date, h.e1rm]), lineStyle: { color: p.series[i % 8], width: 2 }, itemStyle: { color: p.series[i % 8] } })),
      }} />}
    </Card>
  );
}
