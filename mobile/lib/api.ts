import { useCallback, useEffect, useState } from 'react';
import type { components } from './schema';
import { useSession } from './session';

export type S = components['schemas'];
export type UserSummary = S['UserSummary'];
export type Profile = S['Profile'];
export type WorkoutItem = S['WorkoutItem'];
export type WorkoutDetail = S['WorkoutDetail'];
export type Recommendation = S['Recommendation'];
export type Alert = S['Alert'];
export type UserRoutes = S['UserRoutes'];
export type UploadRequest = S['UploadRequest'];
export type UploadResult = S['UploadResult'];

export async function request<T>(base: string, path: string, body?: unknown): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  try {
    const res = await fetch(`${base}${path}`, {
      method: body === undefined ? 'GET' : 'POST', signal: ctrl.signal,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = `${res.status}`;
      try { const j = await res.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* not JSON */ }
      throw new Error(detail);
    }
    return (await res.json()) as T;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes('Aborted') || msg.includes('Network request failed') || msg.includes('Failed to fetch')) {
      throw new Error(`Can't reach the FitMine server at ${base}. Is it running, and is the phone on the same Wi-Fi?`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export function useApi() {
  const { apiUrl } = useSession();
  return useCallback(<T,>(path: string, body?: unknown) => request<T>(apiUrl, path, body), [apiUrl]);
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
  date: (iso: string | null | undefined) => {
    if (!iso) return '';
    const d = new Date(iso.replace(' ', 'T'));
    return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  },
  time: (iso: string) => new Date(iso.replace(' ', 'T')).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
  reason: (r: string) => r.split(', ').map((x) => REASONS[x] ?? x).join(' · '),
};

const REASONS: Record<string, string> = {
  hr_spike: 'heart-rate spikes above any human maximum',
  hr_flatline: 'heart rate frozen at one value',
  hr_dropout: 'heart-rate sensor dropped out',
  gps_teleport: 'GPS jumped kilometres in seconds',
  car_speed: 'speed only possible in a vehicle',
  calorie_mismatch: 'calories don\'t match the effort',
  duplicate_of_other_user: 'identical to another user\'s recording',
  'shared stream fingerprint': 'identical to another user\'s recording',
};
