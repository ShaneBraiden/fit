/* Chart colours and shared ECharts option pieces, read from the CSS tokens so light and
   dark mode use their own validated steps (see tokens.css). */
import { useEffect, useState } from 'react';

export interface Palette {
  surface: string; text: string; text2: string; muted: string; grid: string; axis: string;
  series: string[]; seq: string[]; divNeg: string; divMid: string; divPos: string;
  good: string; warning: string; serious: string; critical: string; dark: boolean;
}

function read(): Palette {
  const s = getComputedStyle(document.documentElement);
  const v = (n: string) => s.getPropertyValue(n).trim();
  return {
    surface: v('--surface'), text: v('--text'), text2: v('--text-2'), muted: v('--muted'), grid: v('--grid'),
    axis: v('--axis'),
    series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--s${i}`)),
    seq: [100, 200, 300, 400, 500, 600, 700].map((i) => v(`--seq-${i}`)),
    divNeg: v('--div-neg'), divMid: v('--div-mid'), divPos: v('--div-pos'),
    good: v('--good'), warning: v('--warning'), serious: v('--serious'), critical: v('--critical'),
    dark: s.getPropertyValue('color-scheme').includes('dark'),
  };
}

/** Re-reads the palette whenever the theme (OS or toggle) changes. */
export function usePalette(): Palette {
  const [p, setP] = useState<Palette>(read);
  useEffect(() => {
    const update = () => setP(read());
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', update);
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => { mq.removeEventListener('change', update); mo.disconnect(); };
  }, []);
  return p;
}

/** Marker shapes give scatter series a second channel besides hue. */
export const SYMBOLS = ['circle', 'rect', 'triangle', 'diamond', 'roundRect', 'pin', 'arrow', 'circle'];

export function axisStyle(p: Palette) {
  return {
    axisLine: { lineStyle: { color: p.axis } },
    axisTick: { show: false },
    axisLabel: { color: p.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: p.grid, type: 'solid' as const } },
    nameTextStyle: { color: p.text2, fontSize: 12 },
  };
}

export function base(p: Palette) {
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: p.text2 },
    color: p.series,
    animationDuration: 300,
    grid: { left: 52, right: 18, top: 28, bottom: 40, containLabel: false },
    tooltip: {
      backgroundColor: p.surface, borderColor: p.grid, textStyle: { color: p.text, fontSize: 12 },
      extraCssText: 'box-shadow: 0 4px 14px rgba(0,0,0,0.12); border-radius: 8px;',
    },
    legend: { textStyle: { color: p.text2, fontSize: 12 }, icon: 'roundRect', itemWidth: 10, itemHeight: 10, top: 0 },
  };
}

/** Bars: 4px rounded data end, square at the baseline, capped thickness. */
export function barItem(color: string, horizontal = false) {
  return {
    color,
    borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
  };
}

export function seqColor(p: Palette, t: number): string {
  const i = Math.max(0, Math.min(p.seq.length - 1, Math.round(t * (p.seq.length - 1))));
  return p.seq[i];
}

export const fmt = {
  n: (v: number | null | undefined, d = 0) => (v == null ? '–' : v.toLocaleString(undefined, {
    maximumFractionDigits: d, minimumFractionDigits: d })),
  pct: (v: number | null | undefined, d = 1) => (v == null ? '–' : `${(v * 100).toFixed(d)}%`),
  compact: (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3
    ? `${(v / 1e3).toFixed(1)}K` : `${Math.round(v * 100) / 100}`),
};

/** Typed helper for ECharts label/tooltip formatters that only need the numeric value. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const valueLabel = (f: (n: number) => string): any => (v: { value: unknown }) => f(Number(v.value));
