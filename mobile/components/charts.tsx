import { useState } from 'react';
import { LayoutChangeEvent, Text, View } from 'react-native';
import Svg, { Circle, G, Line, Polyline, Rect, Text as SvgText } from 'react-native-svg';
import { CATEGORY_ORDER, levelColor, LEVELS, phaseColor, PHASES, space, type, useTheme } from '../lib/theme';

function useWidth(initial = 300): [number, (e: LayoutChangeEvent) => void] {
  const [w, setW] = useState(initial);
  return [w, (e) => setW(Math.max(120, e.nativeEvent.layout.width))];
}

export function Legend({ items }: { items: { label: string; color: string; line?: boolean }[] }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 6 }}>
      {items.map((it) => (
        <View key={it.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
          <View style={{ width: it.line ? 14 : 10, height: it.line ? 2 : 10, borderRadius: 2, backgroundColor: it.color }} />
          <Text style={[type.small, { color: t.text2 }]}>{it.label}</Text>
        </View>
      ))}
    </View>
  );
}

/** Weekly training minutes, stacked by activity category (an OLAP roll-up of the user's workouts). */
export function WeeklyBars({ weeks }: { weeks: { week: string; minutes: Record<string, number> }[] }) {
  const t = useTheme();
  const [w, onLayout] = useWidth();
  const h = 150, left = 34, bottom = 20, top = 8;
  const totals = weeks.map((x) => CATEGORY_ORDER.reduce((s, c) => s + (x.minutes[c] ?? 0), 0));
  const max = Math.max(60, ...totals);
  const step = max > 600 ? 300 : max > 300 ? 150 : 60;
  const ymax = Math.ceil(max / step) * step;
  const band = (w - left) / Math.max(weeks.length, 1);
  const bw = Math.min(22, band * 0.6);
  const y = (v: number) => top + (h - top - bottom) * (1 - v / ymax);
  return (
    <View onLayout={onLayout}>
      <Svg width={w} height={h}>
        {Array.from({ length: ymax / step + 1 }).map((_, i) => (
          <G key={i}>
            <Line x1={left} x2={w} y1={y(i * step)} y2={y(i * step)} stroke={t.grid} strokeWidth={1} />
            <SvgText x={left - 6} y={y(i * step) + 4} fontSize={10} fill={t.muted} textAnchor="end">{i * step}</SvgText>
          </G>
        ))}
        {weeks.map((x, i) => {
          let acc = 0;
          const cx = left + band * i + (band - bw) / 2;
          return (
            <G key={x.week}>
              {CATEGORY_ORDER.map((c, ci) => {
                const v = x.minutes[c] ?? 0;
                if (v <= 0) return null;
                const y0 = y(acc), y1 = y(acc + v);
                acc += v;
                return <Rect key={c} x={cx} y={y1} width={bw} height={Math.max(0, y0 - y1 - 2)} fill={t.series[ci]} rx={ci === 2 || acc === totals[i] ? 3 : 0} />;
              })}
              <SvgText x={cx + bw / 2} y={h - 6} fontSize={10} fill={t.muted} textAnchor="middle">{x.week.slice(-3)}</SvgText>
            </G>
          );
        })}
      </Svg>
      <Legend items={CATEGORY_ORDER.map((c, i) => ({ label: c, color: t.series[i] }))} />
    </View>
  );
}

/** Classifier output: probability of each level, ordered light (Beginner) to dark (Elite). */
export function ProbBars({ probs, highlight }: { probs: Record<string, number>; highlight?: string }) {
  const t = useTheme();
  return (
    <View style={{ gap: 6 }}>
      {LEVELS.map((lv) => {
        const p = probs[lv] ?? 0;
        return (
          <View key={lv} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={[type.small, { color: lv === highlight ? t.text : t.text2, width: 86, fontWeight: lv === highlight ? '600' : '400' }]}>{lv}</Text>
            <View style={{ flex: 1, height: 8, borderRadius: 4, backgroundColor: t.surface2 }}>
              <View style={{ width: `${Math.max(2, p * 100)}%`, height: 8, borderRadius: 4, backgroundColor: levelColor(t, lv) }} />
            </View>
            <Text style={[type.small, { color: t.text2, width: 38, textAlign: 'right' }]}>{Math.round(p * 100)}%</Text>
          </View>
        );
      })}
    </View>
  );
}

