import { Ionicons } from '@expo/vector-icons';
import { Redirect, router } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, Text, TextInput, View } from 'react-native';
import { Card, Chip, ErrorState, H2, P, Pill, Row, Screen, Skeleton } from '../components/ui';
import { useFetch, UserSummary } from '../lib/api';
import { useSession } from '../lib/session';
import { levelColor, radius, space, type, useTheme } from '../lib/theme';

/** Sign-in for the demo: pick one of the dataset's users. No passwords; everything is synthetic. */
export default function Welcome() {
  const t = useTheme();
  const { ready, userId, setUserId, apiUrl, setApiUrl } = useSession();
  const [query, setQuery] = useState('');
  const [url, setUrl] = useState(apiUrl);
  const path = query.trim() ? `/api/users?query=${encodeURIComponent(query.trim())}&limit=40` : '/api/users?featured=true&limit=40';
  const users = useFetch<UserSummary[]>(ready ? path : null);
  const groups = useMemo(() => {
    const g: Record<string, UserSummary[]> = {};
    for (const u of users.data ?? []) (g[u.flagged ? 'Flagged profiles' : u.persona] ??= []).push(u);
    return Object.entries(g);
  }, [users.data]);

  if (!ready) return <View style={{ flex: 1, backgroundColor: t.page, justifyContent: 'center' }}><ActivityIndicator color={t.accent} /></View>;
  if (userId != null) return <Redirect href="/(tabs)/today" />;

  return (
    <Screen>
      <View style={{ alignItems: 'center', marginTop: space.lg, marginBottom: space.md }}>
        <View style={{ width: 56, height: 56, borderRadius: 16, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="pulse" size={30} color="#fff" />
        </View>
        <Text style={[type.hero, { color: t.text, marginTop: space.md }]}>FitMine</Text>
        <P muted style={{ textAlign: 'center', marginTop: 4 }}>Your workouts, mined: fitness level, persona, exercise suggestions, routes and sensor checks.</P>
      </View>

      <Card>
        <H2>Server</H2>
        <Row gap={space.sm}>
          <TextInput value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url"
            onSubmitEditing={() => setApiUrl(url)}
            style={{ flex: 1, borderWidth: 1, borderColor: t.border, borderRadius: radius.md, paddingHorizontal: 12, paddingVertical: 10,
              color: t.text, backgroundColor: t.surface2 }} />
          <Chip label="Use" on onPress={() => setApiUrl(url)} />
        </Row>
        <P muted small style={{ marginTop: 6 }}>The laptop running <Text style={{ fontFamily: 'monospace' }}>uvicorn</Text>, on the same Wi-Fi.</P>
      </Card>

      <TextInput value={query} onChangeText={setQuery} placeholder="Search users by name, id or persona" placeholderTextColor={t.muted}
        style={{ borderWidth: 1, borderColor: t.border, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 11, color: t.text,
          backgroundColor: t.surface }} />

      {users.error ? <ErrorState message={users.error} onRetry={users.reload} /> : !users.data ? <Skeleton lines={5} /> :
        users.data.length === 0 ? <P muted>No users match "{query}".</P> :
          groups.map(([group, list]) => (
            <Card key={group}>
              <H2>{group}</H2>
              {list.map((u, i) => (
                <View key={u.user_id}>
                  {i > 0 && <View style={{ height: 1, backgroundColor: t.grid, marginVertical: 8 }} />}
                  <Pressable onPress={() => { setUserId(u.user_id); router.replace('/(tabs)/today'); }}
                    style={({ pressed }) => [{ flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 2 },
                      pressed && { opacity: 0.6 }]}>
                    <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: levelColor(t, u.level) }} />
                    <View style={{ flex: 1 }}>
                      <Text style={[type.body, { color: t.text, fontWeight: '600' }]}>{u.name}</Text>
                      <P muted small>#{u.user_id} · {u.age} · {u.home_zone} · {u.level}{u.level_source === 'predicted' ? ' (predicted)' : ''}</P>
                    </View>
                    {u.flagged ? <Pill kind="bad" label="Flagged" /> : null}
                    <Ionicons name="chevron-forward" size={18} color={t.muted} />
                  </Pressable>
                </View>
              ))}
            </Card>
          ))}
      {users.loading && users.data && <ActivityIndicator color={t.accent} />}
    </Screen>
  );
}
