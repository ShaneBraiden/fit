import { router } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, View } from 'react-native';
import Svg, { Line, Rect, Text as SvgText } from 'react-native-svg';
import { BodyMap, SetsScale, setsColor } from '../../components/body';
import { Button, Card, Chip, Divider, EmptyState, ErrorState, H2, P, Pill, Row, Screen, Skeleton, Stat } from '../../components/ui';
import { fmt, MuscleProgress, MuscleReport, todayIso, useFetch } from '../../lib/api';
import { useFocusRefresh } from '../../lib/focus';
import { space, useTheme } from '../../lib/theme';

const STATUS: Record<MuscleProgress['status'], { kind: 'good' | 'bad' | 'neutral' | 'info'; label: string }> = {
  ready: { kind: 'good', label: 'Ready' },
  recovering: { kind: 'info', label: 'Recovering' },
  overdue: { kind: 'bad', label: 'Overdue' },
  not_trained: { kind: 'neutral', label: 'Not trained' },
};
const VOLUME: Record<MuscleProgress['volume_status'], string> = { low: 'below target', on_target: 'on target', high: 'above target' };

export default function Muscles() {
  const t = useTheme();
  const r = useFetch<MuscleReport>(`/api/me/muscles?today=${todayIso()}`);
  useFocusRefresh(useCallback(() => r.reload(), [r.reload]));
  const [view, setView] = useState<'week' | 'avg'>('week');
  const [sel, setSel] = useState('Chest');
  const d = r.data;
  const hi = d?.sets_target[1] ?? 20, lo = d?.sets_target[0] ?? 10;
  const m = d?.muscles.find((x) => x.muscle === sel);

  return (
    <Screen title="Muscles" subtitle={`Hard sets per muscle each week. ${lo}–${hi} is a common target.`} refreshing={r.loading} onRefresh={r.reload}>
      {r.error ? <ErrorState message={r.error} onRetry={r.reload} /> : !d ? <><Skeleton lines={6} /><Skeleton /></> : <>
        {d.muscles.every((x) => x.sets_avg === 0) && (
          <EmptyState icon="body-outline" title="No sets yet" body="Record a strength or HIIT workout with its exercises. Add sets, reps and kg to track strength too." />
        )}
        <Card>
          <Row gap={space.sm} style={{ marginBottom: space.sm }}>
            <Chip label="This week" on={view === 'week'} onPress={() => setView('week')} />
            <Chip label="8-week average" on={view === 'avg'} onPress={() => setView('avg')} />
          </Row>
          <BodyMap sets={Object.fromEntries(d.muscles.map((x) => [x.muscle, view === 'week' ? x.sets_this_week : x.sets_avg]))}
            selected={sel} onSelect={setSel} top={hi} />
          <SetsScale top={hi} />
          <P muted small style={{ marginTop: 6 }}>Tap a muscle. {fmt.n(d.total_sets_this_week)} sets this week; secondary muscles count half a set.</P>
        </Card>
        {m && <Detail m={m} weeks={d.weeks} />}
        <Card>
          <H2>Every muscle</H2>
          {d.muscles.map((x, i) => (
            <Pressable key={x.muscle} onPress={() => setSel(x.muscle)} accessibilityRole="button">
              {i > 0 && <Divider />}
              <Row gap={space.md}>
                <View style={{ flex: 1 }}>
                  <Row style={{ justifyContent: 'space-between' }}>
                    <P style={{ fontWeight: x.muscle === sel ? '700' : '600' }}>{x.muscle}</P>
                    <P small muted>{fmt.n(x.sets_this_week, 1)} sets</P>
                  </Row>
                  <TargetBar sets={x.sets_this_week} lo={lo} hi={hi} />
                </View>
                <Pill kind={STATUS[x.status].kind} label={STATUS[x.status].label} />
              </Row>
            </Pressable>
          ))}
        </Card>
        <Button label="Record a workout" icon="add-circle-outline" kind="secondary" onPress={() => router.push('/(tabs)/log')} />
      </>}
    </Screen>
  );
}

function TargetBar({ sets, lo, hi }: { sets: number; lo: number; hi: number }) {
  const t = useTheme();
  const max = hi * 1.5;
  return (
    <View style={{ height: 8, borderRadius: 4, backgroundColor: t.surface2, marginTop: 6, overflow: 'hidden' }}>
      <View style={{ position: 'absolute', left: `${(lo / max) * 100}%`, width: `${((hi - lo) / max) * 100}%`, top: 0, bottom: 0,
        backgroundColor: t.good, opacity: 0.2 }} />
      <View style={{ width: `${Math.min(100, (sets / max) * 100)}%`, height: 8, borderRadius: 4, backgroundColor: setsColor(t, sets, hi) }} />
    </View>
  );
}

