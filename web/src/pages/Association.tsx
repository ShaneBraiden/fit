import { useState } from 'react';
import { useGet, useRun } from '../api/client';
import { Card, ChartCard, DataTable, ErrorBox, Loading, PageHead, Recovery, SectionTitle, Select, Slider, Tile } from '../components/ui';
import { axisStyle, barItem, base, fmt, usePalette } from '../theme/chart';

interface Rule { antecedent: string[]; consequent: string[]; support: number; confidence: number; lift: number;
  leverage: number; conviction: number | null }
interface Level { k: number; candidates: number; pruned: number; counted: number; frequent: number }
interface Mined {
  params: { algorithm: string; min_support: number; min_confidence: number; min_lift: number };
  n_transactions: number; avg_basket: number; n_itemsets: number; by_size: Record<string, number>; n_closed: number;
  n_maximal: number; n_rules: number; ms_mine: number; ms_rules: number; stats: Level[] | Record<string, number>;
  items: { item: string; support: number }[]; itemsets: { items: string[]; support: number }[]; rules: Rule[];
  graph: { nodes: { id: string; kind: string; lift?: number; support?: number; confidence?: number }[];
    links: { source: string; target: string }[] };
  planted?: { rules: (Rule & { found: boolean; rank: number | null })[]; recovered: number; total: number };
}
interface Tree { name: string; value?: number; children?: Tree[] }
interface U3 {
  session: Mined; user_week: Mined;
  comparison: { same_itemsets: boolean; apriori_levels: Level[]; scaling: { min_support: number; itemsets: number;
    apriori_ms: number; fpgrowth_ms: number; apriori_candidates: number; fp_tree_nodes: number; conditional_trees: number }[] };
  fp_tree: Tree & { nodes: number; header: { item: string; support_count: number }[] };
}
interface Params { algorithm: 'apriori' | 'fpgrowth'; basket: 'session' | 'user_week'; min_support: number;
  min_confidence: number; min_lift: number }

const ruleText = (r: Rule) => `{${r.antecedent.join(', ')}} → {${r.consequent.join(', ')}}`;

