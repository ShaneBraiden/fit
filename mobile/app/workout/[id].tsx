import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert as RNAlert, Platform, View } from 'react-native';
import { HrChart, RouteMap, SpeedChart } from '../../components/charts';
import { Button, Card, Chip, ErrorState, H2, P, Pill, Row, Screen, Skeleton, Stat } from '../../components/ui';
import { fmt, useApi, useFetch, WorkoutDetail } from '../../lib/api';
import { space } from '../../lib/theme';

const split = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2');

export default function Workout() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const api = useApi();
  const d = useFetch<WorkoutDetail>(id ? `/api/me/workouts/${id}` : null);
  const [busy, setBusy] = useState(false);
  const w = d.data?.workout;

  const remove = async () => {
    setBusy(true);
    try {
      await api(`/api/me/workouts/${id}`, undefined, 'DELETE');
      router.back();
    } finally {
      setBusy(false);
    }
  };
  const confirmRemove = () => {
    if (Platform.OS === 'web') { if (window.confirm('Delete this workout? This cannot be undone.')) remove(); return; }
    RNAlert.alert('Delete this workout?', 'This cannot be undone.', [
      { text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: remove }]);
  };

  return (
    <Screen refreshing={d.loading} onRefresh={d.reload}>
      {d.error ? <ErrorState message={d.error} onRetry={d.reload} /> : !d.data || !w ? <><Skeleton /><Skeleton lines={5} /></> : (
        <>
          <View>
            <P style={{ fontSize: 22, fontWeight: '700' }}>{w.title}</P>
            <P muted small>{split(w.session_type)} · {fmt.date(w.start_time)} {fmt.time(w.start_time)} · {w.source === 'gps' ? 'tracked with GPS' : 'logged manually'}</P>
          </View>
          <Card>
            <Row wrap gap={space.lg}>
              <Stat label="Duration" value={`${Math.round(w.duration_min)} min`} />
              {w.distance_km ? <Stat label="Distance" value={`${w.distance_km.toFixed(2)} km`} /> : null}
              {w.avg_hr ? <Stat label="Avg / max HR" value={`${fmt.n(w.avg_hr)} / ${fmt.n(w.max_hr)}`} sub="bpm" /> : null}
              <Stat label="Calories" value={fmt.n(w.calories)} />
            </Row>
          </Card>
          <Card>
            <Row style={{ justifyContent: 'space-between' }}>
              <H2>Data check</H2>
              <Pill kind={w.flagged ? 'bad' : 'good'} label={w.flagged ? 'Not counted' : 'Counted'} />
            </Row>
            <P muted small>{w.flagged ? `${fmt.reason(w.reasons)}. This workout doesn't count towards your stats.` : 'Nothing unusual in this workout.'}</P>
          </Card>
          {d.data.hr.length > 0 && (
            <Card>
              <H2>Heart rate</H2>
              <HrChart hr={d.data.hr} dt={d.data.dt} />
            </Card>
          )}
          {d.data.lat && d.data.lon && (
            <Card>
              <H2>Route{d.data.segments ? ' & phases' : ''}</H2>
              {d.data.route && <P muted small style={{ marginBottom: space.sm }}>On {String(d.data.route.name)}</P>}
              <RouteMap lat={d.data.lat} lon={d.data.lon} segments={d.data.segments} height={220} />
              {d.data.speed_kmh && d.data.segments && <View style={{ marginTop: space.md }}>
                <SpeedChart speed={d.data.speed_kmh} segments={d.data.segments} />
              </View>}
            </Card>
          )}
          {d.data.exercises.length > 0 && (
            <Card>
              <H2>Exercises</H2>
              <Row wrap gap={space.sm}>{d.data.exercises.map((e) => {
                const l = d.data!.loads.find((x) => x.exercise === e);
                const detail = l ? [l.sets && `${l.sets}×${l.reps ?? '?'}`, l.weight_kg != null && `${fmt.n(l.weight_kg, 1)} kg`].filter(Boolean).join(' @ ') : '';
                return <Chip key={e} label={detail ? `${e} · ${detail}` : e} />;
              })}</Row>
            </Card>
          )}
          <Button label="Delete workout" kind="secondary" icon="trash-outline" onPress={confirmRemove} busy={busy} />
        </>
      )}
    </Screen>
  );
}
