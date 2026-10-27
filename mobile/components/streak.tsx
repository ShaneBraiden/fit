import { Ionicons } from '@expo/vector-icons';
import { Text, View } from 'react-native';
import { Streak, WEEKDAYS } from '../lib/api';
import { space, useTheme } from '../lib/theme';
import { P, Row } from './ui';

const FLAME = '#f59e0b';

/** Flame, streak number and this week's seven days. */
export function StreakBadge({ s }: { s: Streak }) {
  const t = useTheme();
  const lit = s.current > 0;
  return (
    <View>
      <Row gap={space.md}>
        <Ionicons name={lit ? 'flame' : 'flame-outline'} size={46} color={lit ? FLAME : t.muted} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 30, fontWeight: '800', color: t.text }}>{s.current}<Text style={{ fontSize: 15, fontWeight: '500', color: t.text2 }}> day streak</Text></Text>
          <P muted small>{s.today_done ? 'Done for today. See you tomorrow!' : s.at_risk ? 'Train today to keep your streak going.'
            : lit ? 'Rest day: your streak is safe.' : 'Record a workout to start a streak.'}</P>
        </View>
      </Row>
      <Row style={{ justifyContent: 'space-between', marginTop: space.md }}>
        {s.week.map((d, i) => {
          const done = d.status === 'done', rest = d.status === 'rest';
          return (
            <View key={d.date} style={{ alignItems: 'center', gap: 3 }} accessibilityLabel={`${WEEKDAYS[i]}: ${d.status}`}>
              <View style={{ width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center',
                backgroundColor: done ? FLAME : rest ? 'transparent' : t.surface2,
                borderWidth: 2, borderStyle: rest ? 'dashed' : 'solid',
                borderColor: d.status === 'today' ? FLAME : rest ? t.axis : 'transparent', opacity: d.status === 'missed' ? 0.6 : 1 }}>
                {done ? <Ionicons name="checkmark" size={18} color="#3a2400" /> : rest ? <Text style={{ color: t.muted, fontWeight: '700' }}>z</Text> : null}
              </View>
              <Text style={{ fontSize: 11, color: t.muted }}>{WEEKDAYS[i][0]}</Text>
            </View>
          );
        })}
      </Row>
    </View>
  );
}
