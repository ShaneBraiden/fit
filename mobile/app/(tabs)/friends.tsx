import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, Share, View } from 'react-native';
import { Button, Card, Divider, ErrorState, Field, H2, P, Pill, Row, Screen, Skeleton } from '../../components/ui';
import { fmt, Friends, FriendSummary, todayIso, useApi, useFetch } from '../../lib/api';
import { useFocusRefresh } from '../../lib/focus';
import { space, useTheme } from '../../lib/theme';

const showCode = (c: string) => `${c.slice(0, 4)}-${c.slice(4)}`;

export default function FriendsTab() {
  const t = useTheme();
  const api = useApi();
  const r = useFetch<Friends>(`/api/me/friends?today=${todayIso()}`);
  useFocusRefresh(useCallback(() => r.reload(), [r.reload]));
  const [handle, setHandle] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const d = r.data;

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); r.reload(); } catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }); } finally { setBusy(false); }
  };
  const add = () => act(async () => {
    setMsg(null);
    const res = await api<{ status: string }>('/api/me/friends', { handle: handle.trim() });
    setMsg({ ok: true, text: res.status === 'accepted' ? "They'd already asked you, so you're now friends." : "Request sent. You'll see their numbers once they accept." });
    setHandle('');
  });
  const byId = new Map<number, FriendSummary>(d ? [[d.me.user_id, d.me], ...d.friends.map((f) => [f.user_id, f] as const)] : []);

  return (
    <Screen title="Friends" subtitle="Streaks, weekly totals and muscles. Never single workouts or GPS." refreshing={r.loading} onRefresh={r.reload}>
      {r.error ? <ErrorState message={r.error} onRetry={r.reload} /> : !d ? <><Skeleton /><Skeleton lines={4} /></> : <>
        <Card>
          <H2>Add a friend</H2>
          <Field label="Their email or friend code" value={handle} onChangeText={setHandle} autoCapitalize="none" autoCorrect={false}
            placeholder="friend@example.com or ABCD-EFGH" />
          <View style={{ marginTop: space.sm }}><Button label="Send request" icon="person-add-outline" onPress={add} busy={busy} disabled={handle.trim().length < 3} /></View>
          {msg && <P small style={{ marginTop: 6, color: msg.ok ? t.text2 : t.criticalInk }}>{msg.text}</P>}
          <Divider />
          <Row style={{ justifyContent: 'space-between' }}>
            <View><P small muted>Your friend code</P><P style={{ fontSize: 20, fontWeight: '700', letterSpacing: 1.5 }}>{showCode(d.code)}</P></View>
            <Button label="Share" kind="secondary" icon="share-outline"
              onPress={() => Share.share({ message: `Add me on FitMine: my friend code is ${showCode(d.code)}` }).catch(() => undefined)} />
          </Row>
        </Card>

        {d.incoming.length > 0 && (
          <Card>
            <H2 right={<Pill kind="info" label={`${d.incoming.length}`} />}>Requests for you</H2>
            {d.incoming.map((x, i) => (
              <View key={x.user_id}>
                {i > 0 && <Divider />}
                <Row gap={space.sm}>
                  <P style={{ flex: 1, fontWeight: '600' }}>{x.name}</P>
                  <Button label="Accept" onPress={() => act(() => api(`/api/me/friends/${x.user_id}/accept`, undefined, 'POST'))} />
                  <Button label="Decline" kind="secondary" onPress={() => act(() => api(`/api/me/friends/${x.user_id}`, undefined, 'DELETE'))} />
                </Row>
              </View>
            ))}
          </Card>
        )}

        <Card>
          <H2>This week's leaderboard</H2>
          <P muted small style={{ marginBottom: space.sm }}>Minutes trained since Monday.</P>
          {d.leaderboard.length === 1 && <P muted small>Add a friend to compete. Right now it's just you.</P>}
          {d.leaderboard.map((id, i) => {
            const f = byId.get(id)!;
            const me = id === d.me.user_id;
            return (
              <Pressable key={id} disabled={me} onPress={() => router.push(`/friend/${id}`)}
                style={{ flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 8, paddingHorizontal: 6, borderRadius: 10,
                  backgroundColor: me ? t.accentWash : 'transparent' }}>
                <P style={{ width: 20, fontWeight: '800', color: t.muted }}>{i + 1}</P>
                <View style={{ flex: 1 }}>
                  <P style={{ fontWeight: '700' }}>{me ? 'You' : f.name}</P>
                  <P muted small>{f.week_sessions} workout{f.week_sessions === 1 ? '' : 's'}</P>
                </View>
                <Row gap={2}><Ionicons name="flame" size={15} color={f.streak ? '#f59e0b' : t.muted} /><P small>{f.streak}</P></Row>
                <P style={{ fontWeight: '700', minWidth: 64, textAlign: 'right' }}>{fmt.n(f.week_minutes)} min</P>
              </Pressable>
            );
          })}
        </Card>

        <Card>
          <H2>Your friends ({d.friends.length})</H2>
          {d.friends.length === 0 && <P muted small>No friends yet. Share your code: {showCode(d.code)}</P>}
          {d.friends.map((f, i) => (
            <Pressable key={f.user_id} onPress={() => router.push(`/friend/${f.user_id}`)} accessibilityRole="button">
              {i > 0 && <Divider />}
              <Row gap={space.md}>
                <View style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: t.accentWash, alignItems: 'center', justifyContent: 'center' }}>
                  <P style={{ fontWeight: '700', color: t.accentInk }}>{f.name[0]?.toUpperCase()}</P>
                </View>
                <View style={{ flex: 1 }}>
                  <P style={{ fontWeight: '600' }}>{f.name}</P>
                  <P muted small>{f.streak}-day streak · {fmt.n(f.four_week_minutes)} min in 4 weeks</P>
                </View>
                {f.today_done ? <Pill kind="good" label="Today" /> : <Ionicons name="chevron-forward" size={16} color={t.muted} />}
              </Row>
            </Pressable>
          ))}
        </Card>

        {d.outgoing.length > 0 && (
          <Card>
            <H2>Sent requests</H2>
            {d.outgoing.map((x) => (
              <Row key={x.user_id} gap={space.sm} style={{ paddingVertical: 4 }}>
                <P style={{ flex: 1 }}>{x.name} <P small muted>· waiting</P></P>
                <Button label="Cancel" kind="secondary" onPress={() => act(() => api(`/api/me/friends/${x.user_id}`, undefined, 'DELETE'))} />
              </Row>
            ))}
          </Card>
        )}
      </>}
    </Screen>
  );
}
