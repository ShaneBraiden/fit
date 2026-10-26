import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Account, api, getToken, setToken, SIGNED_OUT } from './api/client';

/** Who is signed in. The token lives in localStorage; the account is re-read from /api/me on load. */
interface Auth {
  ready: boolean;
  account: Account | null;
  signIn: (token: string, account: Account) => void;
  setAccount: (a: Account) => void;
  signOut: () => void;
}

const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);
  const signOut = useCallback(() => { setToken(null); setAccount(null); }, []);

  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api<Account>('/api/me').then(setAccount).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);
  useEffect(() => {
    window.addEventListener(SIGNED_OUT, signOut);
    return () => window.removeEventListener(SIGNED_OUT, signOut);
  }, [signOut]);

  const value = useMemo<Auth>(() => ({
    ready, account, setAccount, signOut,
    signIn: (token, acc) => { setToken(token); setAccount(acc); },
  }), [ready, account, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  const a = useContext(Ctx);
  if (!a) throw new Error('useAuth outside AuthProvider');
  return a;
}
