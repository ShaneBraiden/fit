import { useGet, UserRoutes } from '../../api/client';
import { WorkoutRow } from '../../components/fitness';
import MapView from '../../components/MapView';
import { Card, ErrorBox, Legend, Loading, PageHead } from '../../components/ui';
import { usePalette } from '../../theme/chart';

export default function RoutesPage() {
  const p = usePalette();
  const r = useGet<UserRoutes>('/api/me/routes');
  if (r.error) return <ErrorBox error={r.error} />;
  if (!r.data) return <Loading />;
  const used: Record<string, number> = {};
  for (const w of r.data.workouts) if (w.route_name) used[w.route_name] = (used[w.route_name] ?? 0) + 1;
  const mine = r.data.popular.filter((x) => used[x.name]);
  return (
    <>
      <PageHead title="Routes">Your GPS workouts, and popular routes near you.</PageHead>
      {r.data.popular.length > 0 && (
        <Card title="Popular routes near you" sub="Routes many people run or ride; yours are coloured">
          <MapView height={380} tracks={r.data.popular.map((x) => ({ id: x.cluster, points: x.track as [number, number][],
            color: used[x.name] ? p.series[mine.indexOf(x) % 8] : p.muted, weight: used[x.name] ? 4 : 3, label: x.name }))} />
          {mine.length > 0 && <Legend items={mine.map((x, i) => ({ label: `${x.name} · you ×${used[x.name]}`, color: p.series[i % 8], line: true }))} />}
        </Card>
      )}
      <div style={{ marginTop: 16 }}>
        <Card title="Your GPS workouts">
          {r.data.workouts.length === 0 ? <div className="note">No GPS workouts yet. Track a run, walk or ride from the phone app or the Log page.</div>
            : r.data.workouts.slice(0, 50).map((w) => <WorkoutRow key={w.workout_id} w={w} />)}
        </Card>
      </div>
    </>
  );
}
