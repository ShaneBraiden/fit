import { useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { HrChart, RouteMap, SpeedChart } from '../../components/charts';
import { Card, Chip, Divider, ErrorState, H2, P, Pill, Row, Screen, Skeleton, Stat } from '../../components/ui';
import { fmt, useFetch, WorkoutDetail } from '../../lib/api';
import { useSession } from '../../lib/session';
import { space } from '../../lib/theme';

export default function Workout() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { userId } = useSession();
  const d = useFetch<WorkoutDetail>(userId && id ? `/api/users/${userId}/workouts/${id}` : null);
  const w = d.data?.workout;

  return (
    <Screen refreshing={d.loading} onRefresh={d.reload}>
      {d.error ? <ErrorState message={d.error} onRetry={d.reload} /> : !d.data || !w ? <><Skeleton /><Skeleton lines={5} /></> : (
        <>
          <View>
            <P style={{ fontSize: 22, fontWeight: '700' }}>{w.title}</P>
            <P muted small>{w.activity} · {fmt.date(w.start_time)} {fmt.time(w.start_time)}{w.source === 'app' ? ' · recorded in the app' : ''}</P>
          </View>
          <Card>
            <Row wrap gap={space.lg}>
              <Stat label="Duration" value={`${Math.round(w.duration_min)} min`} />
              {w.distance_km ? <Stat label="Distance" value={`${w.distance_km.toFixed(2)} km`} /> : null}
              <Stat label="Avg / max HR" value={`${fmt.n(w.avg_hr)} / ${fmt.n(w.max_hr)}`} sub="bpm" />
              <Stat label="Calories" value={fmt.n(w.calories)} />
            </Row>
          </Card>
          <Card>
            <Row style={{ justifyContent: 'space-between' }}>
              <H2>Sensor check</H2>
              <Pill kind={w.flagged ? 'bad' : 'good'} label={w.flagged ? 'Flagged' : 'Clean'} />
            </Row>
            <P muted small>{w.flagged ? fmt.reason(w.reasons) : 'No detector found anything unusual in this recording.'}</P>
          </Card>
          {d.data.hr.length > 0 && (
            <Card>
              <H2>Heart rate</H2>
              <HrChart hr={d.data.hr} dt={d.data.dt} />
            </Card>
          )}
          {d.data.lat && d.data.lon && (
            <Card>
              <H2>Route & phases</H2>
              <P muted small style={{ marginBottom: space.sm }}>
                {d.data.run_kind ? `Detected session type: ${d.data.run_kind}` : ''}
                {d.data.route ? ` · matched route ${String(d.data.route.name)}` : ' · no popular route matched'}
              </P>
              <RouteMap lat={d.data.lat} lon={d.data.lon} segments={d.data.segments} height={220} />
              {d.data.speed_kmh && d.data.segments && <View style={{ marginTop: space.md }}>
                <SpeedChart speed={d.data.speed_kmh} segments={d.data.segments} />
              </View>}
            </Card>
          )}
          {d.data.exercises.length > 0 && (
            <Card>
              <H2>Exercises</H2>
              <Row wrap gap={space.sm}>{d.data.exercises.map((e) => <Chip key={e} label={e} />)}</Row>
              <Divider />
              <P muted small>These baskets are what the association-rule miner learns from.</P>
            </Card>
          )}
        </>
      )}
    </Screen>
  );
}
