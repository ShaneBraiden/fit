import { useGet } from '../api/client';
import { Card, DataTable, ErrorBox, Loading, PageHead, Status, Tile } from '../components/ui';
import { fmt } from '../theme/chart';

interface Row { unit: string; algorithm: string; reference: string; metric: string; value: number; pass: boolean;
  ours_ms: number; ref_ms: number; note: string }

export default function Verification() {
  const { data, error } = useGet<{ rows: Row[]; passed: number; total: number }>('/api/verify');
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const units = Array.from(new Set(data.rows.map((r) => r.unit)));
  return (
    <>
      <PageHead title="Verification against library implementations">
        Every algorithm in this project is written from scratch in NumPy. Each one is re-run here on the project's own
        data next to a reference implementation (scikit-learn, SciPy, mlxtend, or exhaustive search where no library
        has it) and must agree within tolerance. The same comparisons run as unit tests (<code>pytest server/tests</code>)
        on textbook examples.
      </PageHead>
      <div className="grid g4">
        <Tile label="Checks passed" value={`${data.passed} / ${data.total}`} sub="on the project dataset" />
        {units.slice(0, 3).map((u) => {
          const rows = data.rows.filter((r) => r.unit === u);
          return <Tile key={u} label={`${u} checks`} value={`${rows.filter((r) => r.pass).length} / ${rows.length}`}
            sub={rows.map((r) => r.algorithm).join(', ')} />;
        })}
      </div>
      <Card title="All checks" sub="runtimes are single runs on this machine; the point is agreement, not speed">
        <DataTable rows={data.rows as unknown as Record<string, unknown>[]} height={720} cols={[
          { key: 'pass', label: 'Status', render: (r) => <Status ok={r.pass as boolean} /> },
          { key: 'unit', label: 'Unit' }, { key: 'algorithm', label: 'Our algorithm' }, { key: 'reference', label: 'Reference' },
          { key: 'metric', label: 'Agreement measure' },
          { key: 'value', label: 'Value', num: true, render: (r) => fmt.n(r.value as number, Math.abs(r.value as number) < 0.01 && r.value !== 0 ? 8 : 4) },
          { key: 'ours_ms', label: 'Ours ms', num: true, digits: 1 }, { key: 'ref_ms', label: 'Ref ms', num: true, digits: 1 },
          { key: 'note', label: 'Note', wrap: true }]} />
      </Card>
    </>
  );
}
