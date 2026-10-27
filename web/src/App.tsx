import { useState } from 'react';
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { api } from './api/client';
import { useAuth } from './auth';
import FriendsPage, { ComparePage } from './pages/app/Friends';
import Insights from './pages/app/Insights';
import Log from './pages/app/Log';
import Muscles from './pages/app/Muscles';
import PlanPage from './pages/app/Plan';
import Profile from './pages/app/Profile';
import RoutesPage from './pages/app/Routes';
import StreakPage from './pages/app/Streak';
import Today from './pages/app/Today';
import Workout from './pages/app/Workout';
import Login from './pages/Login';
import Cleaning from './pages/models/Cleaning';
import DataChecks from './pages/models/DataChecks';
import FitnessLevel from './pages/models/FitnessLevel';
import ModelsOverview from './pages/models/Overview';
import Personas from './pages/models/Personas';
import RoutinesRoutes from './pages/models/RoutinesRoutes';
import Suggestions from './pages/models/Suggestions';
import Verification from './pages/models/Verification';

const APP = [
  { to: '/', icon: '◎', label: 'Today', end: true },
  { to: '/log', icon: '+', label: 'Log workout' },
  { to: '/plan', icon: '▤', label: 'Weekly plan' },
  { to: '/streak', icon: '✹', label: 'Streak' },
  { to: '/muscles', icon: '◐', label: 'Muscles' },
  { to: '/friends', icon: '⚇', label: 'Friends' },
  { to: '/insights', icon: '✦', label: 'Insights' },
  { to: '/routes', icon: '⌁', label: 'Routes' },
  { to: '/profile', icon: '☺', label: 'Profile' },
];
const MODELS = [
  { to: '/models', label: 'Overview', end: true },
  { to: '/models/cleaning', label: 'Data cleaning' },
  { to: '/models/fitness-level', label: 'Fitness level' },
  { to: '/models/training-style', label: 'Training style' },
  { to: '/models/suggestions', label: 'Try next' },
  { to: '/models/data-checks', label: 'Data checks' },
  { to: '/models/routines-routes', label: 'Routines & routes' },
  { to: '/models/verification', label: 'Verification' },
];

type Theme = 'system' | 'light' | 'dark';

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) || 'system');
  const apply = (t: Theme) => {
    setTheme(t);
    if (t === 'system') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = t;
    try { localStorage.setItem('fitmine-theme', t); } catch { /* storage unavailable */ }
  };
  return (
    <div className="seg" aria-label="Theme" style={{ margin: '18px 8px 0' }}>
      {(['system', 'light', 'dark'] as Theme[]).map((t) => (
        <button key={t} className={theme === t ? 'on' : ''} onClick={() => apply(t)}>{t}</button>
      ))}
    </div>
  );
}

export default function App() {
  const { ready, account, signOut } = useAuth();
  if (!ready) return <div className="loading">Loading…</div>;
  if (!account) return <Login />;
  const logout = async () => {
    try { await api('/api/auth/logout', undefined, 'POST'); } catch { /* signing out locally is enough */ }
    signOut();
  };
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <div className="brand-mark">F</div>
          <div><strong>FitMine</strong><small>Workouts and fitness</small></div>
        </div>
        <nav className="nav">
          {APP.map((n) => <NavLink key={n.to} to={n.to} end={n.end}><span className="code">{n.icon}</span>{n.label}</NavLink>)}
          {account.is_admin && <>
            <div className="nav-section">How the models work</div>
            {MODELS.map((n) => <NavLink key={n.to} to={n.to} end={n.end}><span className="code">·</span>{n.label}</NavLink>)}
          </>}
        </nav>
        <div className="user-box">
          <div><strong>{account.name}</strong></div>
          <div className="muted">{account.email}</div>
          <button className="linkish" style={{ marginTop: 6 }} onClick={logout}>Sign out</button>
        </div>
        <ThemeToggle />
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/log" element={<Log />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/streak" element={<StreakPage />} />
          <Route path="/muscles" element={<Muscles />} />
          <Route path="/friends" element={<FriendsPage />} />
          <Route path="/friends/:id" element={<ComparePage />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/routes" element={<RoutesPage />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/workout/:id" element={<Workout />} />
          {account.is_admin && <>
            <Route path="/models" element={<ModelsOverview />} />
            <Route path="/models/cleaning" element={<Cleaning />} />
            <Route path="/models/fitness-level" element={<FitnessLevel />} />
            <Route path="/models/training-style" element={<Personas />} />
            <Route path="/models/suggestions" element={<Suggestions />} />
            <Route path="/models/data-checks" element={<DataChecks />} />
            <Route path="/models/routines-routes" element={<RoutinesRoutes />} />
            <Route path="/models/verification" element={<Verification />} />
          </>}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
