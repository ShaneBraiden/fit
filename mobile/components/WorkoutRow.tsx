import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { fmt, WorkoutItem } from '../lib/api';
import { ACTIVITY_ICON, space, useTheme } from '../lib/theme';
import { P, Pill } from './ui';

export default function WorkoutRow({ w }: { w: WorkoutItem }) {
  const t = useTheme();
  return (
    <Pressable onPress={() => router.push(`/workout/${w.workout_id}`)} accessibilityRole="button"
      style={({ pressed }) => [{ flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 7 }, pressed && { opacity: 0.6 }]}>
      <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: t.accentWash, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={(ACTIVITY_ICON[w.activity] ?? 'fitness-outline') as never} size={18} color={t.accentInk} />
      </View>
      <View style={{ flex: 1 }}>
        <P style={{ fontWeight: '600' }}>{w.title}</P>
        <P muted small>{fmt.date(w.start_time)} · {Math.round(w.duration_min)} min{w.distance_km ? ` · ${w.distance_km.toFixed(1)} km` : ''}
          {w.route_name ? ` · ${w.route_name}` : ''}</P>
      </View>
      {w.flagged ? <Pill kind="bad" label="Flagged" /> : <Ionicons name="chevron-forward" size={16} color={t.muted} />}
    </Pressable>
  );
}
