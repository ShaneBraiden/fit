import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { localIso, Streak, todayIso, useGet, WEEKDAYS } from '../../api/client';
import { Card, ErrorBox, Loading, PageHead, Tile } from '../../components/ui';
import { fmt } from '../../theme/chart';

/** The streak hero: flame, number, and this week's seven days. Also used on Today. */
export function StreakBadge({ s, compact }: { s: Streak; compact?: boolean }) {
  const lit = s.current > 0;
  return (
    <div className={`streak-hero ${compact ? 'compact' : ''}`}>
      <div className={`flame ${lit ? 'lit' : ''}`} aria-hidden>🔥</div>
      <div>
        <div className="streak-num">{s.current}<span> day streak</span></div>
        <div className="note">
          {s.today_done ? 'Done for today. See you tomorrow!' : s.at_risk ? 'Train today to keep your streak going.'
            : lit ? 'Rest day: your streak is safe.' : 'Log a workout to start a streak.'}
        </div>
      </div>
      <div className="week-dots">
        {s.week.map((d, i) => (
          <div key={d.date} className={`dot-day ${d.status}`} title={`${WEEKDAYS[i]}: ${d.status}`}>
            <span className="circle">{d.status === 'done' ? '✓' : d.status === 'rest' ? 'z' : ''}</span>
            <span className="lbl">{WEEKDAYS[i][0]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function StreakPage() {
  const r = useGet<Streak>(`/api/me/streak?today=${todayIso()}`);
  const [offset, setOffset] = useState(0);
  const days = useMemo(() => new Map((r.data?.days ?? []).map((d) => [d.date, d])), [r.data]);
  if (r.error) return <ErrorBox error={r.error} />;
  if (!r.data) return <Loading />;
  const s = r.data;
  const today = todayIso();
  const now = new Date();
  const month = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  const lead = (month.getDay() + 6) % 7; // Monday first
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells = Array.from({ length: lead + count }, (_, i) => (i < lead ? null : localIso(new Date(month.getFullYear(), month.getMonth(), i - lead + 1)).slice(0, 10)));
  const inMonth = cells.filter((c): c is string => !!c && days.has(c));
  const maxMin = Math.max(30, ...inMonth.map((c) => days.get(c)!.minutes));
  const rest = new Set(s.rest_weekdays);

  return (
    <>
      <PageHead title="Streak">Days in a row with at least one workout that passed the data checks.</PageHead>
      <Card><StreakBadge s={s} /></Card>
      <div className="grid g4" style={{ marginTop: 16 }}>
        <Tile label="Current streak" value={`${s.current} days`} />
        <Tile label="Longest streak" value={`${s.longest} days`} />
        <Tile label="This week" value={s.weekly_goal ? `${s.this_week_sessions} / ${s.weekly_goal}` : `${s.this_week_sessions} days`}
          sub={s.weekly_goal ? 'training days from your plan' : 'days trained'} />
        <Tile label="Days trained" value={fmt.n(s.active_days_total)} sub="all time" />
      </div>
      <div style={{ marginTop: 16 }}>
        <Card title={month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
          sub={`${inMonth.length} day${inMonth.length === 1 ? '' : 's'} trained, ${fmt.n(inMonth.reduce((a, c) => a + days.get(c)!.minutes, 0))} minutes`}
          actions={<div className="seg">
            <button onClick={() => setOffset(offset - 1)} disabled={offset <= -12} aria-label="Previous month">‹</button>
            <button onClick={() => setOffset(0)} className={offset === 0 ? 'on' : ''}>This month</button>
            <button onClick={() => setOffset(offset + 1)} disabled={offset >= 0} aria-label="Next month">›</button>
          </div>}>
          <div className="calendar">
            {WEEKDAYS.map((w) => <div key={w} className="cal-head">{w}</div>)}
            {cells.map((c, i) => {
              if (!c) return <div key={`x${i}`} />;
              const d = days.get(c);
              const wd = (new Date(`${c}T00:00:00`).getDay() + 6) % 7;
              const cls = d ? 'done' : c > today ? 'future' : rest.has(wd) ? 'rest' : 'missed';
              return (
                <div key={c} className={`cal-day ${cls} ${c === today ? 'today' : ''}`}
                  style={d ? { ['--fill' as string]: `${0.45 + 0.55 * Math.min(1, d.minutes / maxMin)}` } : undefined}
                  title={d ? `${d.workouts} workout${d.workouts === 1 ? '' : 's'}, ${Math.round(d.minutes)} min` : cls === 'rest' ? 'planned rest day' : undefined}>
                  <span>{Number(c.slice(8))}</span>
                  {d && <small>{Math.round(d.minutes)}′</small>}
                </div>
              );
            })}
          </div>
          <div className="legend">
            <span><i style={{ background: 'var(--accent)' }} />trained (darker = longer)</span>
            <span><i style={{ background: 'var(--surface-2)', border: '1px dashed var(--axis)' }} />planned rest day</span>
          </div>
        </Card>
      </div>
      <div className="note" style={{ marginTop: 12 }}>
        {s.rest_weekdays.length
          ? <>Rest days in your plan ({s.rest_weekdays.map((i) => WEEKDAYS[i]).join(', ')}) keep your streak going without adding to it. <Link to="/plan">Change your plan</Link></>
          : <>Every day counts right now. <Link to="/plan">Set up a weekly plan</Link> and its rest days won't break your streak.</>}
      </div>
    </>
  );
}
