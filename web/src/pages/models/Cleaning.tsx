import { Card, ChartCard, DataTable, PageHead, Recovery, SectionTitle, Tile } from '../../components/ui';
import { axisStyle, barItem, base, fmt, usePalette } from '../../theme/chart';
import { Report } from './shared';

interface Imputation { column: string; n_missing: number; chosen: string; methods: { method: string; rmse: number; mae: number }[] }
interface Cleaning {
  raw: { users: number; workouts: number }; clean: { users: number; workouts: number };
  labels: { mapping: { activity_raw: string; activity: string; count: number }[]; variants: number; canonical: number };
  units: { distance_mi_to_km: number; weight_lb_to_kg: number };
  duplicates: { found: number; true: number; precision: number; recall: number };
  sessions: { accuracy: number; rules: { pattern: string; session: string }[] };
  imputation: Imputation[];
}

export default function CleaningPage() {
  const p = usePalette();
  return (
    <Report<Cleaning> name="cleaning">{(r) => (
      <>
        <PageHead title="Data cleaning">
          The training data arrives the way a real app export does: messy labels, mixed units, duplicate uploads when a watch
          re-syncs, and missing heart rate, calories and weight. Missing values are filled with kNN imputation (the mean of the
          5 most similar records of the same activity), scored against the hidden true values.
        </PageHead>
        <div className="grid g4">
          <Tile label="Activity spellings" value={`${r.labels.variants} → ${r.labels.canonical}`} sub="mapped to canonical activities" />
          <Tile label="Unit conversions" value={fmt.n(r.units.distance_mi_to_km + r.units.weight_lb_to_kg)}
            sub={`${fmt.n(r.units.distance_mi_to_km)} mi→km, ${r.units.weight_lb_to_kg} lb→kg`} />
          <Tile label="Duplicate uploads removed" value={`${r.duplicates.found} / ${r.duplicates.true}`}
            sub={`precision ${fmt.pct(r.duplicates.precision)} · recall ${fmt.pct(r.duplicates.recall)}`} />
          <Tile label="Session type from titles" value={fmt.pct(r.sessions.accuracy)} sub={`${r.sessions.rules.length} ordered rules`} />
        </div>
        <SectionTitle title="Missing values: kNN imputation vs the mean baseline" sub="error on the values that were hidden" />
        <div className="grid g3">
          {r.imputation.map((m) => (
            <ChartCard key={m.column} title={m.column} sub={`${fmt.n(m.n_missing)} missing · RMSE (lower is better)`} height={150}
              table={m.methods} cols={[{ key: 'method', label: 'Method' }, { key: 'rmse', label: 'RMSE', num: true, digits: 2 },
                { key: 'mae', label: 'MAE', num: true, digits: 2 }]}
              option={{
                ...base(p), grid: { left: 110, right: 50, top: 6, bottom: 24 },
                xAxis: { type: 'value', ...axisStyle(p) },
                yAxis: { type: 'category', inverse: true, data: m.methods.map((x) => x.method), ...axisStyle(p), axisLabel: { color: p.text2 } },
                series: [{ type: 'bar', barMaxWidth: 16, data: m.methods.map((x, i) => ({ value: x.rmse, itemStyle: barItem(i === 0 ? p.series[0] : p.axis, true) })),
                  label: { show: true, position: 'right', color: p.text2, formatter: (v: { value: unknown }) => Number(v.value).toFixed(2) } }],
              }} />
          ))}
        </div>
        <div className="grid g2" style={{ marginTop: 16 }}>
          <Card title="Activity label mapping">
            <DataTable rows={r.labels.mapping} height={300} cols={[{ key: 'activity_raw', label: 'As exported' },
              { key: 'activity', label: 'Mapped to' }, { key: 'count', label: 'Workouts', num: true }]} />
          </Card>
          <Recovery items={[
            { label: 'Duplicate re-syncs found', value: `${r.duplicates.found} of ${r.duplicates.true}`, ok: r.duplicates.recall === 1 },
            { label: 'Session types matching the truth', value: fmt.pct(r.sessions.accuracy), ok: r.sessions.accuracy > 0.99 },
            { label: 'Workouts after cleaning', value: `${fmt.n(r.clean.workouts)} of ${fmt.n(r.raw.workouts)}` },
          ]} />
        </div>
      </>
    )}</Report>
  );
}
