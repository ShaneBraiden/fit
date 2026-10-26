import { useState } from 'react';
import { useGet, useRun } from '../api/client';
import { Card, Chart, ChartCard, DataTable, ErrorBox, Legend, Loading, PageHead, Recovery, SectionTitle, Select, Slider, Tile } from '../components/ui';
import { axisStyle, barItem, base, fmt, Palette, usePalette, valueLabel } from '../theme/chart';

interface PerClass { class: string; precision: number; recall: number; f1: number; support: number }
interface Eval {
  model: string; label: string; accuracy: number; macro: { precision: number; recall: number; f1: number };
  weighted: { f1: number }; ms: number; fold_accuracy: number[]; per_class: PerClass[]; confusion: number[][];
  labels: string[]; roc: { class: string; auc: number; fpr: number[]; tpr: number[] }[];
}
interface TreeNode { name: string; n: number; dist: Record<string, number>; class: string; split?: string; gain?: number;
  children?: TreeNode[]; truncated?: boolean }
interface TreeView { algorithm: string; tree: TreeNode; rules: { if: string[]; then: string; n: number; confidence: number }[];
  stats: { nodes: number; leaves: number; depth: number }; importance: { feature: string; importance: number }[];
  pruned_subtrees?: number }
interface Hidden { n: number; accuracy: number; macro_f1: number; confusion: number[][]; labels: string[] }
interface U4 {
  n_users: number; n_labelled: number; class_counts: Record<string, number>; features: string[];
  comparison: Eval[]; details: Record<string, Eval>; best_model: string; hidden_truth: Hidden;
  k_sweep: { k: number; accuracy: number }[]; depth_sweep: { depth: number; cv_accuracy: number; train_accuracy: number }[];
  tree: TreeView;
}
type Live = Eval & { hidden_truth: Hidden; tree?: TreeView };
interface Params { model: string; max_depth: number; min_samples_split: number; prune: boolean; k: number;
  weights: 'uniform' | 'distance'; folds: number }

const MODELS = [
  { value: 'id3', label: 'ID3 (information gain)' }, { value: 'c45', label: 'C4.5 (gain ratio)' },
  { value: 'cart', label: 'CART (Gini)' }, { value: 'nb', label: 'Naive Bayes' }, { value: 'knn', label: 'k-NN' },
];

function levelColors(p: Palette): Record<string, string> {
  return { Beginner: p.seq[1], Intermediate: p.seq[3], Advanced: p.seq[4], Elite: p.seq[6] };
}

function confusionOption(p: Palette, M: number[][], labels: string[]) {
  const data: [number, number, number][] = [];
  const rowSum = M.map((r) => r.reduce((a, b) => a + b, 0) || 1);
  M.forEach((r, i) => r.forEach((v, j) => data.push([j, i, v])));
  const max = Math.max(...M.flat());
  return {
    ...base(p), grid: { left: 100, right: 16, top: 10, bottom: 50 },
    xAxis: { type: 'category' as const, data: labels, ...axisStyle(p), name: 'predicted', nameLocation: 'middle' as const, nameGap: 30,
      axisLabel: { color: p.text2 } },
    yAxis: { type: 'category' as const, data: labels, inverse: true, ...axisStyle(p), name: 'actual', axisLabel: { color: p.text2 } },
    visualMap: { min: 0, max, show: false, inRange: { color: [p.seq[0], p.seq[6]] } },
    tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
      const v = (x as { value: [number, number, number] }).value;
      return `actual <b>${labels[v[1]]}</b>, predicted <b>${labels[v[0]]}</b><br/>${v[2]} users (${fmt.pct(v[2] / rowSum[v[1]])} of row)`;
    } },
    series: [{ type: 'heatmap' as const, data, itemStyle: { borderColor: p.surface, borderWidth: 2 },
      label: { show: true, color: p.text, formatter: (x: unknown) => String((x as { value: number[] }).value[2]),
        textBorderColor: p.surface, textBorderWidth: 2 } }],
  };
}

function toEchartsTree(n: TreeNode, colors: Record<string, string>, p: Palette): Record<string, unknown> {
  const label = n.split ? `${n.name === 'root' ? '' : n.name + '  '}${n.split}?` : `${n.name}  ⇒ ${n.class}`;
  return {
    name: label, value: n.n,
    itemStyle: { color: n.split ? p.axis : colors[n.class] ?? p.series[0], borderColor: p.surface },
    children: (n.children ?? []).map((c) => toEchartsTree(c, colors, p)),
    tip: `${n.n} users · ${Object.entries(n.dist).map(([k, v]) => `${k} ${v}`).join(', ')}${n.gain != null ? ` · gain ${n.gain}` : ''}`,
  };
}

