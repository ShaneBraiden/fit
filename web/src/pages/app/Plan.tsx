import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, Catalog, PlanDay, PlanIn, PlanWeek, todayIso, useGet, WEEKDAYS } from '../../api/client';
import { activityIcon } from '../../components/fitness';
import { Card, ErrorBox, Loading, PageHead, Pill } from '../../components/ui';

const ACTIVITIES: PlanDay['activity'][] = ['Strength', 'HIIT', 'Yoga', 'Run', 'Walk', 'Cycle', 'Swim', 'Rest'];
const LIFTING = new Set<PlanDay['activity']>(['Strength', 'HIIT']);

export default function PlanPage() {
  const plan = useGet<PlanWeek>(`/api/me/plan?today=${todayIso()}`);
  const cat = useGet<Catalog>('/api/catalog');
  const [draft, setDraft] = useState<PlanIn | null>(null);
  const [picking, setPicking] = useState(false);
  if (plan.error) return <ErrorBox error={plan.error} />;
  if (!plan.data || !cat.data) return <Loading />;
  const pw = plan.data;
  const done = () => { setDraft(null); setPicking(false); plan.reload(); };

  if (draft) return <Editor initial={draft} cat={cat.data} onCancel={() => setDraft(null)} onSaved={done} />;
  const templates = (
    <div className="grid g3">
      {cat.data.plan_templates.map((t) => (
        <Card key={t.key} title={t.name} sub={`${t.days.filter((d) => d.activity !== 'Rest').length} training days a week`}>
          <div className="plan-mini">
            {t.days.map((d, i) => <div key={i} className={d.activity === 'Rest' ? 'rest' : ''}><span>{WEEKDAYS[i]}</span>{d.label}</div>)}
          </div>
          <button className="btn primary small" style={{ marginTop: 10 }} onClick={() => setDraft({ name: t.name, days: t.days })}>Use this</button>
        </Card>
      ))}
      <Card title="Start from scratch" sub="Seven rest days for you to fill in">
        <button className="btn small" onClick={() => setDraft({ name: 'My plan', days: WEEKDAYS.map(() => ({ label: 'Rest', activity: 'Rest', focus: [], exercises: [] })) })}>Blank plan</button>
      </Card>
    </div>
  );

  if (!pw.plan || picking) {
    return (
      <>
        <PageHead title="Weekly plan" actions={pw.plan ? <button className="btn" onClick={() => setPicking(false)}>Back to my plan</button> : undefined}>
          Pick a split to start from: push/pull/legs, upper/lower, full body, body-part or your own. You can change every day afterwards.
        </PageHead>
        {templates}
      </>
    );
  }

  const remove = async () => {
    if (!window.confirm('Delete your plan? Your workouts are kept.')) return;
    await api('/api/me/plan', undefined, 'DELETE');
    plan.reload();
  };
  return (
    <>
      <PageHead title={pw.plan.name} actions={<div style={{ display: 'flex', gap: 8 }}>
        <button className="btn primary" onClick={() => setDraft({ name: pw.plan!.name, days: pw.plan!.days })}>Edit plan</button>
        <button className="btn" onClick={() => setPicking(true)}>Switch split</button>
      </div>}>
        {pw.done} of {pw.planned} training days done this week. Rest days keep your streak going.
      </PageHead>
      <div className="plan-week">
        {pw.week.map((d) => {
          const day = d.day!;
          const rest = day.activity === 'Rest';
          return (
            <Card key={d.date} className={`plan-day ${d.today ? 'today' : ''} ${rest ? 'rest' : ''}`}>
              <div className="muted" style={{ fontSize: 12 }}>{WEEKDAYS[d.weekday]} · {new Date(`${d.date}T00:00:00`).getDate()}</div>
              <div style={{ fontWeight: 600, margin: '2px 0 6px' }}>{rest ? '😴' : activityIcon(day.activity)} {day.label}</div>
              {!rest && (d.done ? <Pill kind="good">Done</Pill> : d.date < todayIso() ? <Pill kind="bad">Missed</Pill>
                : d.today ? <Link to="/log" className="btn primary small" style={{ textDecoration: 'none' }}>Log it</Link> : <Pill kind="neutral">Planned</Pill>)}
              {day.focus.length > 0 && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{day.focus.join(', ')}</div>}
              {day.exercises.length > 0 && <ul className="ex-list">{day.exercises.map((e) => <li key={e}>{e}</li>)}</ul>}
            </Card>
          );
        })}
      </div>
      <div style={{ marginTop: 16 }}><button className="linkish" onClick={remove}>Delete plan</button></div>
    </>
  );
}