/** Heart-rate line with the 220 bpm human ceiling for reference. */
export function HrChart({ hr, dt }: { hr: number[]; dt: number }) {
  const t = useTheme();
  const [w, onLayout] = useWidth();
  const h = 140, left = 30, top = 8, bottom = 18;
  if (!hr.length) return null;
  const ymax = Math.max(230, ...hr), ymin = Math.min(40, ...hr);
  const x = (i: number) => left + (w - left) * (i / Math.max(hr.length - 1, 1));
  const y = (v: number) => top + (h - top - bottom) * (1 - (v - ymin) / (ymax - ymin));
  const mins = Math.round(hr.length * dt / 60);
  return (
    <View onLayout={onLayout}>
      <Svg width={w} height={h}>
        {[60, 120, 180].map((v) => (
          <G key={v}><Line x1={left} x2={w} y1={y(v)} y2={y(v)} stroke={t.grid} />
            <SvgText x={left - 4} y={y(v) + 4} fontSize={10} fill={t.muted} textAnchor="end">{v}</SvgText></G>
        ))}
        <Line x1={left} x2={w} y1={y(220)} y2={y(220)} stroke={t.critical} strokeWidth={1} />
        <SvgText x={w - 2} y={y(220) - 4} fontSize={10} fill={t.text2} textAnchor="end">220 bpm</SvgText>
        <Polyline points={hr.map((v, i) => `${x(i)},${y(v)}`).join(' ')} fill="none" stroke={t.series[0]} strokeWidth={2} strokeLinejoin="round" />
        <SvgText x={left} y={h - 4} fontSize={10} fill={t.muted}>0′</SvgText>
        <SvgText x={w} y={h - 4} fontSize={10} fill={t.muted} textAnchor="end">{mins}′</SvgText>
      </Svg>
    </View>
  );
}

interface Seg { start: number; end: number; phase: string; mean_speed: number }

/** Speed over time, shaded by the detected run phase. */
export function SpeedChart({ speed, segments }: { speed: number[]; segments: Seg[] }) {
  const t = useTheme();
  const [w, onLayout] = useWidth();
  const h = 130, left = 30, top = 6, bottom = 14;
  if (!speed.length) return null;
  // Robust scale: a GPS glitch can report 1000+ km/h for one sample; clip it instead of flattening the run.
  const sorted = [...speed].sort((a, b) => a - b);
  const p95 = sorted[Math.floor(sorted.length * 0.95)] ?? sorted[sorted.length - 1];
  const ymax = Math.min(Math.max(...speed), p95 * 1.6) * 1.08;
  const clipped = speed.some((v) => v > ymax);
  const x = (i: number) => left + (w - left) * (i / Math.max(speed.length - 1, 1));
  const y = (v: number) => top + (h - top - bottom) * (1 - Math.min(v, ymax) / ymax);
  const used = PHASES.filter((ph) => segments.some((s) => s.phase === ph));
  return (
    <View onLayout={onLayout}>
      <Svg width={w} height={h}>
        {segments.map((s, i) => (
          <Rect key={i} x={x(s.start)} y={top} width={Math.max(1, x(s.end - 1) - x(s.start))} height={h - top - bottom}
            fill={phaseColor(t, s.phase)} opacity={0.22} />
        ))}
        {[0.5, 1].map((f) => (
          <SvgText key={f} x={left - 4} y={y(ymax * f / 1.08) + 4} fontSize={10} fill={t.muted} textAnchor="end">{Math.round(ymax * f / 1.08)}</SvgText>
        ))}
        <Polyline points={speed.map((v, i) => `${x(i)},${y(v)}`).join(' ')} fill="none" stroke={t.text2} strokeWidth={1.5} />
        {speed.map((v, i) => (v > ymax ? <Circle key={i} cx={x(i)} cy={top + 3} r={3} fill={t.critical} /> : null))}
      </Svg>
      <Legend items={used.map((ph) => ({ label: ph, color: phaseColor(t, ph) }))} />
      {clipped && <Text style={[type.small, { color: t.text2, marginTop: 4 }]}>
        Red dots: GPS samples above {Math.round(ymax)} km/h, clipped (peak {Math.round(Math.max(...speed))} km/h).</Text>}
    </View>
  );
}

