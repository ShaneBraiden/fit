import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Switch, View } from 'react-native';
import { RouteMap, SpeedChart } from '../../components/charts';
import { Button, Card, Chip, Divider, ErrorState, H2, P, Pill, Row, Screen, Stat } from '../../components/ui';
import { fmt, UploadRequest, UploadResult, useApi } from '../../lib/api';
import { useSession } from '../../lib/session';
import { ACTIVITY_ICON, space, useTheme } from '../../lib/theme';

type Activity = UploadRequest['activity'];
type Kind = NonNullable<UploadRequest['kind']>;
type Fault = NonNullable<UploadRequest['faults']>[number];

const ACTIVITIES: Activity[] = ['Run', 'Walk', 'Cycle', 'Swim', 'Strength', 'HIIT', 'Yoga'];
const KINDS: Partial<Record<Activity, Kind[]>> = { Run: ['easy', 'intervals', 'tempo', 'long'], Strength: ['push', 'pull', 'legs'] };
const GPS = new Set<Activity>(['Run', 'Walk', 'Cycle']);
const FAULTS: { key: Fault; label: string; gps?: boolean }[] = [
  { key: 'hr_spike', label: 'Heart-rate strap spikes' }, { key: 'hr_flatline', label: 'Heart-rate sensor freezes' },
  { key: 'hr_dropout', label: 'Heart-rate sensor drops out' }, { key: 'calorie_mismatch', label: 'Calories over-reported' },
  { key: 'gps_teleport', label: 'GPS teleports', gps: true }, { key: 'car_speed', label: 'Recorded in a car', gps: true },
];
const DETECTORS: Record<string, string> = { rules: 'Domain rules', duplicates: 'Duplicate check', iqr: 'IQR fences', lof: 'LOF',
  iforest: 'Isolation Forest' };

