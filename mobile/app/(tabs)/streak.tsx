import { router } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Text, View } from 'react-native';
import { StreakBadge } from '../../components/streak';
import { Card, Chip, ErrorState, H2, P, Row, Screen, Skeleton, Stat } from '../../components/ui';
import { fmt, localIso, Streak, todayIso, useFetch, WEEKDAYS } from '../../lib/api';
import { useFocusRefresh } from '../../lib/focus';
import { space, useTheme } from '../../lib/theme';

export default function StreakScreen() {
  const t = useTheme();
  const r = useFetch<Streak>(`/api/me/streak?today=${todayIso()}`);
  useFocusRefresh(useCallback(() => r.reload(), [r.reload]));
  const [offset, setOffset] = useState(0);
  const days = useMemo(() => new Map((r.data?.days ?? []).map((d) => [d.date, d])), [r.data]);
  const s = r.data;

  const today = todayIso();
  const now = new Date();
  const month = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  const lead = (month.getDay() + 6) % 7; // Monday first
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells = Array.from({ length: Math.ceil((lead + count) / 7) * 7 }, (_, i) => {
    const n = i - lead + 1;
    return n < 1 || n > count ? null : localIso(new Date(month.getFullYear(), month.getMonth(), n)).slice(0, 10);
  });
  const trained = cells.filter((c): c is string => !!c && days.has(c));
  const maxMin = Math.max(30, ...trained.map((c) => days.get(c)!.minutes));
  const rest = new Set(s?.rest_weekdays ?? []);

  return (
    <Screen back title="Streak" subtitle="Days in a row with a workout" refreshing={r.loading} onRefresh={r.reload}>
      {r.error ? <ErrorState message={r.error} onRetry={r.reload} /> : !s ? <><Skeleton /><Skeleton lines={6} /></> : <>
        <Card><StreakBadge s={s} /></Card>
        <Card>
          <Row wrap gap={space.lg}>
            <Stat label="Longest streak" value={`${s.longest} day${s.longest === 1 ? '' : 's'}`} />
            <Stat label="This week" value={s.weekly_goal ? `${s.this_week_sessions} / ${s.weekly_goal}` : `${s.this_week_sessions} days`}
              sub={s.weekly_goal ? 'days from your plan' : 'days trained'} />
            <Stat label="Days trained" value={fmt.n(s.active_days_total)} sub="all time" />
          </Row>
        </Card>
        <Card>
          <H2 right={<Row gap={6}>
            <Chip label="‹" onPress={() => setOffset(Math.max(-12, offset - 1))} />
            <Chip label="›" onPress={() => setOffset(Math.min(0, offset + 1))} />
          </Row>}>{month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</H2>
          <P muted small style={{ marginBottom: space.sm }}>{trained.length} day{trained.length === 1 ? '' : 's'} trained · {fmt.n(trained.reduce((a, c) => a + days.get(c)!.minutes, 0))} min</P>
          <Row style={{ marginBottom: 4 }}>
            {WEEKDAYS.map((w) => <Text key={w} style={{ flex: 1, textAlign: 'center', fontSize: 11, color: t.muted }}>{w[0]}</Text>)}
          </Row>
          {Array.from({ length: cells.length / 7 }, (_, row) => (
            <Row key={row} gap={4} style={{ marginBottom: 4 }}>
              {cells.slice(row * 7, row * 7 + 7).map((c, i) => {
                if (!c) return <View key={`x${i}`} style={{ flex: 1, aspectRatio: 1 }} />;
                const d = days.get(c);
                const kind = d ? 'done' : c > today ? 'future' : rest.has(i) ? 'rest' : 'missed';
                return (
                  <View key={c} style={{ flex: 1, aspectRatio: 1, borderRadius: 8, alignItems: 'center', justifyContent: 'center',
                    backgroundColor: d ? t.accent : kind === 'rest' ? 'transparent' : t.surface2,
                    opacity: d ? 0.45 + 0.55 * Math.min(1, d.minutes / maxMin) : kind === 'future' ? 0.4 : 1,
                    borderWidth: c === today ? 2 : kind === 'rest' ? 1 : 0, borderStyle: kind === 'rest' ? 'dashed' : 'solid',
                    borderColor: c === today ? '#f59e0b' : t.axis }}
                    accessibilityLabel={d ? `${c}: ${d.workouts} workouts, ${Math.round(d.minutes)} minutes` : `${c}: ${kind}`}>
                    <Text style={{ fontSize: 12, fontWeight: d ? '700' : '400', color: d ? '#fff' : t.text2 }}>{Number(c.slice(8))}</Text>
                  </View>
                );
              })}
            </Row>
          ))}
          <P muted small style={{ marginTop: 6 }}>Blue: trained (darker = longer). Dashed: planned rest day.</P>
        </Card>
        <Card onPress={() => router.push('/(tabs)/plan')}>
          <P small muted>{s.rest_weekdays.length
            ? `Rest days in your plan (${s.rest_weekdays.map((i) => WEEKDAYS[i]).join(', ')}) keep your streak going without adding to it. Tap to change your plan.`
            : 'Every day counts right now. Tap to set up a weekly plan; its rest days won\'t break your streak.'}</P>
        </Card>
      </>}
    </Screen>
  );
}