/** A GPS track (optionally coloured by segment) over faint reference routes; equirectangular projection. */
export function RouteMap({ lat, lon, segments, background = [], height = 220 }: {
  lat: number[]; lon: number[]; segments?: Seg[] | null; background?: { track: number[][]; color?: string; label?: string }[]; height?: number;
}) {
  const t = useTheme();
  const [w, onLayout] = useWidth();
  const pts: [number, number][] = [...lat.map((la, i) => [la, lon[i]] as [number, number]), ...background.flatMap((b) => b.track as [number, number][])];
  if (!pts.length) return null;
  const lats = pts.map((p) => p[0]), lons = pts.map((p) => p[1]);
  const la0 = Math.min(...lats), la1 = Math.max(...lats), lo0 = Math.min(...lons), lo1 = Math.max(...lons);
  const k = Math.cos(((la0 + la1) / 2) * Math.PI / 180);
  const spanX = Math.max((lo1 - lo0) * k, 1e-4), spanY = Math.max(la1 - la0, 1e-4);
  const pad = 12;
  const s = Math.min((w - 2 * pad) / spanX, (height - 2 * pad) / spanY);
  const ox = (w - spanX * s) / 2, oy = (height - spanY * s) / 2;
  const P = (la: number, lo: number) => `${ox + (lo - lo0) * k * s},${oy + (la1 - la) * s}`;
  const line = (from: number, to: number) => lat.slice(from, to).map((la, i) => P(la, lon[from + i])).join(' ');
  return (
    <View onLayout={onLayout} style={{ borderRadius: 12, overflow: 'hidden', backgroundColor: t.surface2 }}>
      <Svg width={w} height={height}>
        {background.map((b, i) => (
          <Polyline key={`b${i}`} points={(b.track as [number, number][]).map(([la, lo]) => P(la, lo)).join(' ')} fill="none"
            stroke={b.color ?? t.muted} strokeWidth={b.color ? 3 : 2} strokeLinejoin="round" opacity={b.color ? 0.95 : 0.6} />
        ))}
        {segments && segments.length
          ? segments.map((sg, i) => (
            <Polyline key={i} points={line(sg.start, sg.end + 1)} fill="none" stroke={phaseColor(t, sg.phase)} strokeWidth={4}
              strokeLinejoin="round" strokeLinecap="round" />))
          : lat.length > 1 && <Polyline points={line(0, lat.length)} fill="none" stroke={t.series[0]} strokeWidth={3} strokeLinejoin="round" />}
        {lat.length > 0 && <Circle cx={Number(P(lat[0], lon[0]).split(',')[0])} cy={Number(P(lat[0], lon[0]).split(',')[1])} r={5}
          fill={t.good} stroke={t.surface} strokeWidth={2} />}
      </Svg>
    </View>
  );
}

export function Meter({ value, color }: { value: number; color?: string }) {
  const t = useTheme();
  return (
    <View style={{ height: 6, borderRadius: 3, backgroundColor: t.surface2, marginTop: space.xs }}>
      <View style={{ width: `${Math.min(100, Math.max(2, value * 100))}%`, height: 6, borderRadius: 3, backgroundColor: color ?? t.accent }} />
    </View>
  );
}