function Editor({ initial, cat, onCancel, onSaved }: { initial: PlanIn; cat: Catalog; onCancel: () => void; onSaved: () => void }) {
  const [name, setName] = useState(initial.name);
  const [days, setDays] = useState<PlanDay[]>(initial.days.map((d) => ({ ...d, focus: [...(d.focus ?? [])], exercises: [...(d.exercises ?? [])] })));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (i: number, patch: Partial<PlanDay>) => setDays((ds) => ds.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const save = async () => {
    setBusy(true); setError(null);
    try { await api<PlanWeek>(`/api/me/plan?today=${todayIso()}`, { name: name.trim() || 'My plan', days }, 'PUT'); onSaved(); } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };
  const training = days.filter((d) => d.activity !== 'Rest').length;

  return (
    <>
      <PageHead title="Edit plan" actions={<div style={{ display: 'flex', gap: 8 }}>
        <button className="btn" onClick={onCancel}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save plan'}</button>
      </div>}>
        {training} training day{training === 1 ? '' : 's'} a week. Name each day what you like ("Chest & Back", "Arms", "Long run").
      </PageHead>
      <Card>
        <label className="field" style={{ maxWidth: 360 }}><span>Plan name</span>
          <input value={name} maxLength={40} onChange={(e) => setName(e.target.value)} /></label>
      </Card>
      <div className="stack" style={{ marginTop: 16 }}>
        {days.map((d, i) => {
          const lifting = LIFTING.has(d.activity);
          const options = cat.exercises[d.activity] ?? [];
          const hits = (e: string) => [...(cat.exercise_muscles[e]?.primary ?? []), ...(cat.exercise_muscles[e]?.secondary ?? [])].some((m) => d.focus.includes(m));
          const addable = options.filter((e) => !d.exercises.includes(e)).sort((a, b) => Number(hits(b)) - Number(hits(a)) || a.localeCompare(b));
          return (
            <Card key={i} title={WEEKDAYS[i]}>
              <div className="form">
                <div className="row">
                  <label className="field"><span>Name</span><input value={d.label} maxLength={30} onChange={(e) => set(i, { label: e.target.value })} /></label>
                  <label className="field"><span>Activity</span>
                    <select value={d.activity} onChange={(e) => {
                      const a = e.target.value as PlanDay['activity'];
                      set(i, { activity: a, label: a === 'Rest' ? 'Rest' : d.activity === 'Rest' ? a : d.label, exercises: [], focus: LIFTING.has(a) ? d.focus : [] });
                    }}>
                      {ACTIVITIES.map((a) => <option key={a} value={a}>{a}</option>)}
                    </select></label>
                </div>
                {lifting && <div className="field"><span>Muscles this day trains</span>
                  <div className="chips">
                    {cat.muscles.map((m) => <button key={m} type="button" className={`chip toggle ${d.focus.includes(m) ? 'on' : ''}`}
                      onClick={() => set(i, { focus: d.focus.includes(m) ? d.focus.filter((x) => x !== m) : [...d.focus, m] })}>{m}</button>)}
                  </div></div>}
                {d.activity !== 'Rest' && options.length > 0 && <div className="field"><span>Exercises</span>
                  <div className="chips">
                    {d.exercises.map((e) => <button key={e} type="button" className="chip toggle on" title="Remove"
                      onClick={() => set(i, { exercises: d.exercises.filter((x) => x !== e) })}>{e} ×</button>)}
                    <select className="chip" value="" onChange={(e) => e.target.value && set(i, { exercises: [...d.exercises, e.target.value] })}
                      aria-label="Add an exercise">
                      <option value="">+ Add exercise</option>
                      {addable.map((e) => <option key={e} value={e}>{e}{lifting && hits(e) ? ' ★' : ''}</option>)}
                    </select>
                  </div>
                  {lifting && d.focus.length > 0 && <span className="hint">★ works the muscles you picked</span>}
                </div>}
              </div>
            </Card>
          );
        })}
      </div>
      {error && <div className="form-error" style={{ marginTop: 12 }}>{error}</div>}
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button className="btn primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save plan'}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
      </div>
    </>
  );
}
