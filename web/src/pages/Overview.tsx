import { Link } from 'react-router-dom';
import { useGet } from '../api/client';
import { Card, ChartCard, DataTable, ErrorBox, Loading, PageHead, SectionTitle, Tile } from '../components/ui';
import { axisStyle, barItem, base, fmt, usePalette } from '../theme/chart';

interface Summary {
  generated_at: string;
  timings_s: Record<string, number>;
  dataset: { users: number; workouts: number; raw_workouts: number };
  recovery: Record<string, unknown>;
  syllabus: { unit: string; title: string; page: string; mining: string }[];
}
interface DatasetSummary { tables: Record<string, { rows: number; columns: string[] }> }

const PAGE: Record<string, string> = {
  preprocess: '/preprocess', olap: '/olap', association: '/association', classification: '/classification',
  clustering: '/clustering', outliers: '/outliers', sequences: '/sequences',
};

function show(v: unknown): string {
  if (Array.isArray(v)) return v.map(show).join(' / ');
  if (typeof v === 'number') return v <= 1 && v >= 0 && !Number.isInteger(v) ? fmt.pct(v) : fmt.n(v, 2);
  return v == null ? '–' : String(v);
}

export default function Overview() {
  const p = usePalette();
  const s = useGet<Summary>('/api/summary');
  const d = useGet<DatasetSummary>('/api/dataset/summary');
  if (s.error) return <ErrorBox error={s.error} />;
  if (!s.data) return <Loading />;
  const sum = s.data;
  const rec = sum.recovery;
  const timings = Object.entries(sum.timings_s).map(([step, sec]) => ({ step, sec }));
  const recRows = Object.entries(rec).map(([check, value]) => ({ check, value: show(value) }));

  return (
    <>
      <PageHead title="Smart fitness workout analytics">
        A Strava/Fitbit-style workout log mined end to end: what exercises go together, who is fit, which routes
        are popular, and which sensors or profiles are lying. Every unit of the data mining syllabus runs on the
        same synthetic dataset, which has known (planted) answers so each result can be scored.
      </PageHead>

      <div className="grid g4">
        <Tile label="Users" value={fmt.n(sum.dataset.users)} sub="incl. 10 cloned accounts" />
        <Tile label="Workouts (clean)" value={fmt.n(sum.dataset.workouts)}
          sub={`${fmt.n(sum.dataset.raw_workouts - sum.dataset.workouts)} duplicates removed`} />
        <Tile label="Planted patterns recovered" value={String(rec['U3 planted exercise rules recovered'])}
          sub="exercise co-occurrence rules" />
        <Tile label="Library cross-checks" value={String(rec['Verification checks passed'] ?? '–')}
          sub="from-scratch vs sklearn / scipy / mlxtend" />
      </div>

      <SectionTitle title="Syllabus map" sub="each unit has its own page, with live re-runs" />
      <div className="grid g3">
        {sum.syllabus.map((u) => (
          <Link key={u.unit} to={PAGE[u.page]} style={{ textDecoration: 'none', color: 'inherit' }}>
            <Card title={<><span className="mono muted">{u.unit}</span> {u.title}</>}>
              <div className="note">{u.mining}</div>
            </Card>
          </Link>
        ))}
        <Link to="/verify" style={{ textDecoration: 'none', color: 'inherit' }}>
          <Card title={<><span className="mono muted">✓</span> Verification</>}>
            <div className="note">Every hand-written algorithm checked against a library implementation on this data.</div>
          </Card>
        </Link>
      </div>

      <SectionTitle title="What the mining recovered" sub={`pipeline run ${sum.generated_at.replace('T', ' ')}`} />
      <div className="grid g2">
        <Card title="Recovery against planted ground truth">
          <DataTable rows={recRows} cols={[
            { key: 'check', label: 'Check', wrap: true },
            { key: 'value', label: 'Result', num: true },
          ]} />
        </Card>
        <ChartCard title="Pipeline time per step" sub="seconds, full run on one laptop core"
          table={timings} cols={[{ key: 'step', label: 'Step' }, { key: 'sec', label: 'Seconds', num: true, digits: 1 }]}
          option={{
            ...base(p),
            grid: { left: 190, right: 40, top: 8, bottom: 28 },
            xAxis: { type: 'value', ...axisStyle(p), name: 's' },
            yAxis: { type: 'category', data: timings.map((t) => t.step).reverse(), ...axisStyle(p),
              axisLabel: { color: p.text2, fontSize: 12 } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
            series: [{
              type: 'bar', barMaxWidth: 18, data: timings.map((t) => t.sec).reverse(),
              itemStyle: barItem(p.series[0], true),
              label: { show: true, position: 'right', color: p.text2, formatter: '{c}s' },
            }],
          }} />
      </div>

      <SectionTitle title="Database" sub="raw app tables, clean tables, star schema and mining outputs" />
      {d.data ? (
        <Card>
          <DataTable rows={Object.entries(d.data.tables).map(([t, v]) => ({ table: t, rows: v.rows,
            columns: v.columns.join(', ') }))} cols={[
            { key: 'table', label: 'Table', render: (r) => <code>{r.table}</code> },
            { key: 'rows', label: 'Rows', num: true },
            { key: 'columns', label: 'Columns', wrap: true },
          ]} />
        </Card>
      ) : d.error ? <ErrorBox error={d.error} /> : <Loading />}
    </>
  );
}
