import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';
import { Platform } from 'react-native';

/** Which server to talk to and which demo user is signed in. Both survive restarts. */
interface Session {
  ready: boolean;
  apiUrl: string;
  userId: number | null;
  setApiUrl: (u: string) => void;
  setUserId: (id: number | null) => void;
}

const DEFAULT_URL = Platform.OS === 'web' ? 'http://localhost:8000'
  : (process.env.EXPO_PUBLIC_API_URL ?? 'http://10.0.2.2:8000');

const Ctx = createContext<Session | null>(null);

async function load(key: string): Promise<string | null> {
  try { return await AsyncStorage.getItem(key); } catch { return null; }
}
function save(key: string, value: string | null) {
  (value == null ? AsyncStorage.removeItem(key) : AsyncStorage.setItem(key, value)).catch(() => undefined);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [apiUrl, setUrl] = useState(DEFAULT_URL);
  const [userId, setUser] = useState<number | null>(null);
  useEffect(() => {
    Promise.all([load('fitmine.apiUrl'), load('fitmine.userId')]).then(([u, id]) => {
      if (u) setUrl(u);
      if (id) setUser(Number(id));
      setReady(true);
    });
  }, []);
  const value: Session = {
    ready, apiUrl, userId,
    setApiUrl: (u) => { const clean = u.trim().replace(/\/+$/, ''); setUrl(clean); save('fitmine.apiUrl', clean); },
    setUserId: (id) => { setUser(id); save('fitmine.userId', id == null ? null : String(id)); },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error('useSession outside SessionProvider');
  return s;
}
