import { Ionicons } from '@expo/vector-icons';
import { useCallback } from 'react';
import { View } from 'react-native';
import { Meter } from '../../components/charts';
import { Card, Divider, ErrorState, H2, P, Row, Screen, Skeleton } from '../../components/ui';
import { fmt, Profile, Recommendation, useFetch } from '../../lib/api';
import { useFocusRefresh } from '../../lib/focus';
import { space, useTheme } from '../../lib/theme';

const split = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2');

export default function Insights() {
  const t = useTheme();
  const recs = useFetch<Recommendation[]>('/api/me/recommendations');
  const prof = useFetch<Profile>('/api/me/profile');
  // Back on this tab (e.g. after saving a workout): show fresh numbers.
  useFocusRefresh(useCallback(() => { recs.reload(); prof.reload(); }, [recs.reload, prof.reload]));
  const refresh = () => { recs.reload(); prof.reload(); };
  const p = prof.data;
  const dist = p ? Object.entries(p.persona.distances).sort((a, b) => a[1] - b[1]) : [];
  const maxD = dist.length ? Math.max(...dist.map((d) => d[1])) : 1;

  return (
    <Screen back title="Insights" subtitle="What your training says, and what to try next" refreshing={recs.loading} onRefresh={refresh}>
      <Card>
        <H2>Try next</H2>
        <P muted small style={{ marginBottom: space.sm }}>Exercises that people usually add to the ones in your recent workouts.</P>
        {recs.error ? <ErrorState message={recs.error} onRetry={recs.reload} /> : !recs.data ? <Skeleton lines={3} />
          : recs.data.length === 0 ? <P muted>Log a workout with its exercises to get suggestions.</P>
            : recs.data.map((r, i) => (
              <View key={r.exercise}>
                {i > 0 && <Divider />}
                <Row gap={space.md}>
                  <Ionicons name="add-circle-outline" size={22} color={t.accent} />
                  <View style={{ flex: 1 }}>
                    <P style={{ fontWeight: '600' }}>{r.exercise}</P>
                    <P muted small>{fmt.pct(r.confidence)} of people who do {r.because.join(' + ')} also do it</P>
                    <Meter value={r.confidence} />
                  </View>
                </Row>
              </View>
            ))}
      </Card>

      <Card>
        <H2>Your weekly routine</H2>
        <P muted small style={{ marginBottom: space.sm }}>Orders of workouts you repeat in at least half of your weeks.</P>
        {!p ? <Skeleton lines={2} /> : p.routines.length === 0 ? <P muted>No regular pattern yet. Keep training for a couple of weeks.</P> : p.routines.map((r) => (
          <View key={r.text} style={{ marginBottom: space.sm }}>
            <Row wrap gap={6}>
              {r.pattern.map((el, i) => (
                <Row key={i} gap={6}>
                  {i > 0 && <Ionicons name="arrow-forward" size={14} color={t.muted} />}
                  <View style={{ backgroundColor: t.accentWash, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 }}>
                    <P small style={{ color: t.accentInk, fontWeight: '600' }}>{el.map(split).join(' + ')}</P>
                  </View>
                </Row>
              ))}
            </Row>
            <P muted small style={{ marginTop: 4 }}>in {fmt.pct(r.weeks)} of your weeks</P>
          </View>
        ))}
      </Card>

      <Card>
        <H2>Your training style</H2>
        <P muted small style={{ marginBottom: space.sm }}>How close your mix of workouts is to each common style (shorter bar = closer).</P>
        {!p ? <Skeleton lines={4} /> : dist.map(([name, d]) => (
          <View key={name} style={{ marginBottom: 8 }}>
            <P small style={{ fontWeight: name === p.persona.name ? '700' : '400' }}>{name}{name === p.persona.name ? ' · you' : ''}</P>
            <Meter value={d / maxD} color={name === p.persona.name ? t.accent : t.axis} />
          </View>
        ))}
      </Card>
    </Screen>
  );
}
