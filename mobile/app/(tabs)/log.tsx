import { Ionicons } from '@expo/vector-icons';
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import * as Location from 'expo-location';
import { router } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { View } from 'react-native';
import { RouteMap, SpeedChart } from '../../components/charts';
import { Button, Card, Chip, Divider, ErrorState, Field, H2, P, Pill, Row, Screen, Stat } from '../../components/ui';
import { Catalog, fmt, localIso, RecordRequest, RecordResult, useApi, useFetch } from '../../lib/api';
import { ACTIVITY_ICON, space, useTheme } from '../../lib/theme';

type Activity = RecordRequest['activity'];
type Fix = { t: number; lat: number; lon: number; accuracy: number | null };

const ACTIVITIES: Activity[] = ['Run', 'Walk', 'Cycle', 'Swim', 'Strength', 'HIIT', 'Yoga'];
const GPS = new Set<Activity>(['Run', 'Walk', 'Cycle']);
const SPLITS: { key: NonNullable<RecordRequest['kind']>; label: string }[] = [
  { key: 'push', label: 'Push' }, { key: 'pull', label: 'Pull' }, { key: 'legs', label: 'Legs' }];
const DAYS = [{ label: 'Today', back: 0 }, { label: 'Yesterday', back: 1 }, { label: '2 days ago', back: 2 }];
const MAX_ACCURACY_M = 35; // the server drops fixes worse than this too

