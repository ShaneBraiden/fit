import { FormEvent, useState } from 'react';
import { api, AuthResult, SignupRequest } from '../api/client';
import { useAuth } from '../auth';

/** Sign in, or create an account with the body measurements the predictions need. */
export default function Login() {
  const { signIn } = useAuth();
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [f, setF] = useState({ email: '', password: '', name: '', age: '', height: '', weight: '', rhr: '', vo2: '' });
  const [gender, setGender] = useState<'F' | 'M' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const num = (s: string) => (s.trim() === '' ? null : Number(s));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    let path = '/api/auth/login';
    let body: unknown = { email: f.email, password: f.password };
    if (mode === 'signup') {
      const age = num(f.age), height = num(f.height), weight = num(f.weight);
      if (!f.name.trim() || !gender || age == null || height == null || weight == null) {
        setError('Fill in your name, sex, age, height and weight.');
        return;
      }
      const req: SignupRequest = { email: f.email, password: f.password, name: f.name.trim(), gender, age: Math.round(age),
        height_cm: height, weight_kg: weight, resting_hr: num(f.rhr), vo2max: num(f.vo2) };
      path = '/api/auth/signup';
      body = req;
    }
    setBusy(true);
    try {
      const r = await api<AuthResult>(path, body);
      signIn(r.token, r.account);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <form className="auth-box" onSubmit={submit}>
        <div className="auth-brand">
          <div className="brand-mark">F</div>
          <div><h1>FitMine</h1><div className="muted">Your workouts, your fitness level, what to try next</div></div>
        </div>
        <div className="seg" style={{ justifySelf: 'center' }}>
          <button type="button" className={mode === 'login' ? 'on' : ''} onClick={() => { setMode('login'); setError(null); }}>Sign in</button>
          <button type="button" className={mode === 'signup' ? 'on' : ''} onClick={() => { setMode('signup'); setError(null); }}>Create account</button>
        </div>
        <section className="card form">
          {mode === 'signup' && <label className="field"><span>Name</span><input value={f.name} onChange={set('name')} autoComplete="name" required /></label>}
          <label className="field"><span>Email</span><input type="email" value={f.email} onChange={set('email')} autoComplete="email" required /></label>
          <label className="field"><span>Password</span>
            <input type="password" value={f.password} onChange={set('password')} required minLength={mode === 'signup' ? 8 : undefined}
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} />
            {mode === 'signup' && <span className="hint">At least 8 characters.</span>}
          </label>
        </section>
        {mode === 'signup' && (
          <section className="card form">
            <div><h3>About you</h3><div className="note">Used to estimate your fitness level and calories. You can change these later.</div></div>
            <div className="field"><span>Sex</span>
              <div className="chips">
                <button type="button" className={`chip toggle ${gender === 'F' ? 'on' : ''}`} onClick={() => setGender('F')}>Female</button>
                <button type="button" className={`chip toggle ${gender === 'M' ? 'on' : ''}`} onClick={() => setGender('M')}>Male</button>
              </div>
            </div>
            <div className="row">
              <label className="field"><span>Age</span><input inputMode="numeric" value={f.age} onChange={set('age')} /></label>
              <label className="field"><span>Height (cm)</span><input inputMode="decimal" value={f.height} onChange={set('height')} /></label>
              <label className="field"><span>Weight (kg)</span><input inputMode="decimal" value={f.weight} onChange={set('weight')} /></label>
            </div>
            <div className="row">
              <label className="field"><span>Resting heart rate</span><input inputMode="numeric" value={f.rhr} onChange={set('rhr')} />
                <span className="hint">Optional, bpm</span></label>
              <label className="field"><span>VO2max</span><input inputMode="decimal" value={f.vo2} onChange={set('vo2')} />
                <span className="hint">Optional, from your watch</span></label>
            </div>
          </section>
        )}
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="btn primary" type="submit" disabled={busy} style={{ padding: '10px 14px' }}>
          {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
    </div>
  );
}