export default function Association() {
  const p = usePalette();
  const rep = useGet<U3>('/api/association/report');
  const live = useRun<Params, Mined>('/api/association/run');
  const [prm, setPrm] = useState<Params>({ algorithm: 'fpgrowth', basket: 'session', min_support: 0.02,
    min_confidence: 0.6, min_lift: 1 });
  if (rep.error) return <ErrorBox error={rep.error} />;
  if (!rep.data) return <Loading />;
  const r = rep.data;
  const m = live.data ?? r.session;
  const levels = Array.isArray(m.stats) ? m.stats : null;
  const maxLift = Math.max(1, ...m.rules.map((x) => x.lift));

  return (
    <>
      <PageHead code="U3" title="Association rules">
        Each workout is a basket of exercises. Frequent itemsets show what people do <em>together</em>; rules
        X → Y are kept by confidence and ranked by lift. Switch to user-week baskets to see how training
        <em> types</em> combine across a week.
      </PageHead>

      <div className="controls">
        <Select label="Algorithm" value={prm.algorithm} onChange={(v) => setPrm({ ...prm, algorithm: v })}
          options={[{ value: 'fpgrowth', label: 'FP-Growth' }, { value: 'apriori', label: 'Apriori' }]} />
        <Select label="Basket" value={prm.basket} onChange={(v) => setPrm({ ...prm, basket: v })}
          options={[{ value: 'session', label: 'Exercises per workout' }, { value: 'user_week', label: 'Session types per user-week' }]} />
        <Slider label="min support" value={prm.min_support} min={0.005} max={0.2} step={0.005}
          onChange={(v) => setPrm({ ...prm, min_support: v })} format={(v) => fmt.pct(v, 1)} />
        <Slider label="min confidence" value={prm.min_confidence} min={0.1} max={1} step={0.05}
          onChange={(v) => setPrm({ ...prm, min_confidence: v })} format={(v) => fmt.pct(v, 0)} />
        <Slider label="min lift" value={prm.min_lift} min={0} max={5} step={0.1}
          onChange={(v) => setPrm({ ...prm, min_lift: v })} format={(v) => v.toFixed(1)} />
        <button className="btn primary" disabled={live.loading} onClick={() => live.run(prm)}>
          {live.loading ? 'Mining…' : 'Run'}</button>
        {live.data && <button className="btn" onClick={() => live.setData(null)}>Reset to pipeline result</button>}
      </div>
      {live.error && <div className="error" style={{ marginBottom: 16 }}>{live.error}</div>}

      <div className={`grid g4 ${live.loading ? 'stale' : ''}`}>
        <Tile label="Transactions" value={fmt.n(m.n_transactions)} sub={`avg ${m.avg_basket.toFixed(1)} items per basket`} />
        <Tile label="Frequent itemsets" value={fmt.n(m.n_itemsets)} sub={`${m.n_closed} closed · ${m.n_maximal} maximal`} />
        <Tile label="Rules" value={fmt.n(m.n_rules)} sub={`conf ≥ ${fmt.pct(m.params.min_confidence, 0)}, lift ≥ ${m.params.min_lift}`} />
        <Tile label={`${m.params.algorithm === 'apriori' ? 'Apriori' : 'FP-Growth'} time`} value={`${fmt.n(m.ms_mine)} ms`}
          sub={`+ ${fmt.n(m.ms_rules)} ms rule generation`} />
      </div>

      <div className={`grid g2 ${live.loading ? 'stale' : ''}`} style={{ marginTop: 16 }}>
        <ChartCard title="Rules: support × confidence" sub="dot colour = lift (darker = stronger association); hover for the rule"
          height={320}
          option={{
            ...base(p), grid: { left: 52, right: 20, top: 16, bottom: 40 },
            xAxis: { type: 'value', ...axisStyle(p), name: 'support', nameLocation: 'middle', nameGap: 26,
              axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            yAxis: { type: 'value', ...axisStyle(p), name: 'confidence', min: (v: { min: number }) => Math.floor(v.min * 10) / 10,
              axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            visualMap: { min: 1, max: maxLift, dimension: 2, show: false, inRange: { color: [p.seq[1], p.seq[6]] } },
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const i = (x as { dataIndex: number }).dataIndex;
              const rr = m.rules[i];
              return `${ruleText(rr)}<br/>support <b>${fmt.pct(rr.support)}</b> · confidence <b>${fmt.pct(rr.confidence)}</b> · lift <b>${rr.lift.toFixed(2)}</b>`;
            } },
            series: [{ type: 'scatter', symbolSize: 9, data: m.rules.map((x) => [x.support, x.confidence, x.lift]),
              itemStyle: { borderColor: p.surface, borderWidth: 1.5 } }],
          }} />
        <ChartCard title="Rule graph" sub="items (blue) feed rules (grey, size = support) that point at their consequent; top 30 by lift"
          height={320}
          option={{
            ...base(p),
            tooltip: { ...base(p).tooltip, formatter: (x: unknown) => {
              const d = (x as { data: { id: string; kind: string; lift?: number; support?: number; confidence?: number } }).data;
              if (!d || !d.kind) return '';
              return d.kind === 'item' ? `<b>${d.id}</b>` : `${d.id}: lift <b>${d.lift?.toFixed(2)}</b>, confidence ${fmt.pct(d.confidence)}`;
            } },
            series: [{
              type: 'graph', layout: 'force', roam: true, draggable: true,
              force: { repulsion: 140, edgeLength: [30, 70] },
              data: m.graph.nodes.map((n) => ({ ...n, name: n.id,
                symbolSize: n.kind === 'item' ? 12 : 6 + Math.sqrt(n.support ?? 0) * 40,
                itemStyle: { color: n.kind === 'item' ? p.series[0] : p.axis, borderColor: p.surface, borderWidth: 2 },
                label: { show: n.kind === 'item', color: p.text2, fontSize: 11, position: 'right' } })),
              links: m.graph.links,
              edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 6,
              lineStyle: { color: p.axis, width: 1, opacity: 0.8 },
            }],
          }} />
      </div>

      <div className={`grid g2 ${live.loading ? 'stale' : ''}`} style={{ marginTop: 16 }}>
        <Card title="Rules" sub="sorted by lift; click a header to re-sort">
          <DataTable rows={m.rules as unknown as Record<string, unknown>[]} height={380} cols={[
            { key: 'antecedent', label: 'If', wrap: true }, { key: 'consequent', label: 'Then', wrap: true },
            { key: 'support', label: 'Support', num: true, pct: true },
            { key: 'confidence', label: 'Confidence', num: true, pct: true },
            { key: 'lift', label: 'Lift', num: true, digits: 2 }, { key: 'leverage', label: 'Leverage', num: true, digits: 4 },
            { key: 'conviction', label: 'Conviction', num: true, digits: 2 }]} />
        </Card>
        {m.planted ? (
          <Recovery items={m.planted.rules.map((x) => ({
            label: ruleText(x), ok: x.found,
            value: x.found ? `conf ${fmt.pct(x.confidence)} · lift ${x.lift.toFixed(1)}` : 'not mined',
            note: x.found ? `rank ${x.rank} by lift of ${m.n_rules}` : 'lower min support / confidence?',
          }))} />
        ) : (
          <Card title="Frequent itemsets" sub="largest first">
            <DataTable rows={m.itemsets.map((x) => ({ items: x.items.join(', '), size: x.items.length, support: x.support }))}
              height={380} cols={[{ key: 'items', label: 'Itemset', wrap: true }, { key: 'size', label: 'k', num: true },
                { key: 'support', label: 'Support', num: true, pct: true }]} />
          </Card>
        )}
      </div>

      <SectionTitle title="Apriori vs FP-Growth"
        sub={r.comparison.same_itemsets ? 'both return exactly the same frequent itemsets; they differ in work done' : 'itemsets differ!'} />
      <div className="grid g3">
        <ChartCard title="Apriori, level by level" sub="candidates from the join, pruned by the Apriori property, frequent after the scan"
          height={260}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['candidates', 'pruned', 'frequent'] },
            xAxis: { type: 'category', data: (levels ?? r.comparison.apriori_levels).map((l) => `k=${l.k}`), ...axisStyle(p) },
            yAxis: { type: 'value', ...axisStyle(p) },
            tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
            series: (['candidates', 'pruned', 'frequent'] as const).map((k, i) => ({
              name: k, type: 'bar', barMaxWidth: 14, barGap: '15%', itemStyle: barItem(p.series[i]),
              data: (levels ?? r.comparison.apriori_levels).map((l) => l[k]),
            })),
          }}
          table={(levels ?? r.comparison.apriori_levels) as unknown as Record<string, unknown>[]}
          cols={[{ key: 'k', label: 'k', num: true }, { key: 'candidates', label: 'Candidates', num: true },
            { key: 'pruned', label: 'Pruned', num: true }, { key: 'counted', label: 'Counted', num: true },
            { key: 'frequent', label: 'Frequent', num: true }]} />
        <ChartCard title="Runtime as min support drops" sub="milliseconds on the session baskets" height={260}
          option={{
            ...base(p), legend: { ...base(p).legend, data: ['Apriori', 'FP-Growth'] },
            xAxis: { type: 'category', data: r.comparison.scaling.map((s) => fmt.pct(s.min_support, 1)), ...axisStyle(p), name: 'min support', nameLocation: 'middle', nameGap: 26 },
            yAxis: { type: 'value', ...axisStyle(p), name: 'ms' },
            tooltip: { ...base(p).tooltip, trigger: 'axis' },
            series: [
              { name: 'Apriori', type: 'line', data: r.comparison.scaling.map((s) => s.apriori_ms), symbolSize: 8,
                lineStyle: { width: 2, color: p.series[0] }, itemStyle: { color: p.series[0], borderColor: p.surface, borderWidth: 2 } },
              { name: 'FP-Growth', type: 'line', data: r.comparison.scaling.map((s) => s.fpgrowth_ms), symbolSize: 8,
                lineStyle: { width: 2, color: p.series[1] }, itemStyle: { color: p.series[1], borderColor: p.surface, borderWidth: 2 } },
            ],
          }}
          table={r.comparison.scaling} cols={[{ key: 'min_support', label: 'min sup', num: true, pct: true },
            { key: 'itemsets', label: 'Itemsets', num: true }, { key: 'apriori_ms', label: 'Apriori ms', num: true, digits: 1 },
            { key: 'fpgrowth_ms', label: 'FP-Growth ms', num: true, digits: 1 },
            { key: 'apriori_candidates', label: 'Apriori candidates', num: true },
            { key: 'fp_tree_nodes', label: 'FP-tree nodes', num: true },
            { key: 'conditional_trees', label: 'Conditional trees', num: true }]} />
        <ChartCard title="Item supports" sub="1-itemsets, most frequent first" height={260}
          option={{
            ...base(p), grid: { left: 130, right: 40, top: 6, bottom: 24 },
            xAxis: { type: 'value', ...axisStyle(p), axisLabel: { ...axisStyle(p).axisLabel, formatter: (v: number) => fmt.pct(v, 0) } },
            yAxis: { type: 'category', inverse: true, data: m.items.slice(0, 14).map((x) => x.item), ...axisStyle(p), axisLabel: { color: p.text2, fontSize: 11 } },
            tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => fmt.pct(v as number) },
            series: [{ type: 'bar', barMaxWidth: 12, data: m.items.slice(0, 14).map((x) => x.support), itemStyle: barItem(p.series[0], true) }],
          }}
          table={m.items} cols={[{ key: 'item', label: 'Item' }, { key: 'support', label: 'Support', num: true, pct: true }]} />
      </div>

      <div style={{ marginTop: 16 }}>
        <ChartCard title="The FP-tree (min support 5%)"
          sub={`${fmt.n(r.fp_tree.nodes)} nodes compress ${fmt.n(r.session.n_transactions)} baskets; item:count per node, first 80 nodes`}
          height={520}
          option={{
            ...base(p),
            tooltip: { ...base(p).tooltip, triggerOn: 'mousemove' },
            series: [{
              type: 'tree', data: [r.fp_tree], top: 10, left: 60, bottom: 10, right: 160, symbolSize: 7,
              initialTreeDepth: 3, expandAndCollapse: true,
              itemStyle: { color: p.series[0], borderColor: p.surface },
              lineStyle: { color: p.axis, width: 1 },
              label: { color: p.text2, fontSize: 11, position: 'left', verticalAlign: 'middle', align: 'right' },
              leaves: { label: { position: 'right', align: 'left' } },
            }],
          }}
          table={r.fp_tree.header as unknown as Record<string, unknown>[]}
          cols={[{ key: 'item', label: 'Header table item' }, { key: 'support_count', label: 'Support count', num: true }]} />
      </div>

      <SectionTitle title="Training types combined in a week" sub="user-week baskets: pipeline result at 5% support" />
      <Card>
        <DataTable rows={r.user_week.rules as unknown as Record<string, unknown>[]} height={320} cols={[
          { key: 'antecedent', label: 'If a week has', wrap: true }, { key: 'consequent', label: 'it also has', wrap: true },
          { key: 'support', label: 'Support', num: true, pct: true }, { key: 'confidence', label: 'Confidence', num: true, pct: true },
          { key: 'lift', label: 'Lift', num: true, digits: 2 }]} />
      </Card>
    </>
  );
}