function haversine(a: Fix, b: Fix): number {
  const r = Math.PI / 180;
  const h = Math.sin((b.lat - a.lat) * r / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin((b.lon - a.lon) * r / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

export default function Record() {
  const api = useApi();
  const [activity, setActivity] = useState<Activity>('Run');
  const [mode, setMode] = useState<'gps' | 'manual'>('gps');
  const [res, setRes] = useState<RecordResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const gpsOk = GPS.has(activity);
  const useGps = gpsOk && mode === 'gps';

  const upload = async (body: RecordRequest) => {
    setBusy(true); setError(null);
    try {
      setRes(await api<RecordResult>('/api/me/workouts', body));
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (res) return <ResultView res={res} onDone={() => setRes(null)} />;

  return (
    <Screen title="Record a workout" subtitle="Track it live with GPS, or log one you've done">
      <Card>
        <H2>Activity</H2>
        <Row wrap gap={space.sm}>
          {ACTIVITIES.map((a) => <Chip key={a} label={a} icon={ACTIVITY_ICON[a]} on={a === activity} onPress={() => setActivity(a)} />)}
        </Row>
        {gpsOk && <>
          <Divider />
          <Row gap={space.sm}>
            <Chip label="Track with GPS" icon="navigate-outline" on={mode === 'gps'} onPress={() => setMode('gps')} />
            <Chip label="Log manually" icon="create-outline" on={mode === 'manual'} onPress={() => setMode('manual')} />
          </Row>
        </>}
      </Card>
      {useGps ? <GpsRecorder activity={activity} busy={busy} onFinish={upload} />
        : <ManualForm activity={activity} busy={busy} onSubmit={upload} />}
      {error && <ErrorState message={error} />}
    </Screen>
  );
}

// ----------------------------------------------------------------------------- live GPS tracking

function GpsRecorder({ activity, busy, onFinish }: { activity: Activity; busy: boolean; onFinish: (b: RecordRequest) => Promise<boolean> }) {
  const t = useTheme();
  const [state, setState] = useState<'idle' | 'tracking' | 'paused' | 'stopped'>('idle');
  // Fixes live in a ref (an hour is 3,600 of them); `count` re-renders the screen as they arrive.
  const fixes = useRef<Fix[]>([]);
  const good = useRef<Fix[]>([]);
  const meters = useRef(0);
  const [count, setCount] = useState(0);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [problem, setProblem] = useState<string | null>(null);
  const sub = useRef<Location.LocationSubscription | null>(null);
  const started = useRef<Date | null>(null);
  const lastTick = useRef<number | null>(null);

  // Moving-time clock: counts only while tracking.
  useEffect(() => {
    if (state !== 'tracking') { lastTick.current = null; return; }
    lastTick.current = Date.now();
    const id = setInterval(() => {
      const now = Date.now();
      setElapsed((e) => e + (now - (lastTick.current ?? now)) / 1000);
      lastTick.current = now;
    }, 1000);
    return () => clearInterval(id);
  }, [state]);

  useEffect(() => () => { sub.current?.remove(); deactivateKeepAwake('record'); }, []);

  const startWatch = async () => {
    setProblem(null);
    const perm = await Location.requestForegroundPermissionsAsync();
    if (perm.status !== 'granted') {
      setProblem('FitMine needs location access to track this workout. Allow it in your phone settings, or log the workout manually.');
      return false;
    }
    sub.current = await Location.watchPositionAsync(
      { accuracy: Location.Accuracy.BestForNavigation, timeInterval: 1000, distanceInterval: 2 },
      (loc) => {
        const f: Fix = { t: loc.timestamp, lat: loc.coords.latitude, lon: loc.coords.longitude, accuracy: loc.coords.accuracy };
        fixes.current.push(f);
        if ((f.accuracy ?? 0) <= MAX_ACCURACY_M) {
          const prev = good.current[good.current.length - 1];
          if (prev) meters.current += haversine(prev, f);
          good.current.push(f);
        }
        setAccuracy(f.accuracy);
        setCount(fixes.current.length);
      },
    );
    activateKeepAwakeAsync('record').catch(() => undefined);
    return true;
  };
  const stopWatch = () => { sub.current?.remove(); sub.current = null; deactivateKeepAwake('record'); };

  const start = async () => {
    if (await startWatch()) { started.current = new Date(); reset(); setState('tracking'); }
  };
  const pause = () => { stopWatch(); setState('paused'); };
  const resume = async () => { if (await startWatch()) setState('tracking'); };
  const stop = () => { stopWatch(); setState('stopped'); };
  const reset = () => { fixes.current = []; good.current = []; meters.current = 0; setCount(0); setAccuracy(null); setElapsed(0); };
  const discard = () => { stopWatch(); reset(); setState('idle'); };
  const save = async () => {
    const ok = await onFinish({ activity, start_time: started.current ? localIso(started.current) : undefined,
      duration_min: Math.max(elapsed, 1) / 60, track: good.current });
    if (ok) discard();
  };

  const km = meters.current / 1000;
  const tooShort = good.current.length < 2 || elapsed < 30;
  // At most ~300 points on the live map.
  const shown = useMemo(() => {
    const g = good.current;
    const step = Math.max(1, Math.ceil(g.length / 300));
    return g.filter((_, i) => i % step === 0 || i === g.length - 1);
  }, [count]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <Card>
        <Row wrap gap={space.lg}>
          <Stat label="Time" value={fmt.clock(elapsed)} />
          <Stat label="Distance" value={`${km.toFixed(2)} km`} />
          <Stat label={activity === 'Cycle' ? 'Speed' : 'Pace'}
            value={km > 0.05 ? (activity === 'Cycle' ? `${(km / (elapsed / 3600)).toFixed(1)} km/h` : fmt.pace(elapsed / 60 / km)) : '–'} />
        </Row>
        {state !== 'idle' && (
          <Row gap={6} style={{ marginTop: space.sm }}>
            <Ionicons name={accuracy != null && accuracy <= MAX_ACCURACY_M ? 'cellular' : 'cellular-outline'} size={14}
              color={accuracy != null && accuracy <= MAX_ACCURACY_M ? t.good : t.warning} />
            <P small muted>{accuracy == null ? 'Waiting for GPS…' : `GPS accuracy ${Math.round(accuracy)} m`}{state === 'paused' ? ' · paused' : ''}</P>
          </Row>
        )}
        {shown.length > 1 && <View style={{ marginTop: space.md }}><RouteMap lat={shown.map((f) => f.lat)} lon={shown.map((f) => f.lon)} height={180} /></View>}
      </Card>

      {problem && <P style={{ color: t.criticalInk }}>{problem}</P>}
      {state === 'idle' && <>
        <Button label={`Start ${activity.toLowerCase()}`} icon="play" onPress={start} />
        <P muted small style={{ textAlign: 'center' }}>Keep FitMine open while you record; the screen stays on.</P>
      </>}
      {state === 'tracking' && <Row gap={space.sm}>
        <View style={{ flex: 1 }}><Button label="Pause" kind="secondary" icon="pause" onPress={pause} /></View>
        <View style={{ flex: 1 }}><Button label="Finish" icon="stop" onPress={stop} /></View>
      </Row>}
      {state === 'paused' && <Row gap={space.sm}>
        <View style={{ flex: 1 }}><Button label="Resume" kind="secondary" icon="play" onPress={resume} /></View>
        <View style={{ flex: 1 }}><Button label="Finish" icon="stop" onPress={stop} /></View>
      </Row>}
      {state === 'stopped' && <>
        {tooShort && <P muted small>Too short to save: record at least 30 seconds with a GPS signal.</P>}
        <Button label={busy ? 'Saving…' : 'Save workout'} icon="cloud-upload-outline" onPress={save} busy={busy} disabled={tooShort} />
        <Button label="Discard" kind="secondary" icon="trash-outline" onPress={discard} />
      </>}
    </>
  );
}

// ----------------------------------------------------------------------------- manual log

function ManualForm({ activity, busy, onSubmit }: { activity: Activity; busy: boolean; onSubmit: (b: RecordRequest) => Promise<boolean> }) {
  const t = useTheme();
  const catalog = useFetch<Catalog>('/api/catalog');
  const now = new Date();
  const [day, setDay] = useState(0);
  const [time, setTime] = useState(`${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`);
  const [duration, setDuration] = useState('');
  const [distance, setDistance] = useState('');
  const [avgHr, setAvgHr] = useState('');
  const [calories, setCalories] = useState('');
  const [split, setSplit] = useState<RecordRequest['kind']>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => { setPicked([]); setSplit(null); }, [activity]);

  const options = catalog.data?.exercises[activity] ?? [];
  const num = (s: string) => (s.trim() === '' ? null : Number(s.replace(',', '.')));
  const submit = async () => {
    setProblem(null);
    const mins = num(duration);
    const m = /^(\d{1,2}):(\d{2})$/.exec(time.trim());
    if (!mins || mins <= 0) return setProblem('Enter how many minutes the workout took.');
    if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return setProblem('Enter the start time as HH:MM, e.g. 07:30.');
    const start = new Date();
    start.setDate(start.getDate() - day);
    start.setHours(Number(m[1]), Number(m[2]), 0, 0);
    if (start.getTime() > Date.now()) return setProblem('That start time is in the future.');
    const ok = await onSubmit({ activity, start_time: localIso(start), duration_min: mins, kind: split,
      distance_km: GPS.has(activity) || activity === 'Swim' ? num(distance) : null, avg_hr: num(avgHr), calories: num(calories),
      exercises: picked });
    if (ok) { setDuration(''); setDistance(''); setAvgHr(''); setCalories(''); setPicked([]); }
  };

  return (
    <>
      <Card>
        <H2>When</H2>
        <Row wrap gap={space.sm}>{DAYS.map((d) => <Chip key={d.back} label={d.label} on={day === d.back} onPress={() => setDay(d.back)} />)}</Row>
        <Row gap={space.md} wrap style={{ marginTop: space.md }}>
          <Field label="Start time" value={time} onChangeText={setTime} keyboardType="numbers-and-punctuation" placeholder="07:30" />
          <Field label="Duration (min)" value={duration} onChangeText={setDuration} keyboardType="decimal-pad" />
        </Row>
      </Card>
      <Card>
        <H2>Details</H2>
        <Row gap={space.md} wrap>
          {(GPS.has(activity) || activity === 'Swim') && <Field label="Distance (km)" value={distance} onChangeText={setDistance} keyboardType="decimal-pad" />}
          <Field label="Avg heart rate" value={avgHr} onChangeText={setAvgHr} keyboardType="number-pad" hint="Optional, bpm" />
          <Field label="Calories" value={calories} onChangeText={setCalories} keyboardType="number-pad" hint="Optional; we estimate it" />
        </Row>
        {activity === 'Strength' && <>
          <Divider />
          <P small muted style={{ marginBottom: 6 }}>Session</P>
          <Row wrap gap={space.sm}>
            {SPLITS.map((s) => <Chip key={s.key} label={s.label} on={split === s.key} onPress={() => setSplit(split === s.key ? null : s.key)} />)}
          </Row>
        </>}
      </Card>
      {options.length > 0 && (
        <Card>
          <H2>Exercises</H2>
          <P muted small style={{ marginBottom: space.sm }}>Pick what you did. This is what your "Try next" suggestions are based on.</P>
          <Row wrap gap={space.sm}>
            {options.map((e) => <Chip key={e} label={e} on={picked.includes(e)}
              onPress={() => setPicked((p) => (p.includes(e) ? p.filter((x) => x !== e) : [...p, e]))} />)}
          </Row>
        </Card>
      )}
      {problem && <P style={{ color: t.criticalInk }}>{problem}</P>}
      <Button label={busy ? 'Saving…' : 'Save workout'} icon="checkmark" onPress={submit} busy={busy} />
    </>
  );
}

// ----------------------------------------------------------------------------- after saving

function ResultView({ res, onDone }: { res: RecordResult; onDone: () => void }) {
  const t = useTheme();
  const d = res.detail;
  const v = res.verdict;
  const w = res.workout;
  const changed = res.level_before !== res.level_after || res.persona_before !== res.persona_after;
  return (
    <Screen title="Workout saved" subtitle={`${w.title} · ${fmt.date(w.start_time)}`}>
      <Card style={{ borderLeftWidth: 3, borderLeftColor: v.flagged ? t.critical : t.good }}>
        <Row style={{ justifyContent: 'space-between' }}>
          <H2>{v.flagged ? 'This one needs a look' : 'All good'}</H2>
          <Pill kind={v.flagged ? 'bad' : 'good'} label={v.flagged ? 'Not counted' : 'Counted'} />
        </Row>
        {v.flagged
          ? <>
            {v.reasons.map((r) => <P key={r} small style={{ marginTop: 4 }}>• {fmt.reason(r)}</P>)}
            <P muted small style={{ marginTop: 6 }}>It's saved, but it won't count towards your stats. Delete it from the workout page if it was a mistake.</P>
          </>
          : <P muted small>It counts towards your stats and predictions.</P>}
      </Card>

      <Card>
        <Row wrap gap={space.lg}>
          <Stat label="Duration" value={`${Math.round(w.duration_min)} min`} />
          {w.distance_km ? <Stat label="Distance" value={`${w.distance_km.toFixed(2)} km`} /> : null}
          {w.avg_hr ? <Stat label="Avg HR" value={`${fmt.n(w.avg_hr)} bpm`} /> : null}
          <Stat label="Calories" value={fmt.n(w.calories)} />
        </Row>
        {d.lat && d.lon && <>
          <Divider />
          {d.run_kind && <P muted small>Workout type: <P small style={{ fontWeight: '600' }}>{w.session_type.replace(/([a-z])([A-Z])/g, '$1 $2')}</P>
            {d.route ? <> · on <P small style={{ fontWeight: '600' }}>{String(d.route.name)}</P></> : ''}</P>}
          {d.speed_kmh && d.segments && <View style={{ marginTop: space.sm }}><SpeedChart speed={d.speed_kmh} segments={d.segments} /></View>}
          <View style={{ marginTop: space.md }}><RouteMap lat={d.lat} lon={d.lon} segments={d.segments} height={200} /></View>
        </>}
      </Card>

      <Card>
        <H2>{changed ? 'What changed' : 'Where you stand'}</H2>
        <P small muted>Fitness level</P>
        <P style={{ fontWeight: '600' }}>{res.level_before === res.level_after ? res.level_after : `${res.level_before} → ${res.level_after}`}</P>
        <P small muted style={{ marginTop: 8 }}>Training style</P>
        <P style={{ fontWeight: '600' }}>{res.persona_before === res.persona_after ? res.persona_after : `${res.persona_before} → ${res.persona_after}`}</P>
        {res.recommendations.length > 0 && <>
          <Divider />
          <P small muted>Try next time</P>
          {res.recommendations.slice(0, 3).map((r) => (
            <P key={r.exercise} style={{ marginTop: 4 }}>• <P style={{ fontWeight: '600' }}>{r.exercise}</P>
              <P small muted> (most people who do {r.because.join(' + ')} add it)</P></P>
          ))}
        </>}
      </Card>
      <Button label="Open workout" kind="secondary" icon="open-outline" onPress={() => router.push(`/workout/${w.workout_id}`)} />
      <Button label="Record another" icon="add" onPress={onDone} />
    </Screen>
  );
}