export default function Classification() {
  const p = usePalette();
  const rep = useGet<U4>('/api/classify/report');
  const live = useRun<Params, Live>('/api/classify/run');
  const [prm, setPrm] = useState<Params>({ model: 'c45', max_depth: 6, min_samples_split: 10, prune: false, k: 7,
    weights: 'distance', folds: 5 });
  if (rep.error) return <ErrorBox error={rep.error} />;
  if (!rep.data) return <Loading />;
  const r = rep.data;
  const ev: Eval = live.data ?? r.details[r.best_model];
  const hidden = live.data?.hidden_truth ?? r.hidden_truth;
  const tree = live.data ? live.data.tree : r.tree;
  const colors = levelColors(p);
  const isTree = ['id3', 'c45', 'cart'].includes(prm.model);

  return (
    <>
      <PageHead code="U4" title="Classification: fitness level">
        {fmt.n(r.n_labelled)} of {fmt.n(r.n_users)} users have a fitness assessment (with ~10% label noise). Models
        learn the level from profile and training behaviour, are scored by stratified k-fold cross-validation, and
        then predict the unassessed users, whose hidden true level we can check.
      </PageHead>

      <div className="controls">
        <Select label="Model" value={prm.model} options={MODELS} onChange={(v) => setPrm({ ...prm, model: v })} />
        {isTree && <>
          <Slider label="max depth" value={prm.max_depth} min={1} max={12} step={1} onChange={(v) => setPrm({ ...prm, max_depth: v })} />
          <Slider label="min samples to split" value={prm.min_samples_split} min={2} max={80} step={2}
            onChange={(v) => setPrm({ ...prm, min_samples_split: v })} />
          <label className="check"><input type="checkbox" checked={prm.prune} onChange={(e) => setPrm({ ...prm, prune: e.target.checked })} />
            reduced-error pruning</label>
        </>}
        {prm.model === 'knn' && <>
          <Slider label="k" value={prm.k} min={1} max={41} step={2} onChange={(v) => setPrm({ ...prm, k: v })} />
          <Select label="Weights" value={prm.weights} onChange={(v) => setPrm({ ...prm, weights: v })}
            options={[{ value: 'distance', label: '1 / distance' }, { value: 'uniform', label: 'uniform' }]} />
        </>}
        <Slider label="folds" value={prm.folds} min={2} max={10} step={1} onChange={(v) => setPrm({ ...prm, folds: v })} />
        <button className="btn primary" disabled={live.loading} onClick={() => live.run(prm)}>
          {live.loading ? 'Cross-validating…' : 'Train & evaluate'}</button>
        {live.data && <button className="btn" onClick={() => live.setData(null)}>Reset</button>}
      </div>
      {live.error && <div className="error" style={{ marginBottom: 16 }}>{live.error}</div>}

      <div className={`grid g4 ${live.loading ? 'stale' : ''}`}>
        <Tile label={`${ev.label}: CV accuracy`} value={fmt.pct(ev.accuracy)}
          sub={`folds: ${ev.fold_accuracy.map((a) => fmt.pct(a, 0)).join(' · ')}`} />
        <Tile label="Macro F1" value={ev.macro.f1.toFixed(3)} sub={`precision ${ev.macro.precision.toFixed(3)} · recall ${ev.macro.recall.toFixed(3)}`} />
        <Tile label="Unassessed users vs hidden truth" value={fmt.pct(hidden.accuracy)} sub={`${hidden.n} users · macro F1 ${hidden.macro_f1.toFixed(3)}`} />
        <Tile label="Cross-validation time" value={`${fmt.n(ev.ms)} ms`} sub={`${ev.fold_accuracy.length} folds, train + predict`} />
      </div>

      <div className={`grid g3 ${live.loading ? 'stale' : ''}`} style={{ marginTop: 16 }}>
        <ChartCard title="Confusion matrix" sub="out-of-fold predictions" height={280}
          option={confusionOption(p, ev.confusion, ev.labels)} />
        <ChartCard title="ROC, one class vs rest" sub="area under each curve in the legend" height={280}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ev.roc.map((x) => `${x.class} (AUC ${x.auc.toFixed(2)})`) },
            grid: { left: 44, right: 14, top: 48, bottom: 36 },
            xAxis: { type: 'value', min: 0, max: 1, ...axisStyle(p), name: 'false positive rate', nameLocation: 'middle', nameGap: 22 },
            yAxis: { type: 'value', min: 0, max: 1, ...axisStyle(p), name: 'TPR' },
            tooltip: { ...base(p).tooltip, trigger: 'item' },
            series: [
              ...ev.roc.map((x) => ({ name: `${x.class} (AUC ${x.auc.toFixed(2)})`, type: 'line' as const, showSymbol: false,
                data: x.fpr.map((f, i) => [f, x.tpr[i]]), lineStyle: { width: 2, color: colors[x.class] },
                itemStyle: { color: colors[x.class] } })),
              { name: 'chance', type: 'line' as const, data: [[0, 0], [1, 1]], showSymbol: false,
                lineStyle: { width: 1, color: p.axis }, silent: true },
            ],
          }} />
        <Card title="Per-class metrics">
          <DataTable rows={ev.per_class as unknown as Record<string, unknown>[]} cols={[
            { key: 'class', label: 'Level', render: (x) => <span><i style={{ display: 'inline-block', width: 10, height: 10,
              borderRadius: 2, background: colors[x.class as string], marginRight: 6 }} />{x.class as string}</span> },
            { key: 'precision', label: 'Precision', num: true, digits: 3 }, { key: 'recall', label: 'Recall', num: true, digits: 3 },
            { key: 'f1', label: 'F1', num: true, digits: 3 }, { key: 'support', label: 'Users', num: true }]} />
          <div className="note" style={{ marginTop: 10 }}>Levels are ordered, so they use one blue ramp (light = Beginner, dark = Elite).
            Most errors are between neighbouring levels.</div>
        </Card>
      </div>

      {tree && isTree && (
        <>
          <SectionTitle title="The decision tree" sub={`${tree.algorithm.toUpperCase()} · ${tree.stats.nodes} nodes, ${tree.stats.leaves} leaves, depth ${tree.stats.depth}${tree.pruned_subtrees != null ? ` · ${tree.pruned_subtrees} subtrees pruned` : ''}${live.data ? '' : ' · shown at depth 4 for readability'}`} />
          <div className="grid g3">
            <Card className="span2" title="Splits (grey) and leaves (coloured by predicted level)" sub="hover a node for its class distribution">
              <TreeChart p={p} tree={tree} colors={colors} />
              <Legend items={Object.entries(colors).map(([k, v]) => ({ label: k, color: v }))} />
            </Card>
            <ChartCard title="Attribute importance" sub="share of total impurity reduction" height={340}
              option={{
                ...base(p), grid: { left: 120, right: 40, top: 6, bottom: 24 },
                xAxis: { type: 'value', ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
                yAxis: { type: 'category', inverse: true, data: tree.importance.map((x) => x.feature), ...axisStyle(p), axisLabel: { color: p.text2 } },
                tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => fmt.pct(v as number) },
                series: [{ type: 'bar', barMaxWidth: 12, data: tree.importance.map((x) => x.importance), itemStyle: barItem(p.series[0], true) }],
              }}
              table={tree.importance} cols={[{ key: 'feature', label: 'Attribute' }, { key: 'importance', label: 'Importance', num: true, pct: true }]} />
          </div>
          <Card title="Rules read off the tree" sub="IF-THEN rules, one per leaf, largest first">
            <DataTable rows={tree.rules.map((x) => ({ ...x, if: x.if.join('  AND  ') }))} height={300} cols={[
              { key: 'if', label: 'IF', wrap: true }, { key: 'then', label: 'THEN level' },
              { key: 'n', label: 'Users', num: true }, { key: 'confidence', label: 'Confidence', num: true, pct: true }]} />
          </Card>
        </>
      )}

      <SectionTitle title="Model comparison and tuning" sub="pipeline results, 5-fold CV" />
      <div className="grid g3">
        <ChartCard title="Macro F1 by model" sub={`best: ${r.details[r.best_model].label}`} height={260}
          option={{
            ...base(p), grid: { left: 120, right: 44, top: 6, bottom: 24 },
            xAxis: { type: 'value', min: 0, max: 1, ...axisStyle(p) },
            yAxis: { type: 'category', inverse: true, data: r.comparison.map((c) => c.label), ...axisStyle(p), axisLabel: { color: p.text2 } },
            tooltip: { ...base(p).tooltip, trigger: 'axis' },
            series: [{ type: 'bar', barMaxWidth: 16, data: r.comparison.map((c) => ({ value: c.macro.f1,
              itemStyle: barItem(c.model === r.best_model ? p.series[0] : p.axis, true) })),
              label: { show: true, position: 'right', color: p.text2, formatter: valueLabel((n) => n.toFixed(3)) } }],
          }}
          table={r.comparison.map((c) => ({ model: c.label, accuracy: c.accuracy, f1: c.macro.f1, ms: c.ms }))}
          cols={[{ key: 'model', label: 'Model' }, { key: 'accuracy', label: 'Accuracy', num: true, pct: true },
            { key: 'f1', label: 'Macro F1', num: true, digits: 3 }, { key: 'ms', label: 'ms', num: true }]} />
        <ChartCard title="Tree depth: training vs CV accuracy" sub="the gap that opens up is overfitting" height={260}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['training', 'cross-validated'] },
            xAxis: { type: 'category', data: r.depth_sweep.map((d) => d.depth), ...axisStyle(p), name: 'max depth', nameLocation: 'middle', nameGap: 24 },
            yAxis: { type: 'value', min: 0.5, max: 1, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => fmt.pct(v as number) },
            series: [
              { name: 'training', type: 'line', data: r.depth_sweep.map((d) => d.train_accuracy), symbolSize: 7,
                lineStyle: { width: 2, color: p.series[1] }, itemStyle: { color: p.series[1], borderColor: p.surface, borderWidth: 2 } },
              { name: 'cross-validated', type: 'line', data: r.depth_sweep.map((d) => d.cv_accuracy), symbolSize: 7,
                lineStyle: { width: 2, color: p.series[0] }, itemStyle: { color: p.series[0], borderColor: p.surface, borderWidth: 2 } },
            ],
          }}
          table={r.depth_sweep} cols={[{ key: 'depth', label: 'Depth', num: true }, { key: 'train_accuracy', label: 'Training', num: true, pct: true },
            { key: 'cv_accuracy', label: 'CV', num: true, pct: true }]} />
        <ChartCard title="k-NN: choosing k" sub="CV accuracy, distance-weighted votes" height={260}
          option={{
            ...base(p),
            xAxis: { type: 'category', data: r.k_sweep.map((d) => d.k), ...axisStyle(p), name: 'k', nameLocation: 'middle', nameGap: 24 },
            yAxis: { type: 'value', min: 0.5, max: 0.8, ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => fmt.pct(v as number) },
            series: [{ type: 'line', data: r.k_sweep.map((d) => d.accuracy), symbolSize: 7,
              lineStyle: { width: 2, color: p.series[0] }, itemStyle: { color: p.series[0], borderColor: p.surface, borderWidth: 2 } }],
          }}
          table={r.k_sweep} cols={[{ key: 'k', label: 'k', num: true }, { key: 'accuracy', label: 'CV accuracy', num: true, pct: true }]} />
      </div>

      <div className="grid g2" style={{ marginTop: 16 }}>
        <ChartCard title="Predictions for unassessed users vs their hidden level" sub={`${hidden.n} users the model never saw a label for`}
          height={260} option={confusionOption(p, hidden.confusion, hidden.labels)} />
        <Recovery items={[
          { label: 'Best model (macro F1, 5-fold CV)', value: `${r.details[r.best_model].label}: ${r.details[r.best_model].macro.f1.toFixed(3)}` },
          { label: 'Accuracy on unassessed users vs hidden true level', value: fmt.pct(r.hidden_truth.accuracy),
            ok: r.hidden_truth.accuracy > 0.6, note: 'labels carry ~10% noise, so ~90% is the practical ceiling' },
          { label: 'Class balance of assessed users', value: Object.entries(r.class_counts).map(([k, v]) => `${k} ${v}`).join(' · ') },
        ]} />
      </div>
    </>
  );
}

function TreeChart({ p, tree, colors }: { p: Palette; tree: TreeView; colors: Record<string, string> }) {
  const data = toEchartsTree(tree.tree, colors, p);
  const leaves = tree.stats.leaves;
  return (
    <div style={{ height: Math.max(340, leaves * 26) }}>
      <Chart option={{
        ...base(p),
        tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
          const d = (x as { data: { name: string; tip: string } }).data;
          return `<b>${d.name}</b><br/>${d.tip}`;
        } },
        series: [{
          type: 'tree', data: [data], orient: 'LR', top: 10, bottom: 10, left: 90, right: 190, symbolSize: 9,
          initialTreeDepth: -1, expandAndCollapse: true,
          lineStyle: { color: p.axis, width: 1, curveness: 0.4 },
          label: { color: p.text2, fontSize: 11, position: 'left', verticalAlign: 'middle', align: 'right', distance: 6 },
          leaves: { label: { position: 'right', align: 'left', color: p.text } },
        }],
      }} height={Math.max(340, leaves * 26)} />
    </div>
  );
}
