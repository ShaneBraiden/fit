import { Link } from 'react-router-dom';
import { Alert, pace, Profile, reasonText, useGet, WorkoutItem } from '../../api/client';
import { useAuth } from '../../auth';
import { LevelBars, levelColor, WeeklyChart, WorkoutRow } from '../../components/fitness';
import { Card, ErrorBox, Loading, PageHead, Pill, Tile } from '../../components/ui';
import { fmt, usePalette } from '../../theme/chart';

export default function Today() {
  const p = usePalette();
  const { account } = useAuth();
  const prof = useGet<Profile>('/api/me/profile');
  const ws = useGet<WorkoutItem[]>('/api/me/workouts?limit=8');
  const alerts = useGet<Alert[]>('/api/me/alerts');
  if (prof.error) return <ErrorBox error={prof.error} />;
  if (!prof.data) return <Loading />;
  const d = prof.data;
  const vo2 = d.user.vo2max_estimate as number | null;

  return (
    <>
      <PageHead title={`Hi, ${account?.name.split(' ')[0] ?? ''}`}>Your last 8 weeks of training.</PageHead>
      {d.workouts_counted === 0 && (
        <Card title="Log your first workout" sub="Your level below is a first guess from your profile. It gets personal once you log a few workouts.">
          <Link className="btn primary" to="/log" style={{ display: 'inline-block', textDecoration: 'none' }}>Log a workout</Link>
        </Card>
      )}
      <div className="grid g4" style={{ marginTop: 16 }}>
        <Tile label="Sessions / week" value={fmt.n(d.stats.sessions_per_week, 1)} />
        <Tile label="Minutes / week" value={fmt.n(d.stats.minutes_per_week)} />
        <Tile label="Typical run pace" value={pace(d.stats.run_pace)} />
        <Tile label="VO2max" value={fmt.n(vo2, 1)} sub={d.user.vo2max_source ? `from ${d.user.vo2max_source}` : 'add runs or your resting HR'} />
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Fitness level" sub={`How sure we are of each level, from your ${d.workouts_counted} recent workouts and your profile`}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
            <span className="level-swatch" style={{ background: levelColor(p, d.level.value) }} />
            <span style={{ fontSize: 26, fontWeight: 600 }}>{d.level.value}</span>
          </div>
          <LevelBars probs={d.level.probabilities} highlight={d.level.predicted} />
        </Card>
        <Card title="Training style" sub="The common style your mix of workouts is closest to">
          <div style={{ fontSize: 22, fontWeight: 600, marginBottom: 10 }}>{d.persona.name}</div>
          <Link to="/insights">See how close you are to each style ›</Link>
        </Card>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Weekly minutes">
          {d.weekly.length ? <WeeklyChart weeks={d.weekly} /> : <div className="note">No workouts yet.</div>}
        </Card>
        <Card title="Recent workouts" actions={<Link to="/log">Log one</Link>}>
          {ws.data && ws.data.length === 0 && <div className="note">Nothing logged yet.</div>}
          {ws.data?.map((w) => <WorkoutRow key={w.workout_id} w={w} />)}
        </Card>
      </div>
      {alerts.data && alerts.data.length > 0 && (
        <div style={{ marginTop: 16 }}>
        <Card title={<>Workouts that need a look <Pill kind="bad">{alerts.data.length}</Pill></>} sub="These don't count towards your stats.">
          {alerts.data.slice(0, 5).map((a) => (
            <div key={a.workout_id} className="note" style={{ marginTop: 4 }}>
              <Link to={`/workout/${a.workout_id}`}>{a.title}</Link>: {reasonText(a.detail)}
            </div>
          ))}
        </Card>
        </div>
      )}
    </>
  );
}
