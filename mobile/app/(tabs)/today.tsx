import { router } from 'expo-router';
import { View } from 'react-native';
import { ProbBars, WeeklyBars } from '../../components/charts';
import WorkoutRow from '../../components/WorkoutRow';
import { Card, EmptyState, ErrorState, H2, P, Pill, Row, Screen, Skeleton, Stat } from '../../components/ui';
import { Alert, fmt, Profile, useFetch, WorkoutItem } from '../../lib/api';
import { useSession } from '../../lib/session';
import { levelColor, space, useTheme } from '../../lib/theme';

export default function Today() {
  const t = useTheme();
  const { userId } = useSession();
  const prof = useFetch<Profile>(userId ? `/api/users/${userId}/profile` : null);
  const ws = useFetch<WorkoutItem[]>(userId ? `/api/users/${userId}/workouts?limit=5` : null);
  const alerts = useFetch<Alert[]>(userId ? `/api/users/${userId}/alerts` : null);
  const refresh = () => { prof.reload(); ws.reload(); alerts.reload(); };
  const p = prof.data;

  return (
    <Screen title={p ? `Hi, ${String(p.user.name).split(' ')[0]}` : 'Today'} subtitle="What your training data says about you"
      refreshing={prof.loading} onRefresh={refresh}>
      {prof.error ? <ErrorState message={prof.error} onRetry={refresh} /> : !p ? <><Skeleton /><Skeleton lines={5} /></> : (
        <>
          <Card>
            <Row gap={space.md}>
              <View style={{ width: 12, height: 40, borderRadius: 4, backgroundColor: levelColor(t, p.level.value) }} />
              <View style={{ flex: 1 }}>
                <P muted small>Fitness level · {p.level.source === 'assessed' ? 'from your assessment' : 'predicted by the classifier'}</P>
                <P style={{ fontSize: 24, fontWeight: '700' }}>{p.level.value}</P>
              </View>
            </Row>
            <View style={{ marginTop: space.md }}>
              <ProbBars probs={p.level.probabilities} highlight={p.level.predicted} />
            </View>
            <P muted small style={{ marginTop: space.sm }}>
              Decision-tree probabilities from your VO2max, resting HR and training load
              {p.level.source === 'assessed' && p.level.predicted !== p.level.value ? ` · the model would say ${p.level.predicted}` : ''}.
            </P>
          </Card>

          <Card>
            <P muted small>Your training persona (k-means cluster)</P>
            <P style={{ fontSize: 20, fontWeight: '700', marginTop: 2 }}>{p.persona.name}</P>
            <Row wrap gap={space.lg} style={{ marginTop: space.md }}>
              <Stat label="Sessions / week" value={fmt.n(p.stats.sessions_per_week, 1)} />
              <Stat label="Minutes / week" value={fmt.n(p.stats.minutes_per_week)} />
              <Stat label="Avg intensity" value={fmt.pct(p.stats.avg_intensity)} sub="of heart-rate reserve" />
              {p.stats.run_pace ? <Stat label="Typical run pace" value={fmt.pace(p.stats.run_pace)} /> : null}
            </Row>
          </Card>

          <Card>
            <H2>Weekly minutes</H2>
            {p.weekly.length ? <WeeklyBars weeks={p.weekly} /> : <P muted>No workouts yet.</P>}
            <P muted small style={{ marginTop: space.sm }}>Your slice of the workout cube, rolled up from days to ISO weeks.</P>
          </Card>

          {alerts.data && alerts.data.length > 0 && (
            <Card onPress={() => router.push('/(tabs)/profile')}>
              <H2 right={<Pill kind="bad" label={`${alerts.data.length}`} />}>Data checks</H2>
              {alerts.data.slice(0, 3).map((a, i) => (
                <P key={i} small muted style={{ marginTop: i ? 6 : 0 }}>• {a.title}: {fmt.reason(a.detail)}</P>
              ))}
            </Card>
          )}
        </>
      )}

      <Card>
        <H2>Recent workouts</H2>
        {ws.error ? <P muted small>{ws.error}</P> : !ws.data ? <P muted>Loading…</P> : ws.data.length === 0
          ? <EmptyState icon="barbell-outline" title="No workouts yet" body="Record one from the Record tab." />
          : ws.data.map((w) => <WorkoutRow key={w.workout_id} w={w} />)}
      </Card>
    </Screen>
  );
}