function Detail({ m, weeks }: { m: MuscleProgress; weeks: string[] }) {
  const t = useTheme();
  return (
    <Card>
      <H2 right={<Pill kind={STATUS[m.status].kind} label={STATUS[m.status].label} />}>{m.muscle}</H2>
      <P muted small>{m.last_trained
        ? `Last trained ${m.days_since === 0 ? 'today' : m.days_since === 1 ? 'yesterday' : `${m.days_since} days ago`} (${fmt.date(m.last_trained)})`
        : 'Not trained in the last 4 months'}</P>
      <Row wrap gap={space.lg} style={{ marginTop: space.md }}>
        <Stat label="This week" value={`${fmt.n(m.sets_this_week, 1)} sets`} sub={VOLUME[m.volume_status]} />
        <Stat label="Weekly avg" value={fmt.n(m.sets_avg, 1)} sub={m.trend_pct == null ? 'last 8 weeks'
          : `${m.trend_pct >= 0 ? '+' : ''}${fmt.pct(m.trend_pct)} vs 4 weeks before`} />
      </Row>
      <View style={{ marginTop: space.md }}><SetsChart m={m} weeks={weeks} /></View>
      <Divider />
      <P small muted style={{ marginBottom: 4 }}>Strength by exercise (estimated 1-rep max)</P>
      {m.exercises.length === 0 && <P muted small>No exercises for this muscle in the last 8 weeks.</P>}
      {m.exercises.map((e) => (
        <Row key={e.exercise} gap={space.md} style={{ paddingVertical: 6 }}>
          <View style={{ flex: 1 }}>
            <P style={{ fontWeight: '600' }}>{e.exercise}</P>
            <P muted small>{e.sessions} session{e.sessions === 1 ? '' : 's'}</P>
          </View>
          {e.latest_e1rm != null ? (
            <View style={{ alignItems: 'flex-end' }}>
              <P style={{ fontWeight: '700' }}>{fmt.n(e.latest_e1rm, 1)} kg</P>
              {e.change_pct != null && e.history.length > 1 && (
                <P small style={{ color: e.change_pct >= 0 ? t.goodInk : t.criticalInk }}>{e.change_pct >= 0 ? '▲' : '▼'} {fmt.pct(Math.abs(e.change_pct))}</P>
              )}
            </View>
          ) : <P muted small>add kg & reps</P>}
        </Row>
      ))}
    </Card>
  );
}

function SetsChart({ m, weeks }: { m: MuscleProgress; weeks: string[] }) {
  const t = useTheme();
  const [w, setW] = useState(300);
  const h = 140, left = 26, bottom = 18, top = 6;
  const ymax = Math.ceil(Math.max(m.target_high + 4, ...m.weekly.map((x) => x.sets)) / 5) * 5;
  const y = (v: number) => top + (h - top - bottom) * (1 - v / ymax);
  const band = (w - left) / weeks.length;
  const bw = Math.min(20, band * 0.6);
  return (
    <View onLayout={(e) => setW(Math.max(160, e.nativeEvent.layout.width))}>
      <Svg width={w} height={h}>
        <Rect x={left} width={w - left} y={y(m.target_high)} height={y(m.target_low) - y(m.target_high)} fill={t.good} opacity={0.1} />
        {[0, ymax / 2, ymax].map((v) => (
          <SvgText key={v} x={left - 4} y={y(v) + 4} fontSize={10} fill={t.muted} textAnchor="end">{v}</SvgText>
        ))}
        <Line x1={left} x2={w} y1={y(0)} y2={y(0)} stroke={t.axis} />
        {m.weekly.map((x, i) => {
          const cx = left + band * i + (band - bw) / 2;
          return <Rect key={x.week} x={cx} y={y(x.sets)} width={bw} height={Math.max(0, y(0) - y(x.sets))} rx={3} fill={t.series[0]} />;
        })}
        {weeks.map((wk, i) => (i % 2 === weeks.length % 2 ? null : (
          <SvgText key={wk} x={left + band * i + band / 2} y={h - 4} fontSize={10} fill={t.muted} textAnchor="middle">
            {new Date(`${wk}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
          </SvgText>
        )))}
      </Svg>
      <P muted small>Sets per week. Shaded: the {m.target_low}–{m.target_high} target.</P>
    </View>
  );
}