export default function Record() {
  const t = useTheme();
  const api = useApi();
  const { userId } = useSession();
  const [activity, setActivity] = useState<Activity>('Run');
  const [kind, setKind] = useState<Kind>('easy');
  const [route, setRoute] = useState<'popular' | 'personal'>('popular');
  const [faults, setFaults] = useState<Fault[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<UploadResult | null>(null);

  const pick = (a: Activity) => {
    setActivity(a);
    setKind(KINDS[a]?.[0] ?? 'easy');
    setFaults((f) => (GPS.has(a) ? f : f.filter((x) => !FAULTS.find((y) => y.key === x)?.gps)));
  };
  const submit = async () => {
    if (!userId) return;
    setBusy(true); setError(null);
    try {
      const body: UploadRequest = { activity, kind, route, faults };
      setRes(await api<UploadResult>(`/api/users/${userId}/workouts`, body));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const d = res?.detail;
  const v = res?.verdict;

  return (
    <Screen title="Record a workout" subtitle="The watch recording is simulated; everything after upload is the real mining pipeline">
      <Card>
        <H2>Activity</H2>
        <Row wrap gap={space.sm}>
          {ACTIVITIES.map((a) => <Chip key={a} label={a} icon={ACTIVITY_ICON[a]} on={a === activity} onPress={() => pick(a)} />)}
        </Row>
        {KINDS[activity] && <>
          <Divider />
          <P muted small style={{ marginBottom: 6 }}>Session</P>
          <Row wrap gap={space.sm}>
            {KINDS[activity]!.map((k) => <Chip key={k} label={k} on={k === kind} onPress={() => setKind(k)} />)}
          </Row>
        </>}
        {GPS.has(activity) && <>
          <Divider />
          <P muted small style={{ marginBottom: 6 }}>Route</P>
          <Row wrap gap={space.sm}>
            <Chip label="Popular route near home" icon="people-outline" on={route === 'popular'} onPress={() => setRoute('popular')} />
            <Chip label="My own loop" icon="sync-outline" on={route === 'personal'} onPress={() => setRoute('personal')} />
          </Row>
        </>}
      </Card>

      <Card>
        <H2>Simulate a fault</H2>
        <P muted small style={{ marginBottom: space.sm }}>Inject a sensor problem or a spoof and watch the detectors catch it.</P>
        {FAULTS.filter((f) => !f.gps || GPS.has(activity)).map((f) => (
          <Row key={f.key} style={{ justifyContent: 'space-between', paddingVertical: 4 }}>
            <P>{f.label}</P>
            <Switch value={faults.includes(f.key)} trackColor={{ true: t.accent, false: t.axis }}
              onValueChange={(on) => setFaults((x) => (on ? [...x, f.key] : x.filter((y) => y !== f.key)))} />
          </Row>
        ))}
      </Card>

      <Button label={busy ? 'Uploading and mining…' : 'Record & upload'} icon="cloud-upload-outline" onPress={submit} busy={busy} />
      {error && <ErrorState message={error} onRetry={submit} />}

      {res && v && d && (
        <>
          <Card style={{ borderLeftWidth: 3, borderLeftColor: v.flagged ? t.critical : t.good }}>
            <Row style={{ justifyContent: 'space-between' }}>
              <H2>Upload verdict</H2>
              <Pill kind={v.flagged ? 'bad' : 'good'} label={v.flagged ? 'Flagged' : 'Looks genuine'} />
            </Row>
            {v.flagged
              ? v.reasons.map((r) => <P key={r} small style={{ marginTop: 4 }}>• {fmt.reason(r)}</P>)
              : <P muted small>Every detector agrees this recording is plausible for a {activity.toLowerCase()}.</P>}
            <Divider />
            <Row wrap gap={space.sm}>
              {Object.entries(v.detectors).map(([k, on]) => (
                <Row key={k} gap={4}>
                  <Ionicons name={on ? 'alert-circle' : 'checkmark-circle'} size={14} color={on ? t.critical : t.good} />
                  <P small muted>{DETECTORS[k] ?? k}</P>
                </Row>
              ))}
            </Row>
            {v.scores.iforest != null && (
              <P muted small style={{ marginTop: 6 }}>Isolation Forest score {v.scores.iforest.toFixed(2)} · LOF {v.scores.lof?.toFixed(2)}</P>
            )}
          </Card>

          <Card>
            <Row wrap gap={space.lg}>
              <Stat label="Duration" value={`${Math.round(res.workout.duration_min)} min`} />
              {res.workout.distance_km ? <Stat label="Distance" value={`${res.workout.distance_km.toFixed(2)} km`} /> : null}
              <Stat label="Avg HR" value={`${fmt.n(res.workout.avg_hr)} bpm`} />
              <Stat label="Calories" value={fmt.n(res.workout.calories)} />
            </Row>
            {d.lat && d.lon && d.segments && d.speed_kmh && <>
              <Divider />
              <P muted small>
                Detected session type: <P small style={{ fontWeight: '600' }}>{d.run_kind}</P>
                {d.route ? <> · matched route <P small style={{ fontWeight: '600' }}>{String(d.route.name)}</P></> : ' · no popular route matched'}
              </P>
              <View style={{ marginTop: space.sm }}><SpeedChart speed={d.speed_kmh} segments={d.segments} /></View>
              <View style={{ marginTop: space.md }}><RouteMap lat={d.lat} lon={d.lon} segments={d.segments} height={200} /></View>
            </>}
          </Card>

          <Card>
            <H2>What changed</H2>
            <P small muted>Fitness level (classifier)</P>
            <P style={{ fontWeight: '600' }}>{res.level_before} → {res.level_after}</P>
            <P small muted style={{ marginTop: 8 }}>Persona (nearest cluster centre)</P>
            <P style={{ fontWeight: '600' }}>{res.persona_before} → {res.persona_after}</P>
            {res.recommendations.length > 0 && <>
              <Divider />
              <P small muted>Next, people like you also do</P>
              {res.recommendations.slice(0, 3).map((r) => (
                <P key={r.exercise} style={{ marginTop: 4 }}>• <P style={{ fontWeight: '600' }}>{r.exercise}</P>
                  <P small muted> ({fmt.pct(r.confidence)} of the time after {r.because.join(' + ')})</P></P>
              ))}
            </>}
          </Card>
          <Button label="Open workout" kind="secondary" icon="open-outline" onPress={() => router.push(`/workout/${res.workout.workout_id}`)} />
        </>
      )}
    </Screen>
  );
}
