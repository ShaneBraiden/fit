import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert as RNAlert, Platform, Pressable, View } from 'react-native';
import { Button, Card, Chip, Divider, ErrorState, Field, H2, P, Pill, Row, Screen, Skeleton } from '../../components/ui';
import { Catalog, PlanDay, PlanIn, PlanWeek, todayIso, useApi, useFetch, WEEKDAYS } from '../../lib/api';
import { useFocusRefresh } from '../../lib/focus';
import { ACTIVITY_ICON, space, useTheme } from '../../lib/theme';

const ACTIVITIES: PlanDay['activity'][] = ['Strength', 'HIIT', 'Yoga', 'Run', 'Walk', 'Cycle', 'Swim', 'Rest'];
const LIFTING = new Set<PlanDay['activity']>(['Strength', 'HIIT']);
const icon = (a: string) => (a === 'Rest' ? 'bed-outline' : ACTIVITY_ICON[a] ?? 'fitness-outline');

export default function PlanScreen() {
  const api = useApi();
  const plan = useFetch<PlanWeek>(`/api/me/plan?today=${todayIso()}`);
  const cat = useFetch<Catalog>('/api/catalog');
  useFocusRefresh(useCallback(() => plan.reload(), [plan.reload]));
  const [draft, setDraft] = useState<PlanIn | null>(null);
  const [picking, setPicking] = useState(false);
  const pw = plan.data;

  if (draft && cat.data) {
    return <Editor initial={draft} cat={cat.data} onCancel={() => setDraft(null)} onSaved={() => { setDraft(null); setPicking(false); plan.reload(); }} />;
  }
  const remove = async () => { await api('/api/me/plan', undefined, 'DELETE'); plan.reload(); };
  const confirmRemove = () => {
    if (Platform.OS === 'web') { if (window.confirm('Delete your plan? Your workouts are kept.')) remove(); return; }
    RNAlert.alert('Delete your plan?', 'Your workouts are kept.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: remove }]);
  };

  if (plan.error) return <Screen back title="Weekly plan"><ErrorState message={plan.error} onRetry={plan.reload} /></Screen>;
  if (!pw || !cat.data) return <Screen back title="Weekly plan"><Skeleton lines={6} /></Screen>;

  if (!pw.plan || picking) {
    return (
      <Screen back title="Pick a split" subtitle="Start from one, then change any day">
        {pw.plan && <Button label="Back to my plan" kind="secondary" icon="arrow-back" onPress={() => setPicking(false)} />}
        {cat.data.plan_templates.map((tpl) => (
          <Card key={tpl.key} onPress={() => setDraft({ name: tpl.name, days: tpl.days })}>
            <H2 right={<Ionicons name="chevron-forward" size={18} color="#888" />}>{tpl.name}</H2>
            <P muted small>{tpl.days.filter((d) => d.activity !== 'Rest').length} training days · {tpl.days.map((d, i) => `${WEEKDAYS[i]} ${d.label}`).join(' · ')}</P>
          </Card>
        ))}
        <Card onPress={() => setDraft({ name: 'My plan', days: WEEKDAYS.map(() => ({ label: 'Rest', activity: 'Rest', focus: [], exercises: [] })) })}>
          <H2>Start from scratch</H2>
          <P muted small>Seven rest days for you to fill in.</P>
        </Card>
      </Screen>
    );
  }

  return (
    <Screen back title={pw.plan.name} subtitle={`${pw.done} of ${pw.planned} training days done this week`} refreshing={plan.loading} onRefresh={plan.reload}>
      <Row gap={space.sm}>
        <View style={{ flex: 1 }}><Button label="Edit plan" icon="create-outline" onPress={() => setDraft({ name: pw.plan!.name, days: pw.plan!.days })} /></View>
        <View style={{ flex: 1 }}><Button label="Switch split" kind="secondary" icon="swap-horizontal" onPress={() => setPicking(true)} /></View>
      </Row>
      {pw.week.map((d) => <DayCard key={d.date} d={d} />)}
      <Button label="Delete plan" kind="secondary" icon="trash-outline" onPress={confirmRemove} />
    </Screen>
  );
}

function DayCard({ d }: { d: PlanWeek['week'][number] }) {
  const t = useTheme();
  const day = d.day!;
  const rest = day.activity === 'Rest';
  return (
    <Card style={d.today ? { borderColor: t.accent, borderWidth: 2 } : rest ? { backgroundColor: t.surface2 } : undefined}
      onPress={d.today && !rest && !d.done ? () => router.push('/(tabs)/log') : undefined}>
      <Row gap={space.md}>
        <Ionicons name={icon(day.activity) as never} size={22} color={rest ? t.muted : t.accent} />
        <View style={{ flex: 1 }}>
          <P small muted>{WEEKDAYS[d.weekday]} {new Date(`${d.date}T00:00:00`).getDate()}{d.today ? ' · today' : ''}</P>
          <P style={{ fontWeight: '700' }}>{day.label}</P>
        </View>
        {!rest && (d.done ? <Pill kind="good" label="Done" /> : d.date < todayIso() ? <Pill kind="bad" label="Missed" />
          : d.today ? <Pill kind="info" label="Tap to record" /> : <Pill kind="neutral" label="Planned" />)}
      </Row>
      {!rest && (day.focus.length > 0 || day.exercises.length > 0) && (
        <P muted small style={{ marginTop: 6 }}>{[day.focus.join(', '), day.exercises.join(' · ')].filter(Boolean).join('\n')}</P>
      )}
    </Card>
  );
}

function Editor({ initial, cat, onCancel, onSaved }: { initial: PlanIn; cat: Catalog; onCancel: () => void; onSaved: () => void }) {
  const t = useTheme();
  const api = useApi();
  const [name, setName] = useState(initial.name);
  const [days, setDays] = useState<PlanDay[]>(initial.days.map((d) => ({ ...d, focus: [...(d.focus ?? [])], exercises: [...(d.exercises ?? [])] })));
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (i: number, patch: Partial<PlanDay>) => setDays((ds) => ds.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const save = async () => {
    setBusy(true); setError(null);
    try { await api(`/api/me/plan?today=${todayIso()}`, { name: name.trim() || 'My plan', days }, 'PUT'); onSaved(); } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };
  const toggle = <T,>(xs: T[], x: T) => (xs.includes(x) ? xs.filter((y) => y !== x) : [...xs, x]);

  return (
    <Screen title="Edit plan" subtitle={`${days.filter((d) => d.activity !== 'Rest').length} training days a week · tap a day to change it`}>
      <Card><Field label="Plan name" value={name} onChangeText={setName} maxLength={40} /></Card>
      {days.map((d, i) => {
        const lifting = LIFTING.has(d.activity);
        const options = cat.exercises[d.activity] ?? [];
        const hits = (e: string) => [...(cat.exercise_muscles[e]?.primary ?? []), ...(cat.exercise_muscles[e]?.secondary ?? [])].some((m) => d.focus.includes(m));
        const sorted = [...options].sort((a, b) => Number(hits(b)) - Number(hits(a)) || a.localeCompare(b));
        return (
          <Card key={i}>
            <Pressable onPress={() => setOpen(open === i ? null : i)} accessibilityRole="button">
              <Row gap={space.md}>
                <Ionicons name={icon(d.activity) as never} size={20} color={d.activity === 'Rest' ? t.muted : t.accent} />
                <View style={{ flex: 1 }}>
                  <P small muted>{WEEKDAYS[i]}</P>
                  <P style={{ fontWeight: '700' }}>{d.label}{d.exercises.length ? <P small muted>  · {d.exercises.length} exercises</P> : null}</P>
                </View>
                <Ionicons name={open === i ? 'chevron-up' : 'chevron-down'} size={18} color={t.muted} />
              </Row>
            </Pressable>
            {open === i && <View style={{ gap: space.sm, marginTop: space.md }}>
              <Field label="Name" value={d.label} onChangeText={(v) => set(i, { label: v })} maxLength={30} placeholder="e.g. Chest & Back" />
              <P small muted>Activity</P>
              <Row wrap gap={6}>
                {ACTIVITIES.map((a) => <Chip key={a} label={a} icon={icon(a)} on={d.activity === a} onPress={() => set(i, {
                  activity: a, label: a === 'Rest' ? 'Rest' : d.activity === 'Rest' ? a : d.label, exercises: [], focus: LIFTING.has(a) ? d.focus : [] })} />)}
              </Row>
              {lifting && <>
                <Divider />
                <P small muted>Muscles this day trains</P>
                <Row wrap gap={6}>{cat.muscles.map((m) => <Chip key={m} label={m} on={d.focus.includes(m)} onPress={() => set(i, { focus: toggle(d.focus, m) })} />)}</Row>
              </>}
              {d.activity !== 'Rest' && options.length > 0 && <>
                <Divider />
                <P small muted>Exercises{lifting && d.focus.length ? ' (★ works the muscles you picked)' : ''}</P>
                <Row wrap gap={6}>{sorted.map((e) => <Chip key={e} label={`${e}${lifting && hits(e) ? ' ★' : ''}`} on={d.exercises.includes(e)}
                  onPress={() => set(i, { exercises: toggle(d.exercises, e) })} />)}</Row>
              </>}
            </View>}
          </Card>
        );
      })}
      {error && <P style={{ color: t.criticalInk }}>{error}</P>}
      <Button label={busy ? 'Saving…' : 'Save plan'} icon="checkmark" busy={busy} onPress={save} />
      <Button label="Cancel" kind="secondary" onPress={onCancel} />
    </Screen>
  );
}
