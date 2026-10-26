import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { TextInput, View } from 'react-native';
import { Button, Card, Divider, ErrorState, H2, P, Pill, Row, Screen, Skeleton } from '../../components/ui';
import { Alert, fmt, Profile, useFetch } from '../../lib/api';
import { useSession } from '../../lib/session';
import { radius, space, useTheme } from '../../lib/theme';

export default function ProfileTab() {
  const t = useTheme();
  const { userId, setUserId, apiUrl, setApiUrl } = useSession();
  const prof = useFetch<Profile>(userId ? `/api/users/${userId}/profile` : null);
  const alerts = useFetch<Alert[]>(userId ? `/api/users/${userId}/alerts` : null);
  const [url, setUrl] = useState(apiUrl);
  const u = prof.data?.user;

  const rows: [string, string][] = u ? [
    ['User id', `#${u.user_id}`], ['Gender', String(u.gender)], ['Age', String(u.age)],
    ['Height', `${u.height_cm} cm`], ['Weight', `${u.weight_kg} kg`], ['BMI', String(u.bmi)],
    ['Resting HR', `${u.resting_hr} bpm`], ['VO2max', String(u.vo2max)], ['Home zone', String(u.home_zone)],
    ['Device', String(u.device)],
  ] : [];

  return (
    <Screen title={u ? String(u.name) : 'Profile'} subtitle="Profile data and the checks run on it"
      refreshing={prof.loading} onRefresh={() => { prof.reload(); alerts.reload(); }}>
      {prof.error ? <ErrorState message={prof.error} onRetry={prof.reload} /> : !u ? <Skeleton lines={6} /> : (
        <Card>
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
        <P muted small style={{ marginBottom: space.sm }}>Outlier detection on your profile and on every uploaded recording.</P>
        {!alerts.data ? <Skeleton lines={2} /> : alerts.data.length === 0 ? <P muted>Nothing suspicious in your data.</P>
          : alerts.data.map((a, i) => (
            <View key={i}>
              {i > 0 && <Divider />}
              <Row gap={space.md}>
                <Ionicons name={a.kind === 'profile' ? 'person-outline' : 'pulse-outline'} size={18} color={t.critical} />
                <View style={{ flex: 1 }}>
                  <P style={{ fontWeight: '600' }}>{a.title}</P>
                  <P muted small>{fmt.reason(a.detail)}{a.start_time ? ` · ${fmt.date(a.start_time)}` : ''}</P>
                </View>
                {a.workout_id ? <Ionicons name="chevron-forward" size={16} color={t.muted}
                  onPress={() => router.push(`/workout/${a.workout_id}`)} /> : null}
              </Row>
            </View>
          ))}
      </Card>

      <Card>
        <H2>Server</H2>
        <TextInput value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url"
          style={{ borderWidth: 1, borderColor: t.border, borderRadius: radius.md, paddingHorizontal: 12, paddingVertical: 10,
            color: t.text, backgroundColor: t.surface2, marginBottom: space.sm }} />
        <Button label="Save server address" kind="secondary" icon="save-outline" onPress={() => setApiUrl(url)} />
      </Card>

      <Button label="Switch user" kind="secondary" icon="swap-horizontal" onPress={() => { setUserId(null); router.replace('/'); }} />
    </Screen>
  );
}
