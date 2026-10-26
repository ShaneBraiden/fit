import { useCallback, useMemo } from 'react';
import { Legend, RouteMap } from '../../components/charts';
import { Card, EmptyState, ErrorState, H2, P, Screen, Skeleton } from '../../components/ui';
import WorkoutRow from '../../components/WorkoutRow';
import { useFetch, UserRoutes } from '../../lib/api';
import { useFocusRefresh } from '../../lib/focus';
import { useTheme } from '../../lib/theme';

export default function Routes() {
  const t = useTheme();
  const r = useFetch<UserRoutes>('/api/me/routes');
  // Back on this tab (e.g. after saving a workout): show fresh numbers.
  useFocusRefresh(useCallback(() => { r.reload(); }, [r.reload]));
  const used = useMemo(() => {
    const c: Record<string, number> = {};
    for (const w of r.data?.workouts ?? []) if (w.route_name) c[w.route_name] = (c[w.route_name] ?? 0) + 1;
    return c;
  }, [r.data]);
  const popular = r.data?.popular ?? [];
  const mine = popular.filter((p) => used[p.name]);

  return (
    <Screen title="Routes" subtitle="Your GPS workouts, and popular routes near you" refreshing={r.loading} onRefresh={r.reload}>
      {r.error ? <ErrorState message={r.error} onRetry={r.reload} /> : !r.data ? <Skeleton lines={6} /> : (
        <>
          {popular.length > 0 && (
            <Card>
              <H2>Popular routes near you</H2>
              <RouteMap lat={[]} lon={[]} height={260}
                background={popular.map((p) => ({ track: p.track, color: used[p.name] ? t.series[mine.indexOf(p) % 8] : undefined }))} />
              {mine.length > 0
                ? <Legend items={mine.map((p, i) => ({ label: `${p.name} · you ×${used[p.name]}`, color: t.series[i % 8], line: true }))} />
                : <P muted small style={{ marginTop: 6 }}>Grey: routes many people run or ride that you haven't tried yet.</P>}
            </Card>
          )}
          <Card>
            <H2>Your GPS workouts</H2>
            {r.data.workouts.length === 0
              ? <EmptyState icon="map-outline" title="No GPS workouts yet" body="Track a run, walk or ride from the Record tab." />
              : r.data.workouts.slice(0, 40).map((w) => <WorkoutRow key={w.workout_id} w={w} />)}
          </Card>
        </>
      )}
    </Screen>
  );
}
