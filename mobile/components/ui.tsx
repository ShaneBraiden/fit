import { Ionicons } from '@expo/vector-icons';
import { ReactNode } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextStyle, View, ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { radius, space, type, useTheme } from '../lib/theme';

export function Screen({ children, refreshing, onRefresh, title, subtitle, right }: {
  children: ReactNode; refreshing?: boolean; onRefresh?: () => void; title?: string; subtitle?: string; right?: ReactNode;
}) {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <ScrollView style={{ flex: 1, backgroundColor: t.page }}
      contentContainerStyle={{ padding: space.lg, paddingTop: insets.top + space.md, paddingBottom: space.xl * 2, gap: space.md }}
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={t.accent} /> : undefined}>
      {title && (
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: space.xs }}>
          <View style={{ flex: 1 }}>
            <Text style={[type.title, { color: t.text }]}>{title}</Text>
            {subtitle && <Text style={[type.small, { color: t.text2, marginTop: 2 }]}>{subtitle}</Text>}
          </View>
          {right}
        </View>
      )}
      {children}
    </ScrollView>
  );
}

export function Card({ children, style, onPress }: { children: ReactNode; style?: ViewStyle; onPress?: () => void }) {
  const t = useTheme();
  const s = [styles.card, { backgroundColor: t.surface, borderColor: t.border }, style];
  if (onPress) {
    return <Pressable onPress={onPress} style={({ pressed }) => [...s, pressed && { opacity: 0.75 }]}>{children}</Pressable>;
  }
  return <View style={s}>{children}</View>;
}

export function H2({ children, right }: { children: ReactNode; right?: ReactNode }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.sm }}>
      <Text style={[type.h2, { color: t.text, flex: 1 }]}>{children}</Text>
      {right}
    </View>
  );
}

export function P({ children, muted, style, small }: { children: ReactNode; muted?: boolean; style?: TextStyle; small?: boolean }) {
  const t = useTheme();
  return <Text style={[small ? type.small : type.body, { color: muted ? t.text2 : t.text, lineHeight: small ? 17 : 20 }, style]}>{children}</Text>;
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  const t = useTheme();
  return (
    <View style={{ flex: 1, minWidth: 130 }}>
      <Text style={[type.small, { color: t.text2 }]}>{label}</Text>
      <Text style={{ fontSize: 22, fontWeight: '600', color: t.text, marginTop: 2 }}>{value}</Text>
      {sub && <Text style={[type.small, { color: t.muted }]}>{sub}</Text>}
    </View>
  );
}

export function Row({ children, gap = space.md, wrap, style }: { children: ReactNode; gap?: number; wrap?: boolean; style?: ViewStyle }) {
  return <View style={[{ flexDirection: 'row', gap, alignItems: 'center' }, wrap && { flexWrap: 'wrap' }, style]}>{children}</View>;
}

/** Status pill: icon + label, never colour alone. */
export function Pill({ kind, label }: { kind: 'good' | 'bad' | 'neutral' | 'info'; label: string }) {
  const t = useTheme();
  const map = {
    good: { icon: 'checkmark-circle', color: t.good, ink: t.goodInk },
    bad: { icon: 'alert-circle', color: t.critical, ink: t.criticalInk },
    neutral: { icon: 'ellipse-outline', color: t.muted, ink: t.text2 },
    info: { icon: 'information-circle', color: t.accent, ink: t.accentInk },
  }[kind];
  return (
    <View style={[styles.pill, { borderColor: t.border }]}>
      <Ionicons name={map.icon as never} size={14} color={map.color} />
      <Text style={[type.small, { color: map.ink, fontWeight: '600' }]}>{label}</Text>
    </View>
  );
}

export function Chip({ label, on, onPress, icon }: { label: string; on?: boolean; onPress?: () => void; icon?: string }) {
  const t = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!on }}
      style={[styles.chip, { borderColor: on ? t.accent : t.border, backgroundColor: on ? t.accentWash : t.surface }]}>
      {icon && <Ionicons name={icon as never} size={15} color={on ? t.accentInk : t.text2} />}
      <Text style={[type.small, { color: on ? t.accentInk : t.text2, fontWeight: on ? '600' : '400' }]}>{label}</Text>
    </Pressable>
  );
}

export function Button({ label, onPress, kind = 'primary', disabled, busy, icon }: {
  label: string; onPress: () => void; kind?: 'primary' | 'secondary'; disabled?: boolean; busy?: boolean; icon?: string;
}) {
  const t = useTheme();
  const primary = kind === 'primary';
  return (
    <Pressable onPress={onPress} disabled={disabled || busy} accessibilityRole="button"
      style={({ pressed }) => [styles.button, { backgroundColor: primary ? t.accent : t.surface, borderColor: primary ? t.accent : t.border,
        opacity: disabled ? 0.5 : pressed ? 0.8 : 1 }]}>
      {busy ? <ActivityIndicator color={primary ? t.onAccent : t.accent} />
        : icon ? <Ionicons name={icon as never} size={17} color={primary ? t.onAccent : t.text} /> : null}
      <Text style={{ color: primary ? t.onAccent : t.text, fontWeight: '600', fontSize: 15 }}>{label}</Text>
    </Pressable>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  const t = useTheme();
  return (
    <Card>
      {Array.from({ length: lines }).map((_, i) => (
        <View key={i} style={{ height: i === 0 ? 18 : 12, width: `${i === 0 ? 45 : 90 - i * 12}%`, backgroundColor: t.surface2,
          borderRadius: 6, marginBottom: 10 }} />
      ))}
    </Card>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useTheme();
  return (
    <Card style={{ borderLeftWidth: 3, borderLeftColor: t.critical }}>
      <Row gap={space.sm}><Ionicons name="cloud-offline-outline" size={18} color={t.critical} /><P style={{ fontWeight: '600' }}>Something went wrong</P></Row>
      <P muted small style={{ marginTop: 6 }}>{message}</P>
      {onRetry && <View style={{ marginTop: space.md }}><Button label="Try again" kind="secondary" onPress={onRetry} icon="refresh" /></View>}
    </Card>
  );
}

export function EmptyState({ icon, title, body }: { icon: string; title: string; body?: string }) {
  const t = useTheme();
  return (
    <Card style={{ alignItems: 'center', paddingVertical: space.xl }}>
      <Ionicons name={icon as never} size={30} color={t.muted} />
      <P style={{ fontWeight: '600', marginTop: space.sm }}>{title}</P>
      {body && <P muted small style={{ textAlign: 'center', marginTop: 4 }}>{body}</P>}
    </Card>
  );
}

export function Divider() {
  const t = useTheme();
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: t.grid, marginVertical: space.sm }} />;
}

const styles = StyleSheet.create({
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radius.lg, padding: space.lg },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: StyleSheet.hairlineWidth, borderRadius: radius.pill,
    paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start' },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 5, borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 12,
    paddingVertical: 7 },
  button: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderRadius: radius.md,
    paddingVertical: 13, paddingHorizontal: 16 },
});
