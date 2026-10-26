import { FormEvent, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, Catalog, localIso, pace, reasonText, RecordRequest, RecordResult, splitWords, useGet, when } from '../../api/client';
import { activityIcon, TrackMap } from '../../components/fitness';
import { Card, PageHead, Pill, Tile } from '../../components/ui';
import { fmt } from '../../theme/chart';

type Activity = RecordRequest['activity'];
type Fix = { t: number; lat: number; lon: number; accuracy: number | null };
const ACTIVITIES: Activity[] = ['Run', 'Walk', 'Cycle', 'Swim', 'Strength', 'HIIT', 'Yoga'];
const GPS = new Set<Activity>(['Run', 'Walk', 'Cycle']);
const MAX_ACCURACY_M = 35;

function haversine(a: Fix, b: Fix): number {
  const r = Math.PI / 180;
  const h = Math.sin((b.lat - a.lat) * r / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin((b.lon - a.lon) * r / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}
const clock = (sec: number) => {
  const s = Math.round(sec), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h ? `${h}:` : ''}${String(m).padStart(h ? 2 : 1, '0')}:${String(s % 60).padStart(2, '0')}`;
};

export default function Log() {
  const [activity, setActivity] = useState<Activity>('Run');
  const [mode, setMode] = useState<'manual' | 'gps'>('manual');
  const [res, setRes] = useState<RecordResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = async (body: RecordRequest) => {
    setBusy(true); setError(null);
    try { setRes(await api<RecordResult>('/api/me/workouts', body)); return true; } catch (e) {
      setError(e instanceof Error ? e.message : String(e)); return false;
    } finally { setBusy(false); }
  };
  if (res) return <Result res={res} onDone={() => setRes(null)} />;
  const gps = GPS.has(activity) && mode === 'gps';
  return (
    <>
      <PageHead title="Log a workout">Log one you've done, or track a run, walk or ride with this device's GPS.</PageHead>
      <Card title="Activity">
        <div className="chips">
          {ACTIVITIES.map((a) => (
            <button key={a} type="button" className={`chip toggle ${a === activity ? 'on' : ''}`} onClick={() => setActivity(a)}>
              {activityIcon(a)} {a}</button>
          ))}
        </div>
        {GPS.has(activity) && (
          <div className="seg" style={{ marginTop: 12 }}>
            <button className={mode === 'manual' ? 'on' : ''} onClick={() => setMode('manual')}>Log manually</button>
            <button className={mode === 'gps' ? 'on' : ''} onClick={() => setMode('gps')}>Track with GPS</button>
          </div>
        )}
      </Card>
      <div style={{ marginTop: 16 }}>
        {gps ? <GpsTracker activity={activity} busy={busy} onFinish={upload} /> : <Manual activity={activity} busy={busy} onSubmit={upload} />}
      </div>
      {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
    </>
  );
}

function Manual({ activity, busy, onSubmit }: { activity: Activity; busy: boolean; onSubmit: (b: RecordRequest) => Promise<boolean> }) {
  const catalog = useGet<Catalog>('/api/catalog');
  const [start, setStart] = useState(() => localIso(new Date()).slice(0, 16));
  const [f, setF] = useState({ duration: '', distance: '', hr: '', calories: '', title: '' });
  const [split, setSplit] = useState<RecordRequest['kind']>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => { setPicked([]); setSplit(null); }, [activity]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const num = (s: string) => (s.trim() === '' ? null : Number(s));
  const hasDistance = GPS.has(activity) || activity === 'Swim';
  const options = catalog.data?.exercises[activity] ?? [];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setProblem(null);
    const mins = num(f.duration);
    if (!mins || mins <= 0) { setProblem('Enter how many minutes the workout took.'); return; }
    if (new Date(start).getTime() > Date.now()) { setProblem('That start time is in the future.'); return; }
    const ok = await onSubmit({ activity, start_time: `${start}:00`, duration_min: mins, kind: split, title: f.title.trim() || null,
      distance_km: hasDistance ? num(f.distance) : null, avg_hr: num(f.hr), calories: num(f.calories), exercises: picked });
    if (ok) { setF({ duration: '', distance: '', hr: '', calories: '', title: '' }); setPicked([]); }
  };

  return (
    <form onSubmit={submit} className="stack">
      <Card title="Details">
        <div className="form">
          <div className="row">
            <label className="field"><span>Started</span><input type="datetime-local" value={start} max={localIso(new Date()).slice(0, 16)}
              onChange={(e) => setStart(e.target.value)} required /></label>
            <label className="field"><span>Duration (min)</span><input inputMode="decimal" value={f.duration} onChange={set('duration')} required /></label>
            {hasDistance && <label className="field"><span>Distance (km)</span><input inputMode="decimal" value={f.distance} onChange={set('distance')} /></label>}
          </div>
          <div className="row">
            <label className="field"><span>Avg heart rate</span><input inputMode="numeric" value={f.hr} onChange={set('hr')} /><span className="hint">Optional, bpm</span></label>
            <label className="field"><span>Calories</span><input inputMode="numeric" value={f.calories} onChange={set('calories')} /><span className="hint">Optional; we estimate it</span></label>
            <label className="field"><span>Title</span><input value={f.title} onChange={set('title')} maxLength={60} /><span className="hint">Optional</span></label>
          </div>
          {activity === 'Strength' && (
            <div className="field"><span>Session</span>
              <div className="chips">
                {(['push', 'pull', 'legs'] as const).map((k) => (
                  <button key={k} type="button" className={`chip toggle ${split === k ? 'on' : ''}`} onClick={() => setSplit(split === k ? null : k)}>
                    {k[0].toUpperCase() + k.slice(1)}</button>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>
      {options.length > 0 && (
        <Card title="Exercises" sub={'Pick what you did. Your "Try next" suggestions are based on this.'}>
          <div className="chips">
            {options.map((x) => (
              <button key={x} type="button" className={`chip toggle ${picked.includes(x) ? 'on' : ''}`}
                onClick={() => setPicked((p) => (p.includes(x) ? p.filter((y) => y !== x) : [...p, x]))}>{x}</button>
            ))}
          </div>
        </Card>
      )}
      {problem && <div className="form-error">{problem}</div>}
      <div><button className="btn primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save workout'}</button></div>
    </form>
  );
}

function GpsTracker({ activity, busy, onFinish }: { activity: Activity; busy: boolean; onFinish: (b: RecordRequest) => Promise<boolean> }) {
  const [state, setState] = useState<'idle' | 'tracking' | 'paused' | 'stopped'>('idle');
  const [, setCount] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const good = useRef<Fix[]>([]);
  const meters = useRef(0);
  const watch = useRef<number | null>(null);
  const started = useRef<Date | null>(null);

  useEffect(() => {
    if (state !== 'tracking') return;
    let last = Date.now();
    const id = setInterval(() => { const now = Date.now(); setElapsed((e) => e + (now - last) / 1000); last = now; }, 1000);
    return () => clearInterval(id);
  }, [state]);
  useEffect(() => () => { if (watch.current != null) navigator.geolocation.clearWatch(watch.current); }, []);

  const startWatch = () => {
    if (!('geolocation' in navigator)) { setProblem('This browser has no GPS access. Log the workout manually instead.'); return false; }
    setProblem(null);
    watch.current = navigator.geolocation.watchPosition((pos) => {
      const f: Fix = { t: pos.timestamp, lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy };
      setAccuracy(f.accuracy);
      if ((f.accuracy ?? 0) <= MAX_ACCURACY_M) {
        const prev = good.current[good.current.length - 1];
        if (prev) meters.current += haversine(prev, f);
        good.current.push(f);
        setCount(good.current.length);
      }
    }, (err) => setProblem(err.code === err.PERMISSION_DENIED
      ? 'Location access was blocked. Allow it for this site, or log the workout manually.' : `GPS error: ${err.message}`),
    { enableHighAccuracy: true, maximumAge: 0 });
    return true;
  };
  const stopWatch = () => { if (watch.current != null) navigator.geolocation.clearWatch(watch.current); watch.current = null; };
  const reset = () => { good.current = []; meters.current = 0; setCount(0); setElapsed(0); setAccuracy(null); };
  const save = async () => {
    const ok = await onFinish({ activity, start_time: started.current ? localIso(started.current) : null,
      duration_min: Math.max(elapsed, 1) / 60, track: good.current });
    if (ok) { reset(); setState('idle'); }
  };
  const km = meters.current / 1000;
  const tooShort = good.current.length < 2 || elapsed < 30;

  return (
    <div className="stack">
      <div className="grid g4">
        <Tile label="Time" value={clock(elapsed)} />
        <Tile label="Distance" value={`${km.toFixed(2)} km`} />
        <Tile label={activity === 'Cycle' ? 'Speed' : 'Pace'} value={km > 0.05 ? (activity === 'Cycle'
          ? `${(km / (elapsed / 3600)).toFixed(1)} km/h` : pace(elapsed / 60 / km)) : '–'} />
        <Tile label="GPS accuracy" value={accuracy == null ? '–' : `${Math.round(accuracy)} m`} sub={state === 'paused' ? 'paused' : undefined} />
      </div>
      {good.current.length > 1 && <Card><TrackMap lat={good.current.map((f) => f.lat)} lon={good.current.map((f) => f.lon)} height={260} /></Card>}
      {problem && <div className="form-error">{problem}</div>}
      <div style={{ display: 'flex', gap: 8 }}>
        {state === 'idle' && <button className="btn primary" onClick={() => { if (startWatch()) { reset(); started.current = new Date(); setState('tracking'); } }}>
          Start {activity.toLowerCase()}</button>}
        {state === 'tracking' && <>
          <button className="btn" onClick={() => { stopWatch(); setState('paused'); }}>Pause</button>
          <button className="btn primary" onClick={() => { stopWatch(); setState('stopped'); }}>Finish</button></>}
        {state === 'paused' && <>
          <button className="btn" onClick={() => { if (startWatch()) setState('tracking'); }}>Resume</button>
          <button className="btn primary" onClick={() => setState('stopped')}>Finish</button></>}
        {state === 'stopped' && <>
          <button className="btn primary" onClick={save} disabled={busy || tooShort}>{busy ? 'Saving…' : 'Save workout'}</button>
          <button className="btn" onClick={() => { reset(); setState('idle'); }}>Discard</button></>}
      </div>
      {state === 'stopped' && tooShort && <div className="note">Too short to save: record at least 30 seconds with a GPS signal.</div>}
      {state === 'idle' && <div className="note">Best on a phone browser; keep this page open while you record.</div>}
    </div>
  );
}

function Result({ res, onDone }: { res: RecordResult; onDone: () => void }) {
  const w = res.workout, v = res.verdict, d = res.detail;
  return (
    <>
      <PageHead title="Workout saved">{w.title} · {when.date(w.start_time)}</PageHead>
      <div className="grid g2">
        <Card title={<>{v.flagged ? 'This one needs a look' : 'All good'} <Pill kind={v.flagged ? 'bad' : 'good'}>{v.flagged ? 'Not counted' : 'Counted'}</Pill></>}>
          {v.flagged ? <>
            {v.reasons.map((r) => <div key={r} className="note">• {reasonText(r)}</div>)}
            <div className="note" style={{ marginTop: 6 }}>It's saved but won't count towards your stats. Delete it from the workout page if it was a mistake.</div>
          </> : <div className="note">It counts towards your stats and predictions.</div>}
        </Card>
        <Card title={res.level_before !== res.level_after || res.persona_before !== res.persona_after ? 'What changed' : 'Where you stand'}>
          <dl className="kv">
            <dt>Fitness level</dt><dd>{res.level_before === res.level_after ? res.level_after : `${res.level_before} → ${res.level_after}`}</dd>
            <dt>Training style</dt><dd>{res.persona_before === res.persona_after ? res.persona_after : `${res.persona_before} → ${res.persona_after}`}</dd>
          </dl>
          {res.recommendations.length > 0 && <div style={{ marginTop: 10 }}>
            <div className="note">Try next time:</div>
            {res.recommendations.slice(0, 3).map((r) => <div key={r.exercise}><strong>{r.exercise}</strong> <span className="muted">
              (most people who do {r.because.join(' + ')} add it)</span></div>)}
          </div>}
        </Card>
      </div>
      <div className="grid g4" style={{ marginTop: 16 }}>
        <Tile label="Duration" value={`${Math.round(w.duration_min)} min`} />
        <Tile label="Distance" value={w.distance_km ? `${w.distance_km.toFixed(2)} km` : '–'} />
        <Tile label="Type" value={splitWords(w.session_type)} />
        <Tile label="Calories" value={fmt.n(w.calories)} />
      </div>
      {d.lat && d.lon && <div style={{ marginTop: 16 }}><Card title="Route"><TrackMap lat={d.lat} lon={d.lon} segments={d.segments} /></Card></div>}
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button className="btn primary" onClick={onDone}>Log another</button>
        <Link className="btn" to={`/workout/${w.workout_id}`} style={{ textDecoration: 'none' }}>Open workout</Link>
      </div>
    </>
  );
}
