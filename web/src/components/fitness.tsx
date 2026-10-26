/* Pieces shared by the user pages: workout rows, level bars, weekly minutes, the route map with phases. */
import { Link } from 'react-router-dom';
import { pace, reasonText, when, WorkoutItem } from '../api/client';
import { axisStyle, barItem, base, fmt, Palette, usePalette } from '../theme/chart';
import MapView from './MapView';
import { Chart, Legend, Pill } from './ui';

export const LEVELS = ['Beginner', 'Intermediate', 'Advanced', 'Elite'];
export const levelColor = (p: Palette, level: string) => p.seq[[1, 3, 4, 6][LEVELS.indexOf(level)] ?? 3];
const ICON: Record<string, string> = { Run: '🏃', Walk: '🚶', Cycle: '🚴', Swim: '🏊', Strength: '🏋', HIIT: '⚡', Yoga: '🧘' };
export const activityIcon = (a: string) => ICON[a] ?? '•';

export function WorkoutRow({ w }: { w: WorkoutItem }) {
  return (
    <Link to={`/workout/${w.workout_id}`} className="workout-row">
      <span className="icon" aria-hidden>{activityIcon(w.activity)}</span>
      <span className="grow">
        <strong>{w.title}</strong>
        <div className="muted" style={{ fontSize: 12 }}>
          {when.date(w.start_time)} · {Math.round(w.duration_min)} min{w.distance_km ? ` · ${w.distance_km.toFixed(1)} km` : ''}
          {w.activity === 'Run' && w.distance_km ? ` · ${pace(w.duration_min / w.distance_km)}` : ''}{w.route_name ? ` · ${w.route_name}` : ''}
        </div>
      </span>
      {w.flagged ? <span title={reasonText(w.reasons)}><Pill kind="bad">Not counted</Pill></span> : <span className="muted">›</span>}
    </Link>
  );
}

export function LevelBars({ probs, highlight }: { probs: Record<string, number>; highlight: string }) {
  const p = usePalette();
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {LEVELS.filter((l) => l in probs).map((l) => (
        <div key={l} style={{ display: 'grid', gridTemplateColumns: '100px 1fr 44px', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <span style={{ fontWeight: l === highlight ? 600 : 400 }}>{l}</span>
          <div className="bar" style={{ marginTop: 0 }}><i style={{ width: `${Math.max(2, probs[l] * 100)}%`, background: levelColor(p, l) }} /></div>
          <span className="num muted" style={{ textAlign: 'right' }}>{fmt.pct(probs[l], 0)}</span>
        </div>
      ))}
    </div>
  );
}

const CATS = ['Cardio', 'Strength', 'Mind-Body'];

export function WeeklyChart({ weeks }: { weeks: { week: string; minutes: Record<string, number> }[] }) {
  const p = usePalette();
  return (
    <Chart height={220} option={{
      ...base(p), legend: { ...base(p).legend, data: CATS },
      grid: { left: 44, right: 10, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: weeks.map((w) => w.week.replace(/^\d{4}-/, '')), ...axisStyle(p) },
      yAxis: { type: 'value', name: 'min', ...axisStyle(p) },
      tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${Math.round(v as number)} min` },
      series: CATS.map((c, i) => ({ name: c, type: 'bar' as const, stack: 'm', barMaxWidth: 28,
        data: weeks.map((w) => w.minutes[c] ?? 0), itemStyle: i === CATS.length - 1 ? barItem(p.series[i]) : { color: p.series[i] } })),
    }} />
  );
}

const PHASES = ['warmup', 'steady', 'fast', 'recovery', 'cooldown', 'stop'];
export const phaseColor = (p: Palette, phase: string) => (phase === 'stop' ? p.muted : p.series[[0, 1, 2, 3, 6][PHASES.indexOf(phase)] ?? 0]);
const PHASE_NAME: Record<string, string> = { warmup: 'warm-up', steady: 'steady', fast: 'fast', recovery: 'recovery',
  cooldown: 'cool-down', stop: 'stopped' };

type Seg = { start: number; end: number; phase: string };

/** The GPS track on the map, coloured by phase when the run was split into phases. */
export function TrackMap({ lat, lon, segments, height = 320 }: { lat: number[]; lon: number[]; segments?: Seg[] | null; height?: number }) {
  const p = usePalette();
  const pts = lat.map((la, i) => [la, lon[i]] as [number, number]);
  const tracks = segments && segments.length
    ? segments.map((s, i) => ({ id: i, points: pts.slice(s.start, s.end + 1), color: phaseColor(p, s.phase), weight: 4,
      label: PHASE_NAME[s.phase] ?? s.phase }))
    : [{ id: 0, points: pts, color: p.series[0], weight: 4 }];
  const used = Array.from(new Set((segments ?? []).map((s) => s.phase)));
  return (
    <>
      <MapView tracks={tracks} height={height} dots={pts.length ? [{ lat: pts[0][0], lon: pts[0][1], color: p.good, r: 6, label: 'start' }] : []} />
      {used.length > 0 && <Legend items={used.map((ph) => ({ label: PHASE_NAME[ph] ?? ph, color: phaseColor(p, ph), line: true }))} />}
    </>
  );
}
