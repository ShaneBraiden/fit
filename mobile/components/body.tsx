/* Front and back body figures with each muscle coloured by its sets per week (same shapes as the web app). */
import Svg, { Ellipse, Rect, Text as SvgText } from 'react-native-svg';
import { View } from 'react-native';
import { Theme, useTheme } from '../lib/theme';
import { Legend } from './charts';

type Shape = { e: [number, number, number, number] } | { r: [number, number, number, number, number] };
const mirror = (cx: number, cy: number, rx: number, ry: number): Shape[] => [{ e: [cx, cy, rx, ry] }, { e: [200 - cx, cy, rx, ry] }];

/** Muscle shapes on a 200 x 400 figure; the back view is drawn 220 to the right. */
const FRONT: Record<string, Shape[]> = {
  Shoulders: mirror(58, 80, 14, 12),
  Chest: mirror(86, 97, 17, 13),
  Biceps: mirror(49, 114, 9, 20),
  Core: [{ r: [84, 116, 32, 70, 10] }],
  Quads: mirror(84, 242, 13, 38),
  Calves: mirror(84, 336, 8, 26),
};
const BACK: Record<string, Shape[]> = {
  Shoulders: mirror(58, 80, 14, 12),
  Back: [{ r: [76, 70, 48, 30, 12] }, ...mirror(87, 122, 14, 30)],
  Triceps: mirror(49, 112, 9, 20),
  Glutes: mirror(87, 208, 15, 14),
  Hamstrings: mirror(84, 256, 13, 32),
  Calves: mirror(84, 332, 10, 26),
};
const SILHOUETTE: Shape[] = [
  { e: [100, 34, 19, 21] }, { r: [92, 52, 16, 14, 4] }, { r: [64, 62, 72, 142, 24] },
  { r: [36, 70, 24, 86, 12] }, { r: [140, 70, 24, 86, 12] }, { r: [33, 152, 20, 78, 10] }, { r: [147, 152, 20, 78, 10] },
  { r: [68, 194, 31, 112, 15] }, { r: [101, 194, 31, 112, 15] }, { r: [71, 300, 26, 92, 12] }, { r: [103, 300, 26, 92, 12] },
];

/** Sets per week -> fill colour: grey when untrained, then the blue ramp up to the top of the target. */
export function setsColor(t: Theme, sets: number, top = 20): string {
  if (sets <= 0) return t.axis;
  const x = 0.15 + 0.85 * Math.min(1, sets / top);
  return t.seq[Math.round(x * (t.seq.length - 1))];
}

function draw(s: Shape, dx: number, props: Record<string, unknown>, key: string) {
  if ('e' in s) return <Ellipse key={key} cx={s.e[0] + dx} cy={s.e[1]} rx={s.e[2]} ry={s.e[3]} {...props} />;
  return <Rect key={key} x={s.r[0] + dx} y={s.r[1]} width={s.r[2]} height={s.r[3]} rx={s.r[4]} {...props} />;
}

export function BodyMap({ sets, selected, onSelect, top = 20, height = 300 }: {
  sets: Record<string, number>; selected?: string | null; onSelect?: (m: string) => void; top?: number; height?: number;
}) {
  const t = useTheme();
  const muscle = (view: Record<string, Shape[]>, dx: number) => Object.entries(view).flatMap(([m, shapes]) => shapes.map((s, i) => draw(s, dx, {
    fill: setsColor(t, sets[m] ?? 0, top), stroke: selected === m ? t.text : t.surface, strokeWidth: selected === m ? 3 : 1.5,
    onPress: onSelect ? () => onSelect(m) : undefined,
  }, `${m}${dx}${i}`)));
  return (
    <View accessibilityRole="image" accessibilityLabel="Sets per muscle, front and back">
      <Svg width="100%" height={height} viewBox="0 0 420 410">
        {[0, 220].map((dx) => SILHOUETTE.map((s, i) => draw(s, dx, { fill: t.dark ? '#222220' : '#eeede8' }, `s${dx}${i}`)))}
        {muscle(FRONT, 0)}
        {muscle(BACK, 220)}
        <SvgText x={100} y={405} textAnchor="middle" fontSize={14} fill={t.muted}>Front</SvgText>
        <SvgText x={320} y={405} textAnchor="middle" fontSize={14} fill={t.muted}>Back</SvgText>
      </Svg>
    </View>
  );
}

export function SetsScale({ top = 20 }: { top?: number }) {
  const t = useTheme();
  return <Legend items={[0, top / 4, top / 2, (3 * top) / 4, top].map((v) => ({ label: `${v === top ? `${v}+` : v}`, color: setsColor(t, v, top) }))} />;
}
