import { Card, ChartCard, DataTable, PageHead, Recovery, Tile } from '../../components/ui';
import { fmt, usePalette } from '../../theme/chart';
import { hbarOption, Report } from './shared';

interface Rule { antecedent: string[]; consequent: string[]; support: number; confidence: number; lift: number; leverage: number; conviction: number }
interface Sugg {
  params: { min_support: number; min_confidence: number }; n_transactions: number; avg_basket: number; n_items: number;
  n_itemsets: number; n_closed: number; n_maximal: number; n_rules: number; ms_mine: number;
  fp_tree: { tree_nodes: number; conditional_trees: number; max_depth: number };
  items: { item: string; support: number }[]; rules: Rule[];
  planted: { rules: { antecedent: string[]; consequent: string[]; found: boolean; rank: number | null; confidence: number | null; lift: number | null }[];
    recovered: number; total: number };
}

export default function SuggestionsPage() {
  const p = usePalette();
  return (
    <Report<Sugg> name="suggestions">{(r) => {
      const top = r.items.slice(0, 15);
      return (
        <>
          <PageHead title="Try next: FP-Growth association rules">
            Each workout is a basket of the exercises done in it. FP-Growth compresses the baskets into an FP-tree and mines the frequent
            itemsets without generating candidates; rules A ⇒ B are kept at support ≥ {fmt.pct(r.params.min_support, 0)} and confidence ≥{' '}
            {fmt.pct(r.params.min_confidence, 0)}. The app suggests B when a user's recent workout had A but not B.
          </PageHead>
          <div className="grid g4">
            <Tile label="Baskets" value={fmt.n(r.n_transactions)} sub={`${r.avg_basket.toFixed(2)} exercises each, ${r.n_items} distinct`} />
            <Tile label="Frequent itemsets" value={fmt.n(r.n_itemsets)} sub={`${r.n_maximal} maximal`} />
            <Tile label="Rules" value={fmt.n(r.n_rules)} sub={`mined in ${fmt.n(r.ms_mine)} ms`} />
            <Tile label="FP-tree" value={`${fmt.n(r.fp_tree.tree_nodes)} nodes`} sub={`${r.fp_tree.conditional_trees} conditional trees`} />
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <ChartCard title="Most common exercises" sub="support = share of workouts" height={360}
              option={hbarOption(p, top.map((x) => x.item), top.map((x) => x.support), { pct: true })}
              table={r.items} cols={[{ key: 'item', label: 'Exercise' }, { key: 'support', label: 'Support', num: true, pct: true }]} />
            <Recovery items={r.planted.rules.map((x) => ({
              label: `${x.antecedent.join(' + ')} ⇒ ${x.consequent.join(' + ')}`,
              value: x.found ? `rank ${x.rank} · conf ${fmt.pct(x.confidence ?? 0, 0)} · lift ${(x.lift ?? 0).toFixed(1)}` : '–', ok: x.found }))} />
          </div>
          <div style={{ marginTop: 16 }}>
            <Card title="Strongest rules" sub="sorted by lift">
              <DataTable rows={r.rules.map((x) => ({ ...x, a: x.antecedent.join(' + '), c: x.consequent.join(' + ') }))} height={420} cols={[
                { key: 'a', label: 'If a workout has', wrap: true }, { key: 'c', label: 'it usually also has' },
                { key: 'support', label: 'Support', num: true, pct: true }, { key: 'confidence', label: 'Confidence', num: true, pct: true },
                { key: 'lift', label: 'Lift', num: true, digits: 2 }, { key: 'conviction', label: 'Conviction', num: true, digits: 2 }]} />
            </Card>
          </div>
        </>
      );
    }}</Report>
  );
}
