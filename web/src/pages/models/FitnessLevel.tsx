import { Card, Chart, ChartCard, DataTable, Legend, PageHead, Recovery, SectionTitle, Tile } from '../../components/ui';
import { axisStyle, base, fmt, Palette, usePalette } from '../../theme/chart';
import { heatmapOption, hbarOption, Report } from './shared';

interface TreeNode { name: string; n: number; dist: Record<string, number>; class: string; split?: string; gain?: number; children?: TreeNode[] }
interface Level {
  n_users: number; n_labelled: number; class_counts: Record<string, number>; features: string[];
  params: { max_depth: number; min_samples_split: number };
  cv: { accuracy: number; macro: { precision: number; recall: number; f1: number }; fold_accuracy: number[]; confusion: number[][];
    labels: string[]; per_class: { class: string; precision: number; recall: number; f1: number; support: number }[];
    roc: { class: string; auc: number; fpr: number[]; tpr: number[] }[] };
  baseline: { rule: string; accuracy: number };
  hidden_truth: { n: number; accuracy: number; macro_f1: number; confusion: number[][]; labels: string[] };
  depth_sweep: { depth: number; cv_accuracy: number; train_accuracy: number }[];
  tree: { tree: TreeNode; rules: { if: string[]; then: string; n: number; confidence: number }[];
    stats: { nodes: number; leaves: number; depth: number }; importance: { feature: string; importance: number }[] };
}

const levelColors = (p: Palette): Record<string, string> => ({ Beginner: p.seq[1], Intermediate: p.seq[3], Advanced: p.seq[4], Elite: p.seq[6] });

function toTree(n: TreeNode, colors: Record<string, string>, p: Palette): Record<string, unknown> {
  return {
    name: n.split ? `${n.name === 'root' ? '' : n.name + '  '}${n.split}?` : `${n.name}  ⇒ ${n.class}`, value: n.n,
    itemStyle: { color: n.split ? p.axis : colors[n.class] ?? p.series[0], borderColor: p.surface },
    children: (n.children ?? []).map((c) => toTree(c, colors, p)),
    tip: `${n.n} users · ${Object.entries(n.dist).map(([k, v]) => `${k} ${v}`).join(', ')}${n.gain != null ? ` · gain ${n.gain}` : ''}`,
  };
}

