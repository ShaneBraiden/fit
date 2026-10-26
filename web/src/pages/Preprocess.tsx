import type { EChartsOption } from 'echarts';
import { useGet } from '../api/client';
import { Card, ChartCard, DataTable, ErrorBox, Loading, PageHead, Recovery, SectionTitle, Tile } from '../components/ui';
import { axisStyle, barItem, base, fmt, Palette, usePalette, valueLabel } from '../theme/chart';

interface Col { column: string; dtype: string; missing: number; missing_pct: number; distinct: number; example: string | null }
interface Imp { column: string; n_missing: number; methods: { method: string; rmse: number; mae: number }[]; chosen: string }
interface Hist { counts: number[]; edges: number[] }
interface U1 {
  raw: { users: number; workouts: number }; clean: { users: number; workouts: number };
  profile: { users: Col[]; workouts: Col[] };
  labels: { mapping: { activity_raw: string; activity: string; count: number }[]; variants: number; canonical: number };
  units: { distance_mi_to_km: number; weight_lb_to_kg: number };
  duplicates: { found: number; true: number; precision: number; recall: number; examples: { duplicate: number; kept: number }[] };
  sessions: { accuracy: number; rules: { pattern: string; session: string }[]; counts: Record<string, number> };
  imputation: Imp[];
  smoothing: { sample: number[]; bins: number[][]; by_means: number[][]; by_medians: number[][]; by_boundaries: number[][];
    stream_workout: number; hr_raw: number[]; hr_moving_median: number[] };
  normalisation: { attribute: string; variants: { name: string; min: number; max: number; mean: number; std: number; hist: Hist }[] };
  discretisation: { attribute: string; class: string; base_entropy: number;
    methods: Record<string, { edges: number[]; counts: number[]; class_entropy: number }> };
  correlation: { columns: string[]; matrix: number[][]; chi_square: { test: string; rows: string[]; cols: string[];
    observed: number[][]; expected: number[][]; chi2: number; dof: number; p_value: number }[] };
  pca: { columns: string[]; explained_variance_ratio: number[]; loadings: number[][];
    points: { x: number; y: number; level: string; user_id: number }[] };
  sampling: { fraction: number; rows: { activity: string; population: number; srswor: number; stratified: number }[];
    max_abs_dev: { srswor: number; stratified: number } };
}

const LEVELS = ['Beginner', 'Intermediate', 'Advanced', 'Elite'];

function missingChart(p: Palette, cols: Col[]): EChartsOption {
  const rows = cols.filter((c) => c.missing > 0);
  return {
    ...base(p), grid: { left: 90, right: 50, top: 8, bottom: 28 },
    xAxis: { type: 'value', ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: '{value}%' } },
    yAxis: { type: 'category', data: rows.map((r) => r.column), ...axisStyle(p), axisLabel: { color: p.text2 } },
    tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{ type: 'bar', barMaxWidth: 18, data: rows.map((r) => r.missing_pct), itemStyle: barItem(p.series[0], true),
      label: { show: true, position: 'right', color: p.text2, formatter: '{c}%' } }],
  };
}

function rmseChart(p: Palette, imp: Imp): EChartsOption {
  return {
    ...base(p), grid: { left: 170, right: 50, top: 8, bottom: 28 },
    xAxis: { type: 'value', ...axisStyle(p), name: 'RMSE' },
    yAxis: { type: 'category', data: imp.methods.map((m) => m.method), ...axisStyle(p), axisLabel: { color: p.text2 } },
    tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{ type: 'bar', barMaxWidth: 18,
      data: imp.methods.map((m) => ({ value: m.rmse, itemStyle: barItem(m.method === imp.chosen ? p.series[0] : p.axis, true) })),
      label: { show: true, position: 'right', color: p.text2, formatter: valueLabel((n) => n.toFixed(1)) } }],
  };
}

