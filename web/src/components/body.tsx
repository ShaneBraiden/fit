/* Front and back body figures with each muscle coloured by its sets per week. */
import { Palette, seqColor } from '../theme/chart';

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

function draw(s: Shape, dx: number, props: Record<string, unknown>, key: string) {
  if ('e' in s) return <ellipse key={key} cx={s.e[0] + dx} cy={s.e[1]} rx={s.e[2]} ry={s.e[3]} {...props} />;
  return <rect key={key} x={s.r[0] + dx} y={s.r[1]} width={s.r[2]} height={s.r[3]} rx={s.r[4]} {...props} />;
}

/** Sets per week -> fill colour: grey when untrained, then the blue ramp up to the top of the target. */
export const setsColor = (p: Palette, sets: number, top = 20) => (sets <= 0 ? p.axis : seqColor(p, 0.15 + 0.85 * Math.min(1, sets / top)));

export function BodyMap({ p, sets, selected, onSelect, top = 20 }: {
  p: Palette; sets: Record<string, number>; selected?: string | null; onSelect?: (m: string) => void; top?: number;
}) {
  const muscle = (view: Record<string, Shape[]>, dx: number) => Object.entries(view).flatMap(([m, shapes]) => shapes.map((s, i) => draw(s, dx, {
    fill: setsColor(p, sets[m] ?? 0, top), stroke: selected === m ? p.text : p.surface, strokeWidth: selected === m ? 2.5 : 1.5,
    style: { cursor: onSelect ? 'pointer' : undefined }, onClick: onSelect ? () => onSelect(m) : undefined,
    children: <title>{`${m}: ${(sets[m] ?? 0).toFixed(1)} sets`}</title>,
  }, `${m}${dx}${i}`)));
  return (
    <svg viewBox="0 0 420 410" role="img" aria-label="Sets per muscle, front and back" style={{ width: '100%', maxHeight: 420 }}>
      {[0, 220].map((dx) => SILHOUETTE.map((s, i) => draw(s, dx, { fill: p.dark ? '#222220' : '#eeede8' }, `s${dx}${i}`)))}
      {muscle(FRONT, 0)}
      {muscle(BACK, 220)}
      <text x={100} y={405} textAnchor="middle" fontSize={12} fill={p.muted}>Front</text>
      <text x={320} y={405} textAnchor="middle" fontSize={12} fill={p.muted}>Back</text>
    </svg>
  );
}

export function SetsScale({ p, top = 20 }: { p: Palette; top?: number }) {
  const stops = [0, top / 4, top / 2, (3 * top) / 4, top];
  return (
    <div className="legend" aria-label="Colour scale">
      {stops.map((v) => <span key={v}><i style={{ background: setsColor(p, v, top) }} />{v === top ? `${v}+` : v} sets</span>)}
    </div>
  );
}
