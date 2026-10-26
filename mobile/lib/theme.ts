import { useColorScheme } from 'react-native';

/* Same validated palette as the web dashboard: categorical slots in fixed order,
   one-hue blue ramp for ordered values (fitness levels), reserved status colours. */
const light = {
  dark: false,
  page: '#f6f6f3', surface: '#fcfcfb', surface2: '#f1f0ec', border: 'rgba(11,11,11,0.1)',
  text: '#0b0b0b', text2: '#52514e', muted: '#7a7873', grid: '#e1e0d9', axis: '#c3c2b7',
  accent: '#2a78d6', accentInk: '#1c5cab', accentWash: 'rgba(42,120,214,0.1)', onAccent: '#ffffff',
  series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
  seq: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'],
  good: '#0ca30c', goodInk: '#006300', warning: '#fab219', critical: '#d03b3b', criticalInk: '#b42323',
};
const dark: typeof light = {
  dark: true,
  page: '#0d0d0d', surface: '#1a1a19', surface2: '#232321', border: 'rgba(255,255,255,0.1)',
  text: '#f0efec', text2: '#c3c2b7', muted: '#8f8d87', grid: '#2c2c2a', axis: '#383835',
  accent: '#3987e5', accentInk: '#86b6ef', accentWash: 'rgba(57,135,229,0.16)', onAccent: '#ffffff',
  series: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
  seq: ['#104281', '#184f95', '#1c5cab', '#256abf', '#3987e5', '#6da7ec', '#b7d3f6'],
  good: '#0ca30c', goodInk: '#0ca30c', warning: '#fab219', critical: '#d03b3b', criticalInk: '#e66767',
};
export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? dark : light;
}

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };
export const radius = { sm: 8, md: 12, lg: 16, pill: 999 };
export const type = {
  hero: { fontSize: 30, fontWeight: '700' as const },
  title: { fontSize: 20, fontWeight: '700' as const },
  h2: { fontSize: 16, fontWeight: '600' as const },
  body: { fontSize: 14 },
  small: { fontSize: 12 },
};

export const LEVELS = ['Beginner', 'Intermediate', 'Advanced', 'Elite'];
export function levelColor(t: Theme, level: string): string {
  return t.seq[[1, 3, 4, 6][LEVELS.indexOf(level)] ?? 3];
}
export const CATEGORY_ORDER = ['Cardio', 'Strength', 'Mind-Body'];
export const PHASES = ['warmup', 'steady', 'fast', 'recovery', 'cooldown', 'stop'];
export function phaseColor(t: Theme, phase: string): string {
  if (phase === 'stop') return t.muted;
  return t.series[[0, 1, 2, 3, 6][PHASES.indexOf(phase)] ?? 0];
}
export const ACTIVITY_ICON: Record<string, string> = {
  Run: 'walk-outline', Walk: 'footsteps-outline', Cycle: 'bicycle-outline', Swim: 'water-outline',
  Strength: 'barbell-outline', HIIT: 'flash-outline', Yoga: 'leaf-outline',
};