export default function FitnessLevel() {
  const p = usePalette();
  const colors = levelColors(p);
  return (
    <Report<Level> name="fitness_level">{(r) => {
      const confusion = (M: number[][], labels: string[]) => heatmapOption(p, M, labels, labels, { xName: 'predicted', yName: 'actual',
        tip: (a, b, v) => `actual <b>${a}</b>, predicted <b>${b}</b>: ${v} users` });
      const h = Math.max(340, r.tree.stats.leaves * 26);
      return (
        <>
          <PageHead title="Fitness level: C4.5 decision tree">
            {fmt.n(r.n_labelled)} of {fmt.n(r.n_users)} training users have a coach assessment (with ~10% label noise). A C4.5 tree
            (gain ratio, numeric thresholds, depth ≤ {r.params.max_depth}) learns the level from {r.features.length} attributes. In the app it
            runs on each user's own profile and last 8 weeks of workouts; missing values (e.g. no heart rate) follow the larger branch.
          </PageHead>
          <div className="grid g4">
            <Tile label="CV accuracy (5-fold)" value={fmt.pct(r.cv.accuracy)} sub={`folds: ${r.cv.fold_accuracy.map((a) => fmt.pct(a, 0)).join(' · ')}`} />
            <Tile label="Macro F1" value={r.cv.macro.f1.toFixed(3)} sub={`precision ${r.cv.macro.precision.toFixed(3)} · recall ${r.cv.macro.recall.toFixed(3)}`} />
            <Tile label="Baseline" value={fmt.pct(r.baseline.accuracy)} sub={r.baseline.rule} />
            <Tile label="Unassessed users vs hidden truth" value={fmt.pct(r.hidden_truth.accuracy)} sub={`${r.hidden_truth.n} users`} />
          </div>
          <div className="grid g3" style={{ marginTop: 16 }}>
            <ChartCard title="Confusion matrix" sub="out-of-fold predictions" height={280} option={confusion(r.cv.confusion, r.cv.labels)} />
            <ChartCard title="ROC, one level vs rest" sub="AUC in the legend" height={280} option={{
              ...base(p), legend: { ...base(p).legend, data: r.cv.roc.map((x) => `${x.class} (${x.auc.toFixed(2)})`) },
              grid: { left: 44, right: 14, top: 48, bottom: 36 },
              xAxis: { type: 'value', min: 0, max: 1, ...axisStyle(p), name: 'false positive rate', nameLocation: 'middle', nameGap: 22 },
              yAxis: { type: 'value', min: 0, max: 1, ...axisStyle(p), name: 'TPR' },
              series: [...r.cv.roc.map((x) => ({ name: `${x.class} (${x.auc.toFixed(2)})`, type: 'line' as const, showSymbol: false,
                data: x.fpr.map((f, i) => [f, x.tpr[i]]), lineStyle: { width: 2, color: colors[x.class] }, itemStyle: { color: colors[x.class] } })),
                { type: 'line' as const, data: [[0, 0], [1, 1]], showSymbol: false, lineStyle: { width: 1, color: p.axis }, silent: true }],
            }} />
            <Card title="Per-level metrics">
              <DataTable rows={r.cv.per_class} cols={[{ key: 'class', label: 'Level' }, { key: 'precision', label: 'Precision', num: true, digits: 3 },
                { key: 'recall', label: 'Recall', num: true, digits: 3 }, { key: 'f1', label: 'F1', num: true, digits: 3 },
                { key: 'support', label: 'Users', num: true }]} />
              <div className="note" style={{ marginTop: 8 }}>Most errors are between neighbouring levels.</div>
            </Card>
          </div>
          <SectionTitle title="The tree" sub={`${r.tree.stats.nodes} nodes, ${r.tree.stats.leaves} leaves; shown at depth 4`} />
          <div className="grid g3">
            <Card className="span2" title="Splits (grey) and leaves (coloured by level)" sub="hover a node for its class counts">
              <Chart height={h} option={{
                ...base(p),
                tooltip: { ...base(p).tooltip, formatter: (x: unknown) => { const d = (x as { data: { name: string; tip: string } }).data; return `<b>${d.name}</b><br/>${d.tip}`; } },
                series: [{ type: 'tree', data: [toTree(r.tree.tree, colors, p)], orient: 'LR', top: 10, bottom: 10, left: 90, right: 190,
                  symbolSize: 9, initialTreeDepth: -1, lineStyle: { color: p.axis, width: 1, curveness: 0.4 },
                  label: { color: p.text2, fontSize: 11, position: 'left', verticalAlign: 'middle', align: 'right', distance: 6 },
                  leaves: { label: { position: 'right', align: 'left', color: p.text } } }],
              }} />
              <Legend items={Object.entries(colors).map(([k, v]) => ({ label: k, color: v }))} />
            </Card>
            <ChartCard title="Attribute importance" sub="share of total gain" height={340}
              option={hbarOption(p, r.tree.importance.map((x) => x.feature), r.tree.importance.map((x) => x.importance), { pct: true, left: 120 })}
              table={r.tree.importance} cols={[{ key: 'feature', label: 'Attribute' }, { key: 'importance', label: 'Importance', num: true, pct: true }]} />
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <ChartCard title="Choosing the depth" sub="training vs cross-validated accuracy; the gap is overfitting" height={260}
              table={r.depth_sweep} cols={[{ key: 'depth', label: 'Depth', num: true }, { key: 'train_accuracy', label: 'Training', num: true, pct: true },
                { key: 'cv_accuracy', label: 'CV', num: true, pct: true }]}
              option={{
                ...base(p), legend: { ...base(p).legend, data: ['training', 'cross-validated'] },
                xAxis: { type: 'category', data: r.depth_sweep.map((d) => d.depth), ...axisStyle(p), name: 'max depth', nameLocation: 'middle', nameGap: 24 },
                yAxis: { type: 'value', min: 0.4, max: 1, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
                tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => fmt.pct(v as number) },
                series: [
                  { name: 'training', type: 'line', data: r.depth_sweep.map((d) => d.train_accuracy), lineStyle: { color: p.series[1] }, itemStyle: { color: p.series[1] } },
                  { name: 'cross-validated', type: 'line', data: r.depth_sweep.map((d) => d.cv_accuracy), lineStyle: { color: p.series[0] }, itemStyle: { color: p.series[0] } },
                ],
              }} />
            <ChartCard title="Unassessed users vs their hidden level" sub={`${r.hidden_truth.n} users the tree never saw a label for`} height={260}
              option={confusion(r.hidden_truth.confusion, r.hidden_truth.labels)} />
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <Card title="Rules read off the tree" sub="one IF-THEN rule per leaf, largest first">
              <DataTable rows={r.tree.rules.map((x) => ({ ...x, if: x.if.join('  AND  ') }))} height={300} cols={[
                { key: 'if', label: 'IF', wrap: true }, { key: 'then', label: 'THEN' }, { key: 'n', label: 'Users', num: true },
                { key: 'confidence', label: 'Confidence', num: true, pct: true }]} />
            </Card>
            <Recovery items={[
              { label: 'CV accuracy vs majority-class baseline', value: `${fmt.pct(r.cv.accuracy)} vs ${fmt.pct(r.baseline.accuracy)}`, ok: r.cv.accuracy > r.baseline.accuracy + 0.2 },
              { label: 'Accuracy on unassessed users', value: fmt.pct(r.hidden_truth.accuracy), ok: r.hidden_truth.accuracy > 0.6,
                note: '~10% of training labels are shifted one level, which caps accuracy' },
              { label: 'Assessed users per level', value: Object.entries(r.class_counts).map(([k, v]) => `${k} ${v}`).join(' · ') },
            ]} />
          </div>
        </>
      );
    }}</Report>
  );
}
