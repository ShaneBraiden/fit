import { Card, ChartCard, DataTable, PageHead, Recovery, Tile } from '../../components/ui';
import { fmt, usePalette } from '../../theme/chart';
import { heatmapOption, Report } from './shared';

interface Method { flagged: number; precision: number; recall: number; f1: number; ms: number }
interface Checks {
  n_workouts: number; n_true_faults: number; features: string[]; fault_counts: Record<string, number>;
  methods: Record<string, Method>; recall_matrix: Record<string, Record<string, number>>;
  users: { evaluation: { flagged: number; precision: number; recall: number; per_type: Record<string, { n: number; detected: number }> };
    flagged: { user_id: number; reasons: string[] }[] };
}

const MEMBER: Record<string, string> = { rules: 'Domain rules', duplicates: 'Stream fingerprints', iqr: 'IQR fences (k = 3)',
  iforest: 'Isolation Forest (top 3%)', ensemble: 'Ensemble (what the app uses)' };

export default function DataChecksPage() {
  const p = usePalette();
  return (
    <Report<Checks> name="data_checks">{(r) => {
      const ens = r.methods.ensemble;
      const order = ['rules', 'duplicates', 'iqr', 'iforest', 'ensemble'];
      const faults = Object.keys(r.fault_counts);
      return (
        <>
          <PageHead title="Data checks: rules + fingerprints + IQR & Isolation Forest">
            Every uploaded workout is turned into {r.features.length} features from its heart-rate and GPS stream and checked within its
            activity. It is flagged if a domain rule fires (e.g. a "run" over 25 km/h, a 500 m GPS jump in 15 s), if its stream fingerprint
            matches another user's, or if IQR fences and Isolation Forest both call it an outlier. Flagged workouts are kept but
            don't count towards the user's stats.
          </PageHead>
          <div className="grid g4">
            <Tile label="Workouts checked" value={fmt.n(r.n_workouts)} sub={`${fmt.n(r.n_true_faults)} planted faults`} />
            <Tile label="Precision" value={fmt.pct(ens.precision)} sub={`${fmt.n(ens.flagged)} flagged`} />
            <Tile label="Recall" value={fmt.pct(ens.recall)} sub={`F1 ${ens.f1.toFixed(3)}`} />
            <Tile label="Spoofed profiles" value={`${r.users.evaluation.flagged} flagged`}
              sub={`precision ${fmt.pct(r.users.evaluation.precision)} · recall ${fmt.pct(r.users.evaluation.recall)}`} />
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <Card title="The ensemble and its members" sub="each member alone, then combined">
              <DataTable rows={order.map((m) => ({ method: MEMBER[m], ...r.methods[m] }))} cols={[{ key: 'method', label: 'Check' },
                { key: 'flagged', label: 'Flagged', num: true }, { key: 'precision', label: 'Precision', num: true, pct: true },
                { key: 'recall', label: 'Recall', num: true, pct: true }, { key: 'f1', label: 'F1', num: true, digits: 3 }]} />
              <div className="note" style={{ marginTop: 8 }}>The members miss different faults, so combining them catches almost all.</div>
            </Card>
            <ChartCard title="Recall per fault type" sub="share of each planted fault caught" height={300}
              option={heatmapOption(p, order.map((m) => faults.map((f) => r.recall_matrix[m]?.[f] ?? 0)), order.map((m) => MEMBER[m]), faults,
                { pct: true, left: 190 })} />
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <Card title="Flagged profiles" sub="physiological limits, consistency models and cloned accounts">
              <DataTable rows={r.users.flagged.map((u) => ({ user: u.user_id, reasons: u.reasons.join('; ') }))} height={300}
                cols={[{ key: 'user', label: 'User', num: true }, { key: 'reasons', label: 'Why', wrap: true }]} />
            </Card>
            <Recovery items={Object.entries(r.users.evaluation.per_type).map(([k, v]) => ({
              label: `Spoofed profiles: ${k.replace(/_/g, ' ')}`, value: `${v.detected} / ${v.n}`, ok: v.detected === v.n }))} />
          </div>
        </>
      );
    }}</Report>
  );
}
