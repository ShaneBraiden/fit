import { Ionicons } from '@expo/vector-icons';
import { View } from 'react-native';
import { Meter } from '../../components/charts';
import { Card, Divider, EmptyState, ErrorState, H2, P, Row, Screen, Skeleton } from '../../components/ui';
import { fmt, Profile, Recommendation, useFetch } from '../../lib/api';
import { useSession } from '../../lib/session';
import { space, useTheme } from '../../lib/theme';

export default function Insights() {
  const t = useTheme();
  const { userId } = useSession();
  const recs = useFetch<Recommendation[]>(userId ? `/api/users/${userId}/recommendations` : null);
  const prof = useFetch<Profile>(userId ? `/api/users/${userId}/profile` : null);
  const refresh = () => { recs.reload(); prof.reload(); };
  const p = prof.data;
  const dist = p ? Object.entries(p.persona.distances).sort((a, b) => a[1] - b[1]) : [];
  const maxD = dist.length ? Math.max(...dist.map((d) => d[1])) : 1;

  return (
    <Screen title="Insights" subtitle="Patterns mined from everyone's workouts, applied to yours" refreshing={recs.loading} onRefresh={refresh}>
      <Card>
        <H2>Try next</H2>
        <P muted small style={{ marginBottom: space.sm }}>Association rules applied to your latest sessions: what people usually add to the exercises you did.</P>
        {recs.error ? <ErrorState message={recs.error} onRetry={recs.reload} /> : !recs.data ? <Skeleton lines={3} />
          : recs.data.length === 0 ? <P muted>No suggestions: your recent sessions already contain what usually goes with them.</P>
            : recs.data.map((r, i) => (
              <View key={r.exercise}>
                {i > 0 && <Divider />}
                <Row gap={space.md}>
                  <Ionicons name="add-circle-outline" size={22} color={t.accent} />
                  <View style={{ flex: 1 }}>
                    <P style={{ fontWeight: '600' }}>{r.exercise}</P>
                    <P muted small>after {r.because.join(' + ')}: done together {fmt.pct(r.confidence)} of the time,
                      {' '}{r.lift.toFixed(1)}× more often than chance</P>
                    <Meter value={r.confidence} />
                  </View>
                </Row>
              </View>
            ))}
      </Card>

      <Card>
        <H2>Your weekly routine</H2>
        <P muted small style={{ marginBottom: space.sm }}>Sequential patterns (GSP) you follow in at least half of your weeks.</P>
        {!p ? <Skeleton lines={2} /> : p.routines.length === 0 ? <P muted>No regular weekly order found yet.</P> : p.routines.map((r) => (
          <View key={r.text} style={{ marginBottom: space.sm }}>
            <Row wrap gap={6}>
              {r.pattern.map((el, i) => (
                <Row key={i} gap={6}>
                  {i > 0 && <Ionicons name="arrow-forward" size={14} color={t.muted} />}
                  <View style={{ backgroundColor: t.accentWash, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 }}>
                    <P small style={{ color: t.accentInk, fontWeight: '600' }}>{el.join(' + ')}</P>
                  </View>
                </Row>
              ))}
            </Row>
            <P muted small style={{ marginTop: 4 }}>in {fmt.pct(r.weeks)} of your weeks</P>
          </View>
        ))}
      </Card>

      <Card>
        <H2>How close you are to each persona</H2>
        <P muted small style={{ marginBottom: space.sm }}>Distance to each k-means cluster centre (shorter bar = closer).</P>
        {!p ? <Skeleton lines={4} /> : dist.map(([name, d]) => (
          <View key={name} style={{ marginBottom: 8 }}>
            <Row style={{ justifyContent: 'space-between' }}>
              <P small style={{ fontWeight: name === p.persona.name ? '700' : '400' }}>{name}</P>
              <P small muted>{d.toFixed(2)}</P>
            </Row>
            <Meter value={d / maxD} color={name === p.persona.name ? t.accent : t.axis} />
          </View>
        ))}
      </Card>

      <Card>
        <H2>People who train like you</H2>
        <P muted small style={{ marginBottom: space.sm }}>Your 5 nearest neighbours in behaviour space (k-NN).</P>
        {!p ? <Skeleton lines={3} /> : p.similar.length === 0 ? <EmptyState icon="people-outline" title="No neighbours yet" />
          : p.similar.map((s) => (
            <Row key={s.user_id} gap={space.md} style={{ paddingVertical: 5 }}>
              <Ionicons name="person-circle-outline" size={22} color={t.muted} />
              <View style={{ flex: 1 }}><P>{s.name}</P><P muted small>{s.persona}</P></View>
            </Row>
          ))}
      </Card>
    </Screen>
  );
}
