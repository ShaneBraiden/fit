import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, reasonText, splitWords, useGet, when, WorkoutDetail } from '../../api/client';
import { phaseColor, TrackMap } from '../../components/fitness';
import { Card, Chart, ErrorBox, Loading, PageHead, Pill, Tile } from '../../components/ui';
import { axisStyle, base, fmt, usePalette } from '../../theme/chart';

export default function Workout() {
  const p = usePalette();
  const { id } = useParams();
  const nav = useNavigate();
  const d = useGet<WorkoutDetail>(`/api/me/workouts/${id}`);
  const [busy, setBusy] = useState(false);
  if (d.error) return <ErrorBox error={d.error} />;
  if (!d.data) return <Loading />;
  const w = d.data.workout;
  const remove = async () => {
    if (!window.confirm('Delete this workout? This cannot be undone.')) return;
    setBusy(true);
    try { await api(`/api/me/workouts/${id}`, undefined, 'DELETE'); nav('/'); } finally { setBusy(false); }
  };
  const speed = d.data.speed_kmh, segs = d.data.segments;

  return (
    <>
      <PageHead title={w.title} actions={<button className="btn" onClick={remove} disabled={busy}>Delete workout</button>}>
        {splitWords(w.session_type)} · {when.date(w.start_time)} {when.time(w.start_time)} · {w.source === 'gps' ? 'tracked with GPS' : 'logged manually'}
      </PageHead>
      <div className="grid g4">
        <Tile label="Duration" value={`${Math.round(w.duration_min)} min`} />
        <Tile label="Distance" value={w.distance_km ? `${w.distance_km.toFixed(2)} km` : '–'} />
        <Tile label="Avg heart rate" value={w.avg_hr ? `${fmt.n(w.avg_hr)} bpm` : '–'} />
        <Tile label="Calories" value={fmt.n(w.calories)} />
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title={<>Data check <Pill kind={w.flagged ? 'bad' : 'good'}>{w.flagged ? 'Not counted' : 'Counted'}</Pill></>}>
          <div className="note">{w.flagged ? `${reasonText(w.reasons)}. This workout doesn't count towards your stats.` : 'Nothing unusual in this workout.'}</div>
        </Card>
        {d.data.exercises.length > 0 && (
          <Card title="Exercises"><div className="chips">{d.data.exercises.map((e) => <span key={e} className="chip">{e}</span>)}</div></Card>
        )}
      </div>
      {d.data.lat && d.data.lon && (
        <div className="grid g2" style={{ marginTop: 16 }}>
          <Card title="Route" sub={d.data.route ? `On ${String(d.data.route.name)}` : undefined}>
            <TrackMap lat={d.data.lat} lon={d.data.lon} segments={segs} />
          </Card>
          {speed && segs && (
            <Card title="Speed and phases" sub="km/h every 15 seconds, coloured by phase">
              <Chart height={320} option={{
                ...base(p), grid: { left: 40, right: 10, top: 16, bottom: 30 },
                xAxis: { type: 'value', ...axisStyle(p), name: 'min', min: 0, max: (speed.length * d.data.dt) / 60 },
                yAxis: { type: 'value', ...axisStyle(p), name: 'km/h' },
                tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => `${(v as number).toFixed(1)} km/h` },
                series: segs.map((s) => ({ type: 'line' as const, showSymbol: false, name: s.phase,
                  data: speed.slice(s.start, s.end + 1).map((v, i) => [((s.start + i) * d.data!.dt) / 60, v]),
                  lineStyle: { width: 2, color: phaseColor(p, s.phase) }, itemStyle: { color: phaseColor(p, s.phase) } })),
              }} />
            </Card>
          )}
        </div>
      )}
    </>
  );
}
