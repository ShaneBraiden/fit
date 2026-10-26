import { Profile, Recommendation, splitWords, useGet } from '../../api/client';
import { Card, ErrorBox, Loading, PageHead } from '../../components/ui';
import { fmt } from '../../theme/chart';

export default function Insights() {
  const recs = useGet<Recommendation[]>('/api/me/recommendations');
  const prof = useGet<Profile>('/api/me/profile');
  if (prof.error) return <ErrorBox error={prof.error} />;
  if (!prof.data) return <Loading />;
  const p = prof.data;
  const dist = Object.entries(p.persona.distances).sort((a, b) => a[1] - b[1]);
  const maxD = Math.max(...dist.map((d) => d[1]), 1e-9);

  return (
    <>
      <PageHead title="Insights">What your training says, and what to try next.</PageHead>
      <div className="grid g2">
        <Card title="Try next" sub="Exercises people usually add to the ones in your recent workouts">
          {!recs.data ? <Loading /> : recs.data.length === 0 ? <div className="note">Log a workout with its exercises to get suggestions.</div>
            : recs.data.map((r) => (
              <div key={r.exercise} style={{ padding: '8px 0', borderBottom: '1px solid var(--grid)' }}>
                <strong>{r.exercise}</strong>
                <div className="note">{fmt.pct(r.confidence, 0)} of people who do {r.because.join(' + ')} also do it</div>
                <div className="bar"><i style={{ width: `${r.confidence * 100}%` }} /></div>
              </div>
            ))}
        </Card>
        <Card title="Your training style" sub="How close your mix of workouts is to each common style (shorter bar = closer)">
          {dist.map(([name, d]) => (
            <div key={name} style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: name === p.persona.name ? 600 : 400 }}>{name}{name === p.persona.name ? ' · you' : ''}</div>
              <div className="bar"><i className={name === p.persona.name ? '' : 'dim'} style={{ width: `${Math.max(2, (d / maxD) * 100)}%` }} /></div>
            </div>
          ))}
        </Card>
      </div>
      <div style={{ marginTop: 16 }}>
        <Card title="Your weekly routine" sub="Orders of workouts you repeat in at least half of your weeks">
          {p.routines.length === 0 ? <div className="note">No regular pattern yet. Keep training for a couple of weeks.</div>
            : p.routines.map((r) => (
              <div key={r.text} style={{ marginBottom: 10 }}>
                <div className="chips">{r.pattern.map((el, i) => <span key={i} className="chip">{i > 0 ? '→ ' : ''}{el.map(splitWords).join(' + ')}</span>)}</div>
                <div className="note">in {fmt.pct(r.weeks, 0)} of your weeks</div>
              </div>
            ))}
        </Card>
      </div>
    </>
  );
}