function histChart(p: Palette, h: Hist): EChartsOption {
  const labels = h.counts.map((_, i) => fmt.compact(h.edges[i]));
  return {
    ...base(p), grid: { left: 40, right: 8, top: 10, bottom: 24 },
    xAxis: { type: 'category', data: labels, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, interval: 5 } },
    yAxis: { type: 'value', ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.compact(v) } },
    tooltip: { ...base(p).tooltip, trigger: 'axis' },
    series: [{ type: 'bar', barCategoryGap: '8%', data: h.counts, itemStyle: barItem(p.series[0]) }],
  };
}

export default function Preprocess() {
  const p = usePalette();
  const { data: r, error } = useGet<U1>('/api/preprocess/report');
  if (error) return <ErrorBox error={error} />;
  if (!r) return <Loading />;
  const c = r.correlation;
  const heat: [number, number, number][] = [];
  c.matrix.forEach((row, i) => row.forEach((v, j) => heat.push([j, i, v])));
  const evr = r.pca.explained_variance_ratio;
  const cum = evr.map((_, i) => evr.slice(0, i + 1).reduce((a, b) => a + b, 0));
  const levelColor: Record<string, string> = { Beginner: p.seq[1], Intermediate: p.seq[3], Advanced: p.seq[4],
    Elite: p.seq[6], Unassessed: p.axis };
  const disc = Object.entries(r.discretisation.methods);

  return (
    <>
      <PageHead code="U1" title="Data preprocessing">
        The raw app export is messy on purpose: missing heart rates and calories, re-synced duplicate uploads, imperial
        units from one device brand and 31 spellings of 7 activities. Cleaning writes the <code>users</code> and{' '}
        <code>workouts</code> tables every later unit mines.
      </PageHead>

      <div className="grid g4">
        <Tile label="Activity labels" value={`${r.labels.variants} → ${r.labels.canonical}`} sub="synonym + case normalisation" />
        <Tile label="Unit conversions" value={fmt.n(r.units.distance_mi_to_km + r.units.weight_lb_to_kg)}
          sub={`${fmt.n(r.units.distance_mi_to_km)} mi→km, ${r.units.weight_lb_to_kg} lb→kg`} />
        <Tile label="Duplicate uploads removed" value={fmt.n(r.duplicates.found)}
          sub={`precision ${fmt.pct(r.duplicates.precision)}, recall ${fmt.pct(r.duplicates.recall)}`} />
        <Tile label="Session type from titles" value={fmt.pct(r.sessions.accuracy)} sub="keyword rules, vs true type" />
      </div>

      <SectionTitle title="Data quality profile" sub="share of missing values per raw column" />
      <div className="grid g2">
        {(['workouts', 'users'] as const).map((t) => (
          <ChartCard key={t} title={`${t}_raw`} sub={`${fmt.n(r.raw[t])} rows${t === 'workouts' ? ' · distance is empty by design for gym sessions' : ' · unassessed users have no level'}`} height={200}
            option={missingChart(p, r.profile[t])}
            table={r.profile[t] as unknown as Record<string, unknown>[]} cols={[
              { key: 'column', label: 'Column' }, { key: 'dtype', label: 'Type' },
              { key: 'missing', label: 'Missing', num: true }, { key: 'missing_pct', label: '%', num: true, digits: 2 },
              { key: 'distinct', label: 'Distinct', num: true }, { key: 'example', label: 'Example' }]} />
        ))}
      </div>

      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Activity label normalisation" sub="raw spelling → canonical activity">
          <DataTable rows={r.labels.mapping} height={260} cols={[
            { key: 'activity_raw', label: 'Raw label', render: (x) => <code>{x.activity_raw}</code> },
            { key: 'activity', label: 'Canonical' }, { key: 'count', label: 'Rows', num: true }]} />
        </Card>
        <Card title="Session type rules" sub="first matching keyword in the workout title wins">
          <DataTable rows={r.sessions.rules.map((x) => ({ ...x, n: r.sessions.counts[x.session] ?? 0 }))} height={260} cols={[
            { key: 'pattern', label: 'Title regex', render: (x) => <code>{x.pattern}</code> },
            { key: 'session', label: 'Session type' }, { key: 'n', label: 'Workouts', num: true }]} />
        </Card>
      </div>

      <SectionTitle title="Missing-value imputation"
        sub="each method fills the masked cells; RMSE against the true hidden values picks the winner" />
      <div className="grid g3">
        {r.imputation.map((imp) => (
          <ChartCard key={imp.column} title={imp.column} sub={`${fmt.n(imp.n_missing)} missing · chosen: ${imp.chosen}`}
            height={200} option={rmseChart(p, imp)} table={imp.methods} cols={[
              { key: 'method', label: 'Method' }, { key: 'rmse', label: 'RMSE', num: true, digits: 2 },
              { key: 'mae', label: 'MAE', num: true, digits: 2 }]} />
        ))}
      </div>

      <SectionTitle title="Noise smoothing" />
      <div className="grid g2">
        <Card title="Smoothing by bins (equal depth, 3 bins)" sub="12 sorted run calorie values, the textbook procedure">
          <DataTable rows={r.smoothing.bins.map((b, i) => ({ bin: i + 1, values: b.join(', '),
            means: r.smoothing.by_means[i].map((v) => v.toFixed(1)).join(', '),
            medians: r.smoothing.by_medians[i].join(', '), bounds: r.smoothing.by_boundaries[i].join(', ') }))} cols={[
            { key: 'bin', label: 'Bin', num: true }, { key: 'values', label: 'Values', wrap: true },
            { key: 'means', label: 'By means', wrap: true }, { key: 'medians', label: 'By medians', wrap: true },
            { key: 'bounds', label: 'By boundaries', wrap: true }]} />
        </Card>
        <ChartCard title={`HR stream of workout ${r.smoothing.stream_workout}`}
          sub="raw sensor readings vs 5-sample moving median (interval run)" height={240}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['raw', 'moving median'] },
            xAxis: { type: 'category', data: r.smoothing.hr_raw.map((_, i) => `${Math.round(i * 15 / 60)}′`), ...axisStyle(p),
              axisLabel: { ...axisStyle(p).axisLabel, interval: 39 } },
            yAxis: { type: 'value', min: 'dataMin', ...axisStyle(p), name: 'bpm' },
            tooltip: { ...base(p).tooltip, trigger: 'axis' },
            series: [
              { name: 'raw', type: 'line', data: r.smoothing.hr_raw, showSymbol: false, lineStyle: { width: 1, color: p.axis }, itemStyle: { color: p.axis } },
              { name: 'moving median', type: 'line', data: r.smoothing.hr_moving_median, showSymbol: false, lineStyle: { width: 2, color: p.series[0] }, itemStyle: { color: p.series[0] } },
            ],
          }} />
      </div>

      <SectionTitle title="Normalisation" sub={`${r.normalisation.attribute}: same shape, different scale`} />
      <div className="grid g4">
        {r.normalisation.variants.map((v) => (
          <ChartCard key={v.name} title={v.name} sub={`min ${fmt.n(v.min, 2)} · max ${fmt.n(v.max, 2)} · mean ${fmt.n(v.mean, 2)}`}
            height={170} option={histChart(p, v.hist)}
            table={v.hist.counts.map((n, i) => ({ from: v.hist.edges[i], to: v.hist.edges[i + 1], n }))} cols={[
              { key: 'from', label: 'From', num: true, digits: 3 }, { key: 'to', label: 'To', num: true, digits: 3 },
              { key: 'n', label: 'Count', num: true }]} />
        ))}
      </div>

      <SectionTitle title="Discretisation of age"
        sub={`weighted class entropy of ${r.discretisation.class} per partition (lower = bins separate levels better; base ${r.discretisation.base_entropy.toFixed(3)})`} />
      <div className="grid g3">
        {disc.map(([name, m]) => (
          <ChartCard key={name} title={name} sub={`${m.counts.length} bins · class entropy ${m.class_entropy.toFixed(3)}`} height={180}
            option={{
              ...base(p), grid: { left: 40, right: 10, top: 10, bottom: 28 },
              xAxis: { type: 'category', data: m.counts.map((_, i) => `${Math.round(m.edges[i])}–${Math.round(m.edges[i + 1])}`), ...axisStyle(p) },
              yAxis: { type: 'value', ...axisStyle(p) },
              tooltip: { ...base(p).tooltip, trigger: 'axis' },
              series: [{ type: 'bar', barMaxWidth: 24, data: m.counts, itemStyle: barItem(p.series[0]) }],
            }}
            table={m.counts.map((n, i) => ({ bin: `${m.edges[i]}–${m.edges[i + 1]}`, n }))}
            cols={[{ key: 'bin', label: 'Age range' }, { key: 'n', label: 'Users', num: true }]} />
        ))}
      </div>

      <SectionTitle title="Correlation analysis" />
      <div className="grid g2">
        <ChartCard title="Pearson correlation of user features" sub="blue positive, red negative, grey ≈ 0" height={420}
          option={{
            ...base(p), grid: { left: 120, right: 20, top: 10, bottom: 110 },
            xAxis: { type: 'category', data: c.columns, ...axisStyle(p), axisLabel: { color: p.text2, rotate: 50, fontSize: 11 } },
            yAxis: { type: 'category', data: c.columns, ...axisStyle(p), axisLabel: { color: p.text2, fontSize: 11 } },
            visualMap: { min: -1, max: 1, show: false, inRange: { color: [p.divNeg, p.divMid, p.divPos] } },
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const v = (x as { value: [number, number, number] }).value;
              return `${c.columns[v[1]]} × ${c.columns[v[0]]}<br/><b>r = ${v[2].toFixed(3)}</b>`;
            } },
            series: [{ type: 'heatmap', data: heat, itemStyle: { borderColor: p.surface, borderWidth: 2 },
              emphasis: { itemStyle: { borderColor: p.text, borderWidth: 1 } } }],
          }}
          table={c.matrix.map((row, i) => ({ feature: c.columns[i], ...Object.fromEntries(row.map((v, j) => [c.columns[j], v])) }))}
          cols={[{ key: 'feature', label: '' }, ...c.columns.map((k) => ({ key: k, label: k, num: true, digits: 2 }))]} />
        <div className="stack">
          {c.chi_square.map((t) => (
            <Card key={t.test} title={`χ² test: ${t.test}`}
              sub={`χ² = ${t.chi2.toFixed(1)}, dof = ${t.dof}, p = ${t.p_value.toExponential(2)} → ${t.p_value < 0.05 ? 'dependent' : 'no evidence of dependence'} at α = 0.05`}>
              <DataTable rows={t.rows.map((row, i) => ({ row, ...Object.fromEntries(t.cols.map((col, j) => [col,
                `${t.observed[i][j]} (${t.expected[i][j].toFixed(0)})`])) }))}
                cols={[{ key: 'row', label: 'observed (expected)' }, ...t.cols.map((k) => ({ key: k, label: k, num: true }))]} />
            </Card>
          ))}
        </div>
      </div>

      <SectionTitle title="Dimensionality reduction (PCA)" sub="standardised user features" />
      <div className="grid g2">
        <ChartCard title="Explained variance" sub="per component (bars) and cumulative (line), one shared 0–100% axis" height={280}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['component', 'cumulative'] },
            xAxis: { type: 'category', data: evr.map((_, i) => `PC${i + 1}`), ...axisStyle(p) },
            yAxis: { type: 'value', max: 1, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => `${v * 100}%` } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => fmt.pct(v as number) },
            series: [
              { name: 'component', type: 'bar', barMaxWidth: 20, data: evr, itemStyle: barItem(p.series[0]) },
              { name: 'cumulative', type: 'line', data: cum, symbolSize: 7, lineStyle: { width: 2, color: p.series[1] },
                itemStyle: { color: p.series[1], borderColor: p.surface, borderWidth: 2 } },
            ],
          }}
          table={evr.map((v, i) => ({ pc: `PC${i + 1}`, v, c: cum[i] }))}
          cols={[{ key: 'pc', label: 'Component' }, { key: 'v', label: 'Explained', num: true, pct: true },
            { key: 'c', label: 'Cumulative', num: true, pct: true }]} />
        <ChartCard title="Users on PC1 × PC2" sub="coloured by assessed fitness level (ordinal ramp)" height={280}
          option={{
            ...base(p), legend: { ...base(p).legend, data: [...LEVELS, 'Unassessed'] },
            grid: { left: 40, right: 12, top: 34, bottom: 30 },
            xAxis: { type: 'value', ...axisStyle(p), name: 'PC1', nameLocation: 'middle', nameGap: 22 },
            yAxis: { type: 'value', ...axisStyle(p), name: 'PC2' },
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const d = x as { seriesName: string; value: [number, number, number] };
              return `user ${d.value[2]}<br/>${d.seriesName}`;
            } },
            series: [...LEVELS, 'Unassessed'].map((lv) => ({
              name: lv, type: 'scatter', symbolSize: 7,
              data: r.pca.points.filter((pt) => pt.level === lv).map((pt) => [pt.x, pt.y, pt.user_id]),
              itemStyle: { color: levelColor[lv], borderColor: p.surface, borderWidth: 1, opacity: lv === 'Unassessed' ? 0.5 : 0.9 },
            })),
          }} />
      </div>

      <SectionTitle title="Data reduction by sampling" sub={`${r.sampling.fraction * 100}% sample of workouts: activity mix preserved?`} />
      <div className="grid g2">
        <ChartCard title="Activity share: population vs samples"
          sub={`max deviation: SRSWOR ${fmt.pct(r.sampling.max_abs_dev.srswor, 2)}, stratified ${fmt.pct(r.sampling.max_abs_dev.stratified, 2)}`}
          height={260}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['population', 'SRSWOR', 'stratified'] },
            xAxis: { type: 'category', data: r.sampling.rows.map((x) => x.activity), ...axisStyle(p) },
            yAxis: { type: 'value', ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => `${Math.round(v * 100)}%` } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => fmt.pct(v as number) },
            series: (['population', 'srswor', 'stratified'] as const).map((k, i) => ({
              name: ['population', 'SRSWOR', 'stratified'][i], type: 'bar', barMaxWidth: 14, barGap: '15%',
              data: r.sampling.rows.map((x) => x[k]), itemStyle: barItem(p.series[i]),
            })),
          }}
          table={r.sampling.rows} cols={[{ key: 'activity', label: 'Activity' },
            { key: 'population', label: 'Population', num: true, pct: true, digits: 2 },
            { key: 'srswor', label: 'SRSWOR', num: true, pct: true, digits: 2 },
            { key: 'stratified', label: 'Stratified', num: true, pct: true, digits: 2 }]} />
        <Recovery items={[
          { label: 'Re-synced duplicates found', value: `${r.duplicates.found} / ${r.duplicates.true}`, ok: r.duplicates.recall === 1 && r.duplicates.precision === 1 },
          ...r.imputation.map((imp) => {
            const best = Math.min(...imp.methods.map((m) => m.rmse));
            const mean = imp.methods.find((m) => m.method === 'mean')!.rmse;
            return { label: `${imp.column}: RMSE of ${imp.chosen}`, value: `${best.toFixed(2)} (mean: ${mean.toFixed(2)})`,
              note: `${((1 - best / mean) * 100).toFixed(0)}% lower error than mean imputation`, ok: best < mean };
          }),
          { label: 'Session types from titles', value: fmt.pct(r.sessions.accuracy), ok: r.sessions.accuracy > 0.95 },
        ]} />
      </div>
    </>
  );
}
