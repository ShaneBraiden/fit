import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { Account, Alert, api, reasonText, useGet, when } from '../../api/client';
import { useAuth } from '../../auth';
import { Card, PageHead, Pill } from '../../components/ui';

export default function Profile() {
  const { account, setAccount } = useAuth();
  const alerts = useGet<Alert[]>('/api/me/alerts');
  const [edit, setEdit] = useState(false);
  if (!account) return null;
  const a = account;
  return (
    <>
      <PageHead title={a.name}>Your details and data checks.</PageHead>
      <div className="grid g2">
        {edit ? <EditForm account={a} onDone={(next) => { if (next) setAccount(next); setEdit(false); }} /> : (
          <Card title="Your details" actions={<button className="btn small" onClick={() => setEdit(true)}>Edit</button>}>
            <dl className="kv">
              <dt>Email</dt><dd>{a.email}</dd>
              <dt>Sex</dt><dd>{a.gender === 'F' ? 'Female' : 'Male'}</dd>
              <dt>Age</dt><dd>{a.age}</dd>
              <dt>Height</dt><dd>{a.height_cm} cm</dd>
              <dt>Weight</dt><dd>{a.weight_kg} kg</dd>
              <dt>BMI</dt><dd>{a.bmi}</dd>
              <dt>Resting HR</dt><dd>{a.resting_hr ? `${a.resting_hr} bpm` : 'not set'}</dd>
              <dt>VO2max</dt><dd>{a.vo2max ?? 'estimated from your workouts'}</dd>
              <dt>Member since</dt><dd>{when.date(a.signup_date)}</dd>
            </dl>
          </Card>
        )}
        <Card title={<>Data checks {alerts.data && <Pill kind={alerts.data.length ? 'bad' : 'good'}>{alerts.data.length ? `${alerts.data.length} found` : 'All clear'}</Pill>}</>}
          sub="Every workout is checked for GPS glitches, impossible speeds and other errors. Flagged ones don't count towards your stats.">
          {alerts.data?.length === 0 && <div className="note">Nothing unusual in your workouts.</div>}
          {alerts.data?.map((x) => (
            <div key={x.workout_id} style={{ padding: '6px 0', borderBottom: '1px solid var(--grid)' }}>
              <Link to={`/workout/${x.workout_id}`}>{x.title}</Link>
              <div className="note">{reasonText(x.detail)} · {when.date(x.start_time)}</div>
            </div>
          ))}
        </Card>
      </div>
    </>
  );
}

function EditForm({ account, onDone }: { account: Account; onDone: (a: Account | null) => void }) {
  const str = (v: number | null | undefined) => (v == null ? '' : String(v));
  const [f, setF] = useState({ name: account.name, age: str(account.age), height: str(account.height_cm), weight: str(account.weight_kg),
    rhr: str(account.resting_hr), vo2: str(account.vo2max) });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const num = (s: string) => (s.trim() === '' ? null : Number(s));
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      onDone(await api<Account>('/api/me', { name: f.name.trim(), age: num(f.age), height_cm: num(f.height), weight_kg: num(f.weight),
        resting_hr: num(f.rhr), vo2max: num(f.vo2) }, 'PATCH'));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Edit your details">
      <form className="form" onSubmit={save}>
        <label className="field"><span>Name</span><input value={f.name} onChange={set('name')} required /></label>
        <div className="row">
          <label className="field"><span>Age</span><input inputMode="numeric" value={f.age} onChange={set('age')} /></label>
          <label className="field"><span>Height (cm)</span><input inputMode="decimal" value={f.height} onChange={set('height')} /></label>
          <label className="field"><span>Weight (kg)</span><input inputMode="decimal" value={f.weight} onChange={set('weight')} /></label>
        </div>
        <div className="row">
          <label className="field"><span>Resting heart rate</span><input inputMode="numeric" value={f.rhr} onChange={set('rhr')} />
            <span className="hint">Leave empty if unknown</span></label>
          <label className="field"><span>VO2max</span><input inputMode="decimal" value={f.vo2} onChange={set('vo2')} />
            <span className="hint">Leave empty to estimate it</span></label>
        </div>
        {error && <div className="form-error">{error}</div>}
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
          <button className="btn" type="button" onClick={() => onDone(null)}>Cancel</button>
        </div>
      </form>
    </Card>
  );
}
