import { useCallback, useEffect, useState } from 'react';
import type { components } from './schema';

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

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

const TOKEN_KEY = 'fitmine.token';
/** Fired when the server rejects the stored token; the auth provider signs the user out. */
export const SIGNED_OUT = 'fitmine:signed-out';

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable: the session lasts until the tab closes */ }
}

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export async function api<T>(path: string, body?: unknown, method?: Method): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: method ?? (body === undefined ? 'GET' : 'POST'), headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Can't reach the FitMine server. Check your connection and try again.", 0);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      detail = typeof j.detail === 'string' ? j.detail
        : Array.isArray(j.detail) ? j.detail.map((d: { msg?: string; loc?: string[] }) => `${d.loc?.slice(-1)[0] ?? ''}: ${d.msg}`).join('; ')
          : JSON.stringify(j.detail);
    } catch { /* not JSON */ }
    if (res.status === 401 && token) window.dispatchEvent(new Event(SIGNED_OUT));
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface Loadable<T> { data: T | null; error: string | null; loading: boolean; reload: () => void }

/** GET on mount. Keeps the previous data while reloading (no skeleton flash). */
export function useGet<T>(path: string | null): Loadable<T> {
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
  }, [path, tick]);
  return { data, error, loading, reload: useCallback(() => setTick((t) => t + 1), []) };
}

/** Local time as the server expects it: "YYYY-MM-DDTHH:MM:SS", no time zone. */
export function localIso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** Today's local date, "YYYY-MM-DD": the streak and the week follow the user's calendar. */
export const todayIso = () => localIso(new Date()).slice(0, 10);
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const when = {
  date: (iso: string | null | undefined) => (iso ? new Date(iso.replace(' ', 'T'))
    .toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) : ''),
  time: (iso: string) => new Date(iso.replace(' ', 'T')).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
};

export function pace(minPerKm: number | null | undefined): string {
  if (minPerKm == null || !isFinite(minPerKm)) return '–';
  const m = Math.floor(minPerKm);
  return `${m}:${String(Math.round((minPerKm - m) * 60)).padStart(2, '0')}/km`;
}

const REASONS: Record<string, string> = {
  hr_spike: 'heart-rate readings above any human maximum',
  hr_flatline: 'heart rate stuck at one value',
  hr_dropout: 'heart-rate sensor dropped out',
  gps_teleport: 'GPS jumped kilometres in seconds',
  car_speed: 'speed only possible in a vehicle',
  calorie_mismatch: "calories don't match the effort",
  duplicate_of_other_user: "identical to someone else's recording",
};
export function reasonText(r: string): string {
  return r.split(', ').filter(Boolean)
    .map((x) => REASONS[x] ?? (x.startsWith('unusual for a') ? 'very unusual numbers for this kind of workout' : x)).join(' · ');
}

export const splitWords = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2');
