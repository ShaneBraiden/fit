import { router } from 'expo-router';
import { useCallback } from 'react';
import { View } from 'react-native';
import { ProbBars, WeeklyBars } from '../../components/charts';
import WorkoutRow from '../../components/WorkoutRow';
import { Button, Card, EmptyState, ErrorState, H2, P, Pill, Row, Screen, Skeleton, Stat } from '../../components/ui';
import { Alert, fmt, Profile, useFetch, WorkoutItem } from '../../lib/api';
import { useFocusRefresh } from '../../lib/focus';
import { useSession } from '../../lib/session';
import { levelColor, space, useTheme } from '../../lib/theme';

export default function Today() {
  const t = useTheme();
  const { account } = useSession();
  const prof = useFetch<Profile>('/api/me/profile');
  const ws = useFetch<WorkoutItem[]>('/api/me/workouts?limit=5');
  const alerts = useFetch<Alert[]>('/api/me/alerts');
  // Back on this tab (e.g. after saving a workout): show fresh numbers.
  useFocusRefresh(useCallback(() => { prof.reload(); ws.reload(); alerts.reload(); }, [prof.reload, ws.reload, alerts.reload]));
  const refresh = () => { prof.reload(); ws.reload(); alerts.reload(); };
  const p = prof.data;
  const first = account ? account.name.split(' ')[0] : null;
  const fresh = p != null && p.workouts_counted === 0;

  return (
    <Screen title={first ? `Hi, ${first}` : 'Today'} subtitle="Your last 8 weeks of training" refreshing={prof.loading} onRefresh={refresh}>
      {prof.error ? <ErrorState message={prof.error} onRetry={refresh} /> : !p ? <><Skeleton /><Skeleton lines={5} /></> : (
        <>
          {fresh && (
            <Card style={{ borderLeftWidth: 3, borderLeftColor: t.accent }}>
              <H2>Record your first workout</H2>
              <P muted small>Your level below is a first guess from your profile. It gets personal once you record a few workouts.</P>
              <View style={{ marginTop: space.md }}>
                <Button label="Record a workout" icon="add-circle-outline" onPress={() => router.push('/(tabs)/log')} />
              </View>
            </Card>
          )}
          <Card>
            <Row gap={space.md}>
              <View style={{ width: 12, height: 40, borderRadius: 4, backgroundColor: levelColor(t, p.level.value) }} />
              <View style={{ flex: 1 }}>
                <P muted small>Fitness level</P>
                <P style={{ fontSize: 24, fontWeight: '700' }}>{p.level.value}</P>
              </View>
            </Row>
            <View style={{ marginTop: space.md }}>
              <ProbBars probs={p.level.probabilities} highlight={p.level.predicted} />
            </View>
            <P muted small style={{ marginTop: space.sm }}>
              How sure we are of each level, from your {p.workouts_counted} recent workout{p.workouts_counted === 1 ? '' : 's'}, body measurements
              {p.user.vo2max_source ? ` and VO2max (${fmt.n(p.user.vo2max_estimate as number, 1)}, from ${p.user.vo2max_source})` : ''}.
            </P>
          </Card>

          <Card>
            <P muted small>Your training style</P>
            <P style={{ fontSize: 20, fontWeight: '700', marginTop: 2 }}>{p.persona.name}</P>
            <Row wrap gap={space.lg} style={{ marginTop: space.md }}>
              <Stat label="Sessions / week" value={fmt.n(p.stats.sessions_per_week, 1)} />
              <Stat label="Minutes / week" value={fmt.n(p.stats.minutes_per_week)} />
              {p.stats.avg_intensity != null ? <Stat label="Avg intensity" value={fmt.pct(p.stats.avg_intensity)} sub="of heart-rate reserve" /> : null}
              {p.stats.run_pace ? <Stat label="Typical run pace" value={fmt.pace(p.stats.run_pace)} /> : null}
            </Row>
          </Card>

          <Card>
            <H2>Weekly minutes</H2>
            {p.weekly.length ? <WeeklyBars weeks={p.weekly} /> : <P muted>No workouts yet.</P>}
          </Card>

          {alerts.data && alerts.data.length > 0 && (
            <Card onPress={() => router.push('/(tabs)/profile')}>
              <H2 right={<Pill kind="bad" label={`${alerts.data.length}`} />}>Workouts that need a look</H2>
              {alerts.data.slice(0, 3).map((a) => (
                <P key={a.workout_id} small muted style={{ marginTop: 4 }}>• {a.title}: {fmt.reason(a.detail)}</P>
              ))}
              <P small muted style={{ marginTop: 6 }}>These don't count towards your stats.</P>
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
