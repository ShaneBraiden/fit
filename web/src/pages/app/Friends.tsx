import { FormEvent, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, Comparison, Friends, FriendSummary, todayIso, useGet, when } from '../../api/client';
import { BodyMap } from '../../components/body';
import { Card, Chart, ErrorBox, Legend, Loading, PageHead, Pill } from '../../components/ui';
import { axisStyle, barItem, base, fmt, usePalette } from '../../theme/chart';

const showCode = (c: string) => `${c.slice(0, 4)}-${c.slice(4)}`;
const days = (n: number) => `${n} day${n === 1 ? '' : 's'}`;

export default function FriendsPage() {
  const r = useGet<Friends>(`/api/me/friends?today=${todayIso()}`);
  const [handle, setHandle] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  if (r.error) return <ErrorBox error={r.error} />;
  if (!r.data) return <Loading />;
  const d = r.data;
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); r.reload(); } catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }); } finally { setBusy(false); }
  };
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null);
    await act(async () => {
      const res = await api<{ status: string }>('/api/me/friends', { handle: handle.trim() });
      setMsg({ ok: true, text: res.status === 'accepted' ? "They'd already asked you, so you're now friends." : "Request sent. You'll see their numbers once they accept." });
      setHandle('');
    });
  };
  const byId = new Map<number, FriendSummary>([[d.me.user_id, d.me], ...d.friends.map((f) => [f.user_id, f] as const)]);

  return (
    <>
      <PageHead title="Friends">Follow each other's training. Friends see your streak, weekly totals, level and sets per muscle, never single workouts or GPS tracks.</PageHead>
      <div className="grid g2">
        <Card title="Add a friend" sub="Their email address or their friend code">
          <form onSubmit={add} style={{ display: 'flex', gap: 8 }}>
            <input className="input" value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="friend@example.com or ABCD-EFGH" aria-label="Email or friend code" style={{ flex: 1 }} />
            <button className="btn primary" disabled={busy || handle.trim().length < 3}>Add</button>
          </form>
          {msg && <div className={msg.ok ? 'note' : 'form-error'} style={{ marginTop: 8 }}>{msg.text}</div>}
          <div className="code-box">
            <div><div className="muted" style={{ fontSize: 12 }}>Your friend code</div><div className="code">{showCode(d.code)}</div></div>
            <button className="btn small" onClick={() => { navigator.clipboard?.writeText(showCode(d.code)).catch(() => undefined); setMsg({ ok: true, text: 'Code copied.' }); }}>Copy</button>
          </div>
        </Card>
        <Card title="This week's leaderboard" sub="Minutes trained since Monday">
          {d.leaderboard.length === 1 && <div className="note">Add a friend to compete. Right now it's just you.</div>}
          {d.leaderboard.map((id, i) => {
            const f = byId.get(id)!;
            const me = id === d.me.user_id;
            return (
              <div key={id} className={`board-row ${me ? 'me' : ''}`}>
                <span className="rank">{i + 1}</span>
                <span className="grow">{me ? <strong>You</strong> : <Link to={`/friends/${id}`}><strong>{f.name}</strong></Link>}
                  <div className="muted" style={{ fontSize: 12 }}>{f.week_sessions} workout{f.week_sessions === 1 ? '' : 's'}</div></span>
                <span title="streak">🔥 {f.streak}</span>
                <span className="num" style={{ minWidth: 70, textAlign: 'right' }}><strong>{fmt.n(f.week_minutes)}</strong> min</span>
              </div>
            );
          })}
        </Card>
      </div>
      {(d.incoming.length > 0 || d.outgoing.length > 0) && (
        <div className="grid g2" style={{ marginTop: 16 }}>
          <Card title={<>Requests for you {d.incoming.length > 0 && <Pill kind="warn">{d.incoming.length}</Pill>}</>}>
            {d.incoming.length === 0 && <div className="note">None right now.</div>}
            {d.incoming.map((x) => (
              <div key={x.user_id} className="board-row">
                <span className="grow"><strong>{x.name}</strong><div className="muted" style={{ fontSize: 12 }}>since {when.date(x.since)}</div></span>
                <button className="btn primary small" disabled={busy} onClick={() => act(() => api(`/api/me/friends/${x.user_id}/accept`, undefined, 'POST'))}>Accept</button>
                <button className="btn small" disabled={busy} onClick={() => act(() => api(`/api/me/friends/${x.user_id}`, undefined, 'DELETE'))}>Decline</button>
              </div>
            ))}
          </Card>
          <Card title="Sent requests">
            {d.outgoing.length === 0 && <div className="note">None waiting.</div>}
            {d.outgoing.map((x) => (
              <div key={x.user_id} className="board-row">
                <span className="grow"><strong>{x.name}</strong><div className="muted" style={{ fontSize: 12 }}>waiting since {when.date(x.since)}</div></span>
                <button className="btn small" disabled={busy} onClick={() => act(() => api(`/api/me/friends/${x.user_id}`, undefined, 'DELETE'))}>Cancel</button>
              </div>
            ))}
          </Card>
        </div>
      )}
      <div style={{ marginTop: 16 }}>
        <Card title={`Your friends (${d.friends.length})`}>
          {d.friends.length === 0 && <div className="note">No friends yet. Share your code: {showCode(d.code)}</div>}
          {d.friends.map((f) => (
            <Link key={f.user_id} to={`/friends/${f.user_id}`} className="workout-row">
              <span className="icon" aria-hidden>{f.name[0]?.toUpperCase()}</span>
              <span className="grow"><strong>{f.name}</strong>
                <div className="muted" style={{ fontSize: 12 }}>🔥 {f.streak}-day streak · {fmt.n(f.four_week_minutes)} min in 4 weeks
                  {f.last_workout ? ` · last trained ${when.date(f.last_workout)}` : ''}</div></span>
              {f.today_done ? <Pill kind="good">Trained today</Pill> : <span className="muted">Compare ›</span>}
            </Link>
          ))}
        </Card>
      </div>
    </>
  );
}

