import { useCallback, useEffect, useState } from 'react';
import type { components } from './schema';
import { useSession } from './session';

export type S = components['schemas'];
export type Account = S['Account'];
export type AuthResult = S['AuthResult'];
export type SignupRequest = S['SignupRequest'];
export type Profile = S['Profile'];
export type WorkoutItem = S['WorkoutItem'];
export type WorkoutDetail = S['WorkoutDetail'];
export type Recommendation = S['Recommendation'];
export type Alert = S['Alert'];
export type UserRoutes = S['UserRoutes'];
export type RecordRequest = S['RecordRequest'];
export type RecordResult = S['RecordResult'];
export type Catalog = S['Catalog'];
export type ExerciseLoad = S['ExerciseLoad'];
export type PlanDay = S['PlanDay-Output'];
export type PlanIn = S['PlanIn'];
export type PlanWeek = S['PlanWeek'];
export type Streak = S['Streak'];
export type MuscleReport = S['MuscleReport'];
export type MuscleProgress = S['MuscleProgress'];
export type Friends = S['Friends'];
export type FriendSummary = S['FriendSummary'];
export type Comparison = S['Comparison'];

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function request<T>(base: string, path: string, opts: { method?: Method; body?: unknown; token?: string | null } = {}): Promise<T> {
  const method = opts.method ?? (opts.body === undefined ? 'GET' : 'POST');
  const ctrl = new AbortController();
  // A sleeping free-tier server can take about a minute to wake up.
  const timer = setTimeout(() => ctrl.abort(), 70000);
  try {
    const headers: Record<string, string> = {};
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
    const res = await fetch(`${base}${path}`, {
      method, signal: ctrl.signal, headers, body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
    if (!res.ok) {
      let detail = `${res.status}`;
      try {
        const j = await res.json();
        detail = typeof j.detail === 'string' ? j.detail
          : Array.isArray(j.detail) ? j.detail.map((d: { msg?: string; loc?: string[] }) => `${d.loc?.slice(-1)[0] ?? ''}: ${d.msg}`).join('; ')
            : JSON.stringify(j.detail);
      } catch { /* not JSON */ }
      throw new ApiError(detail, res.status);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes('Abort') || msg.includes('Network request failed') || msg.includes('Failed to fetch')) {
      throw new ApiError(`Can't reach the FitMine server. Check your connection and try again.`, 0);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/** Calls the API as the signed-in user; an expired session signs the user out. */
export function useApi() {
  const { apiUrl, token, signOut } = useSession();
  return useCallback(async <T,>(path: string, body?: unknown, method?: Method) => {
    try {
      return await request<T>(apiUrl, path, { body, method, token });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401 && token) signOut();
      throw e;
    }
  }, [apiUrl, token, signOut]);
}

/** GET with loading / error / refresh; keeps showing old data while refreshing. */
export function useFetch<T>(path: string | null) {
  const api = useApi();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) return;
    let live = true;
    setLoading(true);
    api<T>(path).then((d) => { if (live) { setData(d); setError(null); } })
      .catch((e: Error) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [api, path, tick]);
  return { data, error, loading, reload: useCallback(() => setTick((t) => t + 1), []) };
}

export const fmt = {
  n: (v: number | null | undefined, d = 0) => (v == null ? '–' : v.toFixed(d)),
  pct: (v: number | null | undefined, d = 0) => (v == null ? '–' : `${(v * 100).toFixed(d)}%`),
  pace: (minPerKm: number | null | undefined) => {
    if (minPerKm == null || !isFinite(minPerKm)) return '–';
    const m = Math.floor(minPerKm);
    return `${m}:${String(Math.round((minPerKm - m) * 60)).padStart(2, '0')}/km`;
  },
  clock: (seconds: number) => {
    const s = Math.max(0, Math.round(seconds));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return `${h ? `${h}:` : ''}${String(m).padStart(h ? 2 : 1, '0')}:${String(r).padStart(2, '0')}`;
  },
  date: (iso: string | null | undefined) => {
    if (!iso) return '';
    const d = new Date(iso.replace(' ', 'T'));
    return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  },
  time: (iso: string) => new Date(iso.replace(' ', 'T')).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
  reason: (r: string) => r.split(', ').filter(Boolean).map((x) => REASONS[x] ?? REASON_PREFIX(x)).join(' · '),
};

/** Today's local date, "YYYY-MM-DD": the streak and the week follow the phone's calendar. */
export const todayIso = () => localIso(new Date()).slice(0, 10);
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** Local time as the server expects it: "YYYY-MM-DDTHH:MM:SS", no time zone. */
export function localIso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

const REASONS: Record<string, string> = {
  hr_spike: 'heart-rate readings above any human maximum',
  hr_flatline: 'heart rate stuck at one value',
  hr_dropout: 'heart-rate sensor dropped out',
  gps_teleport: 'GPS jumped kilometres in seconds',
  car_speed: 'speed only possible in a vehicle',
  calorie_mismatch: 'calories don\'t match the effort',
  duplicate_of_other_user: 'identical to someone else\'s recording',
  'shared stream fingerprint': 'identical to someone else\'s recording',
};
const REASON_PREFIX = (r: string) => (r.startsWith('unusual for a') ? 'very unusual numbers for this kind of workout' : r);
