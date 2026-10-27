import { router, useLocalSearchParams } from 'expo-router';
import { Alert as RNAlert, Platform, ScrollView, View } from 'react-native';
import { BodyMap } from '../../components/body';
import { Legend } from '../../components/charts';
import { Button, Card, Divider, ErrorState, H2, P, Row, Skeleton } from '../../components/ui';
import { Comparison, fmt, todayIso, useApi, useFetch } from '../../lib/api';
import { space, useTheme } from '../../lib/theme';

const days = (n: number) => `${n} day${n === 1 ? '' : 's'}`;

export default function Compare() {
  const t = useTheme();
  const api = useApi();
  const { id } = useLocalSearchParams<{ id: string }>();
  const r = useFetch<Comparison>(id ? `/api/me/friends/${id}/compare?today=${todayIso()}` : null);
  const c = r.data;
  const colors = [t.series[0], t.series[1]];

  const remove = async () => { await api(`/api/me/friends/${id}`, undefined, 'DELETE'); router.back(); };
  const confirmRemove = () => {
    const msg = "You'll stop seeing each other's numbers.";
    if (Platform.OS === 'web') { if (window.confirm(`Remove friend? ${msg}`)) remove(); return; }
    RNAlert.alert('Remove friend?', msg, [{ text: 'Cancel', style: 'cancel' }, { text: 'Remove', style: 'destructive', onPress: remove }]);
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: t.page }} contentContainerStyle={{ padding: space.lg, gap: space.md, paddingBottom: space.xl * 2 }}>
      {r.error ? <ErrorState message={r.error} onRetry={r.reload} /> : !c ? <><Skeleton lines={6} /><Skeleton /></> : <>
        <Card>
          <H2>You vs {c.friend.name}</H2>
          <Row style={{ marginBottom: 4 }}>
            <View style={{ flex: 1.2 }} />
            <P small style={{ flex: 1, fontWeight: '700', color: colors[0] }}>You</P>
            <P small style={{ flex: 1, fontWeight: '700', color: colors[1] }} >{c.friend.name}</P>
          </Row>
          {([
            ['Streak', days(c.me.streak), days(c.friend.streak)],
            ['Longest', days(c.me.longest_streak), days(c.friend.longest_streak)],
            ['This week', `${fmt.n(c.me.week_minutes)} min`, `${fmt.n(c.friend.week_minutes)} min`],
            ['Level', c.me.level, c.friend.level],
            ['Style', c.me.persona, c.friend.persona],
            ['Sessions/wk', fmt.n(c.me.stats.sessions_per_week, 1), fmt.n(c.friend.stats.sessions_per_week, 1)],
            ['Minutes/wk', fmt.n(c.me.stats.minutes_per_week), fmt.n(c.friend.stats.minutes_per_week)],
          ] as [string, string, string][]).map(([k, a, b]) => (
            <View key={k}>
              <Divider />
              <Row><P small muted style={{ flex: 1.2 }}>{k}</P><P small style={{ flex: 1 }}>{a}</P><P small style={{ flex: 1 }}>{b}</P></Row>
            </View>
          ))}
        </Card>

        <Card>
          <H2>Minutes per week</H2>
          {c.me.weekly.map((w, i) => {
            const fw = c.friend.weekly[i];
            const max = Math.max(1, ...c.me.weekly.map((x) => x.minutes), ...c.friend.weekly.map((x) => x.minutes));
            return (
              <Row key={w.week} gap={space.sm} style={{ marginBottom: 6 }}>
                <P small muted style={{ width: 48 }}>{new Date(`${w.week}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</P>
                <View style={{ flex: 1, gap: 2 }}>
                  {[w.minutes, fw?.minutes ?? 0].map((v, k) => (
                    <View key={k} style={{ height: 7, borderRadius: 4, width: `${Math.max(1, (v / max) * 100)}%`, backgroundColor: colors[k] }} />
                  ))}
                </View>
              </Row>
            );
          })}
          <Legend items={[{ label: 'You', color: colors[0] }, { label: c.friend.name, color: colors[1] }]} />
        </Card>

        <Card>
          <H2>Sets per muscle</H2>
          <P muted small style={{ marginBottom: space.sm }}>Average per week over the last 4 weeks.</P>
          <Row gap={space.sm}>
            <View style={{ flex: 1 }}><P small muted style={{ textAlign: 'center' }}>You</P><BodyMap sets={c.me.muscle_sets} height={170} /></View>
            <View style={{ flex: 1 }}><P small muted style={{ textAlign: 'center' }}>{c.friend.name}</P><BodyMap sets={c.friend.muscle_sets} height={170} /></View>
          </Row>
          {Object.keys(c.me.muscle_sets).map((m) => {
            const a = c.me.muscle_sets[m], b = c.friend.muscle_sets[m];
            const max = Math.max(10, ...Object.values(c.me.muscle_sets), ...Object.values(c.friend.muscle_sets));
            return (
              <Row key={m} gap={space.sm} style={{ marginTop: 6 }}>
                <P small style={{ width: 80 }}>{m}</P>
                <View style={{ flex: 1, gap: 2 }}>
                  {[a, b].map((v, k) => <View key={k} style={{ height: 6, borderRadius: 3, width: `${Math.max(1, (v / max) * 100)}%`, backgroundColor: colors[k] }} />)}
                </View>
                <P small muted style={{ width: 62, textAlign: 'right' }}>{fmt.n(a, 1)} / {fmt.n(b, 1)}</P>
              </Row>
            );
          })}
        </Card>
        <Button label="Remove friend" kind="secondary" icon="person-remove-outline" onPress={confirmRemove} />
      </>}
    </ScrollView>
  );
}
