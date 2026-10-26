import { Link } from 'react-router-dom';
import { ChartCard, DataTable, PageHead, SectionTitle, Tile } from '../../components/ui';
import { axisStyle, barItem, base, fmt, usePalette } from '../../theme/chart';
import { Report } from './shared';

interface Summary {
  generated_at: string;
  timings_s: Record<string, number>;
  dataset: { users: number; workouts: number; raw_workouts: number };
  recovery: Record<string, unknown>;
}

const FEATURES = [
  { to: '/models/cleaning', title: 'Data cleaning', what: 'Fixes the raw training data: labels, units, re-sync duplicates; fills missing values with kNN imputation.' },
  { to: '/models/fitness-level', title: 'Fitness level', what: 'C4.5 decision tree: Beginner to Elite from profile and the last 8 weeks of workouts.' },
  { to: '/models/training-style', title: 'Training style', what: 'k-means++ clusters of training behaviour; each user gets the nearest centre.' },
  { to: '/models/suggestions', title: 'Try next', what: 'FP-Growth association rules over the exercises done together in a workout.' },
  { to: '/models/data-checks', title: 'Data checks', what: 'Domain rules + stream fingerprints + IQR fences and Isolation Forest agreeing.' },
  { to: '/models/routines-routes', title: 'Routines & routes', what: 'GSP weekly routines; DBSCAN on Hausdorff distances for routes; change-point run phases.' },
];

function show(v: unknown): string {
  if (Array.isArray(v)) return v.map(show).join(' / ');
  if (typeof v === 'number') return v <= 1 && v >= 0 && !Number.isInteger(v) ? fmt.pct(v) : fmt.n(v, 2);
  return v == null ? '–' : String(v);
}

export default function ModelsOverview() {
  const p = usePalette();
  return (
    <Report<Summary> name="summary">{(s) => {
      const timings = Object.entries(s.timings_s).map(([step, sec]) => ({ step, sec }));
      return (
        <>
          <PageHead title="How the models work">
            Admin view. The app's predictions come from models trained on a synthetic population whose patterns were planted on
            purpose, so each model can be scored against the known answer. Users never see this page.
          </PageHead>
          <div className="grid g4">
            <Tile label="Training users" value={fmt.n(s.dataset.users)} sub="synthetic, incl. 10 cloned accounts" />
            <Tile label="Training workouts" value={fmt.n(s.dataset.workouts)} sub={`${fmt.n(s.dataset.raw_workouts - s.dataset.workouts)} duplicates removed`} />
            <Tile label="Library cross-checks" value={String(s.recovery['Verification checks passed'] ?? '–')} sub="from-scratch vs sklearn / scipy / mlxtend" />
            <Tile label="Trained" value={s.generated_at.slice(0, 10)} sub={s.generated_at.slice(11, 16)} />
          </div>
          <SectionTitle title="One model per feature" />
          <div className="grid g3">
            {FEATURES.map((f) => (
              <Link key={f.to} to={f.to} style={{ textDecoration: 'none', color: 'inherit' }}>
                <section className="card"><h3>{f.title}</h3><div className="note" style={{ marginTop: 6 }}>{f.what}</div></section>
              </Link>
            ))}
          </div>
          <SectionTitle title="Scores against the planted answers" />
          <div className="grid g2">
            <section className="card">
              <DataTable rows={Object.entries(s.recovery).map(([check, value]) => ({ check, value: show(value) }))}
                cols={[{ key: 'check', label: 'Check', wrap: true }, { key: 'value', label: 'Result', num: true }]} />
            </section>
            <ChartCard title="Training time per step" sub="seconds, one full run"
              table={timings} cols={[{ key: 'step', label: 'Step' }, { key: 'sec', label: 'Seconds', num: true, digits: 1 }]}
              option={{
                ...base(p), grid: { left: 210, right: 40, top: 8, bottom: 28 },
                xAxis: { type: 'value', ...axisStyle(p), name: 's' },
                yAxis: { type: 'category', data: timings.map((t) => t.step).reverse(), ...axisStyle(p), axisLabel: { color: p.text2 } },
                tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
                series: [{ type: 'bar', barMaxWidth: 18, data: timings.map((t) => t.sec).reverse(), itemStyle: barItem(p.series[0], true),
                  label: { show: true, position: 'right', color: p.text2, formatter: '{c}s' } }],
              }} />
          </div>
        </>
      );
    }}</Report>
  );
}
