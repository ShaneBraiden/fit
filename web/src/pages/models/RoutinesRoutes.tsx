import MapView from '../../components/MapView';
import { Card, DataTable, Legend, PageHead, Recovery, SectionTitle, Tile } from '../../components/ui';
import { fmt, usePalette } from '../../theme/chart';
import { Report } from './shared';

interface RR {
  sequences: { params: { min_support: number; max_gap: number }; n_sequences: number; n_patterns: number;
    patterns: { text: string; support: number; elements: number }[]; planted: { text: string; support: number | null; found: boolean }[] };
  routes: { params: { eps_m: number; min_samples: number; resample_points: number }; n_tracks: number; n_clusters: number; noise: number;
    clusters: { cluster: number; size: number; landmark: string; track: number[][]; purity: number }[];
    evaluation: { planted_routes: number; routes_found: number; purity: number; popular_recall: number } };
  segmentation: { n_runs: number; boundary_precision: number; boundary_recall: number; boundary_f1: number; phase_accuracy: number;
    interval_detection_accuracy: number };
}

export default function RoutinesRoutesPage() {
  const p = usePalette();
  return (
    <Report<RR> name="routines_routes">{(r) => {
      const s = r.sequences, ro = r.routes, sg = r.segmentation;
      return (
        <>
          <PageHead title="Routines & routes">
            Weekly routines come from GSP over day-ordered sequences of session types (one sequence per user-week, max gap{' '}
            {s.params.max_gap} days). Popular routes come from DBSCAN on the Hausdorff distance between GPS tracks. Runs are split into
            phases by binary segmentation of the speed profile.
          </PageHead>
          <div className="grid g4">
            <Tile label="Routines found" value={`${s.planted.filter((x) => x.found).length} / ${s.planted.length}`} sub={`${s.n_patterns} patterns in ${fmt.n(s.n_sequences)} user-weeks`} />
            <Tile label="Popular routes found" value={`${ro.evaluation.routes_found} / ${ro.evaluation.planted_routes}`} sub={`${ro.n_clusters} clusters, purity ${fmt.pct(ro.evaluation.purity)}`} />
            <Tile label="Run phase boundaries (F1)" value={sg.boundary_f1.toFixed(3)} sub={`precision ${sg.boundary_precision.toFixed(3)} · recall ${sg.boundary_recall.toFixed(3)}`} />
            <Tile label="Interval runs recognised" value={fmt.pct(sg.interval_detection_accuracy)} sub={`${sg.n_runs} runs checked`} />
          </div>
          <SectionTitle title="Weekly routines (GSP)" sub={`min support ${fmt.pct(s.params.min_support)}`} />
          <div className="grid g2">
            <Card title="Longest frequent patterns">
              <DataTable rows={s.patterns} height={320} cols={[{ key: 'text', label: 'Pattern', wrap: true },
                { key: 'elements', label: 'Steps', num: true }, { key: 'support', label: 'Support', num: true, pct: true }]} />
            </Card>
            <Recovery items={s.planted.map((x) => ({ label: x.text, value: x.support == null ? '–' : fmt.pct(x.support), ok: x.found }))} />
          </div>
          <SectionTitle title="Popular routes (Hausdorff + DBSCAN)" sub={`ε ${ro.params.eps_m} m, MinPts ${ro.params.min_samples}, ${ro.params.resample_points} points per track`} />
          <div className="grid g2">
            <Card title="Route clusters" sub={`${ro.n_tracks} tracks, ${ro.noise} left as noise (personal loops)`}>
              <MapView height={380} tracks={ro.clusters.map((c, i) => ({ id: c.cluster, points: c.track as [number, number][],
                color: p.series[i % 8], weight: 4, label: `${c.landmark} · ${c.size} tracks` }))} />
              <Legend items={ro.clusters.map((c, i) => ({ label: `${c.landmark} (${c.size})`, color: p.series[i % 8], line: true }))} />
            </Card>
            <Recovery items={[
              { label: 'Planted routes recovered', value: `${ro.evaluation.routes_found} of ${ro.evaluation.planted_routes}`, ok: ro.evaluation.routes_found === ro.evaluation.planted_routes },
              { label: 'Popular-route tracks put in the right cluster', value: fmt.pct(ro.evaluation.popular_recall), ok: ro.evaluation.popular_recall > 0.9 },
              { label: 'Run phase labels matching the truth', value: fmt.pct(sg.phase_accuracy), ok: sg.phase_accuracy > 0.9 },
            ]} />
          </div>
        </>
      );
    }}</Report>
  );
}
