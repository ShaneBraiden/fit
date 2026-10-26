import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { Button, Card, Chip, Divider, Field, H2, P, Pill, Row, Screen, Skeleton } from '../../components/ui';
import { Account, Alert, fmt, useApi, useFetch } from '../../lib/api';
import { useSession } from '../../lib/session';
import { space, useTheme } from '../../lib/theme';

export default function ProfileTab() {
  const t = useTheme();
  const api = useApi();
  const { account, setAccount, signOut, token, apiUrl, setApiUrl } = useSession();
  const me = useFetch<Account>('/api/me');
  const alerts = useFetch<Alert[]>('/api/me/alerts');
  const [edit, setEdit] = useState(false);
  const [url, setUrl] = useState(apiUrl);
  const a = me.data ?? account;
  useEffect(() => { if (me.data) setAccount(me.data); }, [me.data, setAccount]);

  const logout = async () => {
    try { await api('/api/auth/logout', undefined, 'POST'); } catch { /* signing out locally is enough */ }
    signOut();
    router.replace('/');
  };

  const rows: [string, string][] = a ? [
    ['Email', a.email], ['Sex', a.gender === 'F' ? 'Female' : 'Male'], ['Age', String(a.age)],
    ['Height', `${a.height_cm} cm`], ['Weight', `${a.weight_kg} kg`], ['BMI', String(a.bmi)],
    ['Resting HR', a.resting_hr ? `${a.resting_hr} bpm` : 'not set'], ['VO2max', a.vo2max ? String(a.vo2max) : 'estimated'],
    ['Member since', fmt.date(a.signup_date)],
  ] : [];

  return (
    <Screen title={a ? a.name : 'Profile'} subtitle="Your details and data checks" refreshing={me.loading}
      onRefresh={() => { me.reload(); alerts.reload(); }}>
      {!a ? <Skeleton lines={6} /> : edit ? <EditCard account={a} onDone={(next) => { if (next) setAccount(next); setEdit(false); me.reload(); }} /> : (
        <Card>
          <H2 right={<Chip label="Edit" icon="create-outline" onPress={() => setEdit(true)} />}>Your details</H2>
          {rows.map(([k, v], i) => (
            <View key={k}>
              {i > 0 && <Divider />}
              <Row style={{ justifyContent: 'space-between' }}><P muted>{k}</P><P>{v}</P></Row>
            </View>
          ))}
        </Card>
      )}

      <Card>
        <H2 right={alerts.data ? <Pill kind={alerts.data.length ? 'bad' : 'good'} label={alerts.data.length ? `${alerts.data.length} found` : 'All clear'} /> : undefined}>
          Data checks
        </H2>
        <P muted small style={{ marginBottom: space.sm }}>Every workout is checked for GPS glitches, impossible speeds and other errors. Flagged ones don't count towards your stats.</P>
        {!alerts.data ? <Skeleton lines={2} /> : alerts.data.length === 0 ? <P muted>Nothing unusual in your workouts.</P>
          : alerts.data.map((x, i) => (
            <View key={x.workout_id}>
              {i > 0 && <Divider />}
              <Row gap={space.md}>
                <Ionicons name="pulse-outline" size={18} color={t.critical} />
                <View style={{ flex: 1 }}>
                  <P style={{ fontWeight: '600' }}>{x.title}</P>
                  <P muted small>{fmt.reason(x.detail)} · {fmt.date(x.start_time)}</P>
                </View>
                <Ionicons name="chevron-forward" size={16} color={t.muted} onPress={() => router.push(`/workout/${x.workout_id}`)} />
              </Row>
            </View>
          ))}
      </Card>

      <Card>
        <H2>Server</H2>
        <Field label="Server address" value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" />
        <View style={{ marginTop: space.sm }}>
          <Button label="Save server address" kind="secondary" icon="save-outline" onPress={() => setApiUrl(url)} />
        </View>
      </Card>

      {token && <Button label="Sign out" kind="secondary" icon="log-out-outline" onPress={logout} />}
    </Screen>
  );
}

function EditCard({ account, onDone }: { account: Account; onDone: (a: Account | null) => void }) {
  const t = useTheme();
  const api = useApi();
  const str = (v: number | null | undefined) => (v == null ? '' : String(v));
  const [name, setName] = useState(account.name);
  const [age, setAge] = useState(str(account.age));
  const [height, setHeight] = useState(str(account.height_cm));
  const [weight, setWeight] = useState(str(account.weight_kg));
  const [rhr, setRhr] = useState(str(account.resting_hr));
  const [vo2, setVo2] = useState(str(account.vo2max));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const num = (s: string) => (s.trim() === '' ? null : Number(s.replace(',', '.')));
  const save = async () => {
    setBusy(true); setError(null);
    try {
      onDone(await api<Account>('/api/me', { name: name.trim(), age: num(age), height_cm: num(height), weight_kg: num(weight),
        resting_hr: num(rhr), vo2max: num(vo2) }, 'PATCH'));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <H2>Edit your details</H2>
      <View style={{ gap: space.md }}>
        <Field label="Name" value={name} onChangeText={setName} />
        <Row gap={space.md} wrap>
          <Field label="Age" value={age} onChangeText={setAge} keyboardType="number-pad" />
          <Field label="Height (cm)" value={height} onChangeText={setHeight} keyboardType="decimal-pad" />
          <Field label="Weight (kg)" value={weight} onChangeText={setWeight} keyboardType="decimal-pad" />
        </Row>
        <Row gap={space.md} wrap>
          <Field label="Resting heart rate" value={rhr} onChangeText={setRhr} keyboardType="number-pad" hint="Leave empty if unknown" />
          <Field label="VO2max" value={vo2} onChangeText={setVo2} keyboardType="decimal-pad" hint="Leave empty to estimate it" />
        </Row>
        {error && <P style={{ color: t.criticalInk }}>{error}</P>}
        <Row gap={space.sm}>
          <View style={{ flex: 1 }}><Button label="Cancel" kind="secondary" onPress={() => onDone(null)} /></View>
          <View style={{ flex: 1 }}><Button label="Save" icon="checkmark" onPress={save} busy={busy} /></View>
        </Row>
      </View>
    </Card>
  );
}
