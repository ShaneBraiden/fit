import { useCallback, useEffect, useRef, useState } from 'react';

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

export async function api<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch { /* not JSON */ }
    throw new Error(detail);
  }
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
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}

/** A POST re-run whose result replaces the cached report once it arrives. */
export function useRun<P, T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const run = useCallback((params: P) => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    return api<T>(path, params).then((d) => { if (id === seq.current) setData(d); return d; })
      .catch((e: Error) => { if (id === seq.current) setError(e.message); return null; })
      .finally(() => { if (id === seq.current) setLoading(false); });
  }, [path]);
  return { data, error, loading, run, setData };
}