export function ComparePage() {
  const p = usePalette();
  const { id } = useParams();
  const nav = useNavigate();
  const r = useGet<Comparison>(`/api/me/friends/${id}/compare?today=${todayIso()}`);
  if (r.error) return <ErrorBox error={r.error} />;
  if (!r.data) return <Loading />;
  const { me, friend: f } = r.data;
  const unfriend = async () => {
    if (!window.confirm(`Remove ${f.name} from your friends? You'll stop seeing each other's numbers.`)) return;
    await api(`/api/me/friends/${f.user_id}`, undefined, 'DELETE');
    nav('/friends');
  };
  const rows: [string, string, string][] = [
    ['Streak', days(me.streak), days(f.streak)],
    ['Longest streak', days(me.longest_streak), days(f.longest_streak)],
    ['This week', `${fmt.n(me.week_minutes)} min · ${me.week_sessions}×`, `${fmt.n(f.week_minutes)} min · ${f.week_sessions}×`],
    ['Fitness level', me.level, f.level],
    ['Training style', me.persona, f.persona],
    ['Sessions / week', fmt.n(me.stats.sessions_per_week, 1), fmt.n(f.stats.sessions_per_week, 1)],
    ['Minutes / week', fmt.n(me.stats.minutes_per_week), fmt.n(f.stats.minutes_per_week)],
    ['VO2max', fmt.n(me.stats.vo2max, 1), fmt.n(f.stats.vo2max, 1)],
  ];
  const muscles = Object.keys(me.muscle_sets);
  const colors = [p.series[0], p.series[1]];

  return (
    <>
      <PageHead title={`You vs ${f.name}`} actions={<button className="btn" onClick={unfriend}>Remove friend</button>}>
        Your last 8 weeks side by side. <Link to="/friends">All friends</Link>
      </PageHead>
      <div className="grid g2">
        <Card title="Head to head">
          <table className="compare"><thead><tr><th /><th style={{ color: colors[0] }}>You</th><th style={{ color: colors[1] }}>{f.name}</th></tr></thead>
            <tbody>{rows.map(([k, a, b]) => <tr key={k}><td className="muted">{k}</td><td>{a}</td><td>{b}</td></tr>)}</tbody></table>
        </Card>
        <Card title="Minutes per week">
          <Chart height={240} option={{
            ...base(p), legend: { ...base(p).legend, data: ['You', f.name] }, grid: { left: 40, right: 10, top: 34, bottom: 26 },
            xAxis: { type: 'category', data: me.weekly.map((w) => new Date(`${w.week}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })), ...axisStyle(p) },
            yAxis: { type: 'value', name: 'min', ...axisStyle(p) },
            tooltip: { ...base(p).tooltip, trigger: 'axis', valueFormatter: (v) => `${Math.round(v as number)} min` },
            series: [me, f].map((x, i) => ({ type: 'bar' as const, name: i ? f.name : 'You', barMaxWidth: 16, data: x.weekly.map((w) => w.minutes), itemStyle: barItem(colors[i]) })),
          }} />
        </Card>
      </div>
      <div style={{ marginTop: 16 }}>
        <Card title="Sets per muscle" sub="Average per week over the last 4 weeks">
          <div className="grid g2">
            <Chart height={300} option={{
              ...base(p), legend: { ...base(p).legend, data: ['You', f.name] }, grid: { left: 84, right: 16, top: 30, bottom: 24 },
              yAxis: { type: 'category', data: [...muscles].reverse(), ...axisStyle(p) }, xAxis: { type: 'value', name: 'sets', ...axisStyle(p) },
              tooltip: { ...base(p).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${v} sets` },
              series: [me, f].map((x, i) => ({ type: 'bar' as const, name: i ? f.name : 'You', barMaxWidth: 10,
                data: [...muscles].reverse().map((m) => x.muscle_sets[m]), itemStyle: barItem(colors[i], true) })),
            }} />
            <div>
              <div className="grid g2" style={{ gap: 8 }}>
                <div><div className="note" style={{ textAlign: 'center' }}>You</div><BodyMap p={p} sets={me.muscle_sets} /></div>
                <div><div className="note" style={{ textAlign: 'center' }}>{f.name}</div><BodyMap p={p} sets={f.muscle_sets} /></div>
              </div>
              <Legend items={[{ label: 'darker = more sets per week', color: p.seq[5] }]} />
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
