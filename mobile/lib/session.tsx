import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react';
import { Platform } from 'react-native';
import type { components } from './schema';

type Account = components['schemas']['Account'];

/** Which server to talk to, and who is signed in. The sign-in token is kept in the
 *  device's secure store (Keychain / Keystore). */
interface Session {
  ready: boolean;
  apiUrl: string;
  token: string | null;
  account: Account | null;
  signIn: (token: string, account: Account) => void;
  setAccount: (a: Account) => void;
  signOut: () => void;
}

// The app always talks to the hosted FitMine API; EXPO_PUBLIC_API_URL can point a dev build elsewhere.
const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'https://fit-m7v5.onrender.com').replace(/\/+$/, '');
const TOKEN_KEY = 'fitmine.token';

const Ctx = createContext<Session | null>(null);

async function load(key: string): Promise<string | null> {
  try { return await AsyncStorage.getItem(key); } catch { return null; }
}
function save(key: string, value: string | null) {
  (value == null ? AsyncStorage.removeItem(key) : AsyncStorage.setItem(key, value)).catch(() => undefined);
}
// SecureStore has no web implementation; the browser build falls back to local storage.
async function loadToken(): Promise<string | null> {
  if (Platform.OS === 'web') return load(TOKEN_KEY);
  try { return await SecureStore.getItemAsync(TOKEN_KEY); } catch { return null; }
}
function saveToken(value: string | null) {
  if (Platform.OS === 'web') return save(TOKEN_KEY, value);
  (value == null ? SecureStore.deleteItemAsync(TOKEN_KEY) : SecureStore.setItemAsync(TOKEN_KEY, value)).catch(() => undefined);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [account, setAcc] = useState<Account | null>(null);
  useEffect(() => {
    Promise.all([loadToken(), load('fitmine.account')]).then(([tk, acc]) => {
      if (tk) setToken(tk);
      if (tk && acc) { try { setAcc(JSON.parse(acc)); } catch { /* re-fetched on next profile load */ } }
      setReady(true);
    });
  }, []);
  // Stable callbacks: useApi depends on them, and every fetch re-runs when useApi changes.
  const actions = useMemo(() => ({
    signIn: (tk: string, acc: Account) => { setToken(tk); setAcc(acc); saveToken(tk); save('fitmine.account', JSON.stringify(acc)); },
    setAccount: (acc: Account) => { setAcc(acc); save('fitmine.account', JSON.stringify(acc)); },
    signOut: () => { setToken(null); setAcc(null); saveToken(null); save('fitmine.account', null); },
  }), []);
  const value: Session = { ready, apiUrl: API_URL, token, account, ...actions };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error('useSession outside SessionProvider');
  return s;
}
