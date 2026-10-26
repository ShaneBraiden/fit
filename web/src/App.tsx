import { useState } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';
import Overview from './pages/Overview';
import Preprocess from './pages/Preprocess';
import Olap from './pages/Olap';
import Association from './pages/Association';
import Classification from './pages/Classification';
import Clustering from './pages/Clustering';
import Outliers from './pages/Outliers';
import Sequences from './pages/Sequences';
import Verification from './pages/Verification';

const UNITS = [
  { to: '/preprocess', code: 'U1', label: 'Preprocessing' },
  { to: '/olap', code: 'U2', label: 'Warehouse & OLAP' },
  { to: '/association', code: 'U3', label: 'Association rules' },
  { to: '/classification', code: 'U4', label: 'Classification' },
  { to: '/clustering', code: 'U5', label: 'Clustering' },
  { to: '/outliers', code: 'U6', label: 'Outlier detection' },
  { to: '/sequences', code: 'U7', label: 'Sequences & routes' },
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
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <div className="brand-mark">F</div>
          <div><strong>FitMine</strong><small>Workout data mining</small></div>
        </div>
        <nav className="nav">
          <NavLink to="/" end><span className="code">◎</span>Overview</NavLink>
          <div className="nav-section">Syllabus units</div>
          {UNITS.map((u) => (
            <NavLink key={u.to} to={u.to}><span className="code">{u.code}</span>{u.label}</NavLink>
          ))}
          <div className="nav-section">Correctness</div>
          <NavLink to="/verify"><span className="code">✓</span>Verification</NavLink>
        </nav>
        <ThemeToggle />
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/preprocess" element={<Preprocess />} />
          <Route path="/olap" element={<Olap />} />
          <Route path="/association" element={<Association />} />
          <Route path="/classification" element={<Classification />} />
          <Route path="/clustering" element={<Clustering />} />
          <Route path="/outliers" element={<Outliers />} />
          <Route path="/sequences" element={<Sequences />} />
          <Route path="/verify" element={<Verification />} />
        </Routes>
      </main>
    </div>
  );
}
