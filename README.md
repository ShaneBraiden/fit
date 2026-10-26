# FitMine: fitness tracking with data-mined predictions

Users sign up, record workouts on their phone (GPS tracking for runs, walks and rides, or a manual log for gym, HIIT, yoga and swims) or on the web, and see predictions built from their own data:

- **Fitness level** (Beginner to Elite) from their profile and last 8 weeks of workouts
- **Training style** (runner, lifter, yogi, …) from their mix of workouts
- **Try next**: exercises people usually add to the ones they just did
- **Weekly routine**: the order of workouts they repeat
- **Data checks**: GPS glitches, impossible speeds and copied recordings are flagged and left out of their stats
- **Routes**: popular routes near them, and the phases (warm-up, fast, recovery…) inside each run

It has three parts:

| Part | Folder | What it is |
|---|---|---|
| **Server** | `server/` | Python 3.11. Accounts and token auth, the user's own workouts, the model-training pipeline (every algorithm written from scratch in NumPy) and a FastAPI API. |
| **Web app** | `web/` | React + ECharts + Leaflet. Sign in, the same screens as the phone, and admin-only "How the models work" pages. |
| **Mobile app** | `mobile/` | Expo React Native. Sign in, live GPS recording, manual logging, and the predictions. |

## One algorithm per feature

The models are trained on a synthetic population (1,010 users, about 28,000 workouts over 8 weeks) whose patterns were planted on purpose, so every model can be scored against the known answer. They are then applied to each real user's own workouts.

| Feature | Algorithm (all in `server/fitmine/algorithms/`) | Score on the planted truth (seed 42) |
|---|---|---|
| Data cleaning | Rule-based label/unit fixes, re-sync duplicate detection, **kNN imputation** (k = 5) | 280 / 280 duplicates; HR imputation RMSE 3.9 bpm (mean baseline 19.4) |
| Try next | **FP-Growth** + association rules (support ≥ 2%, confidence ≥ 60%) | 8 / 8 planted rules |
| Fitness level | **C4.5** decision tree (gain ratio, depth ≤ 6) | CV accuracy 71.7% (baseline 40.6%), macro-F1 0.677; 72.7% on unassessed users |
| Training style | **k-means** with k-means++ seeding (k = 5) | ARI 0.869 vs the 5 planted personas |
| Data checks | Domain rules + stream fingerprints + **IQR fences** and **Isolation Forest** agreeing | 93.9% precision / 99.8% recall on faulty workouts; 22 / 22 spoofed profiles |
| Weekly routine | **GSP** sequential patterns (max gap 4 days) | 4 / 4 planted routines |
| Popular routes | **DBSCAN** on **Hausdorff** distances between tracks | 8 / 8 planted routes |
| Run phases | Binary-segmentation **change-point** detection on speed | boundary F1 0.865 |

Every from-scratch algorithm is cross-checked against scikit-learn, SciPy or mlxtend (11 / 11 pass); see the web app's Verification page and `pytest`.

**How a real user's predictions are made.** The server keeps each user's workouts in its own tables. On every profile request it takes the user's workouts from the last 8 weeks that passed the data checks, builds the same features the models were trained on (sessions and minutes per week, activity mix, intensity, run pace, longest distance), and runs the trained C4.5 tree and the nearest k-means centre on them. Weekly figures are divided by the weeks the account has existed (1 to 8), so a new user is not penalised. VO2max is the user's own value if they enter one, otherwise estimated from their best recent run (Daniels' VDOT), otherwise from their resting heart rate (Uth's ratio).

## Running it (Windows)

### 1. Server

```bash
cd server
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m fitmine.pipeline run --regenerate
.venv\Scripts\python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

- **Database:** Supabase (Postgres) when `DATABASE_URL` is set, otherwise a local SQLite file (`server/data/fitmine.db`). See [Supabase](#supabase).
- **Admins:** set `ADMIN_EMAILS` (comma-separated) in `server/.env` or on Render. Accounts with those emails see the model pages on the web.
- **Pipeline options:** `--seed`, `--users` and `--skip-verify`. A full run takes about 3 minutes.
- **API docs:** http://localhost:8000/docs
- **Tests:** `.venv\Scripts\python -m pytest tests`. They always use the local SQLite file, never `DATABASE_URL`; the API tests need the pipeline to have run first.
- **What the pipeline rebuilds:** only the synthetic training tables. Accounts and the workouts users record (`accounts`, `auth_tokens`, `live_users`, `live_workouts`, `live_exercises`, `live_streams`) are never touched.

### Accounts and security

- Passwords are hashed with scrypt (random salt per password). Sign-in returns a random token; the server stores only its SHA-256 and it expires after 90 days. Sign-out revokes it.
- Every `/api/me/*` request needs `Authorization: Bearer <token>`, and the token alone decides whose data is read or written.
- Ten failed sign-ins for one email within 15 minutes are refused for the rest of that window.
- The phone keeps the token in the device's secure store (Keychain / Keystore); the web app keeps it in `localStorage`.

### Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. Open **Connect** and copy the **Session pooler** URI (port 5432).
3. Put it in `server/.env` (gitignored): `DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`
4. Run the pipeline. It creates every table in a `fitmine` schema (set `DB_SCHEMA` to change it), which Supabase's public REST API doesn't expose.

On Render, set `DATABASE_URL` and `ADMIN_EMAILS` on the `fitmine-api` service.

### 2. Web app

```bash
cd web
npm install
npm run dev
```

- **Open:** http://localhost:5173 and create an account.
- **API address:** `npm run dev` uses `localhost:8000`; `npm run build` uses the deployed API (`web/.env.production`). Set `VITE_API_URL` to override either.
- GPS tracking on the web works best in a phone browser; on a laptop, log workouts manually.

### 3. Mobile app

```bash
cd mobile
npm install
npx expo start
```

- **On a phone:** scan the QR code with Expo Go, or press `w` to open it in a browser.
- **Server address:** read from `mobile/.env` (`EXPO_PUBLIC_API_URL`), which points at the deployed API. It can be changed under "Server settings" on the sign-in screen or in the Profile tab. For a laptop server use `http://<laptop-ip>:8000` on the same Wi-Fi.
- **Recording:** keep the app open while recording; the screen stays on. Location permission is only used during a recording.
- On Render's free plan the API sleeps after 15 minutes idle, so the first request after that can take about a minute.

To rebuild the APK:

```bash
node %USERPROFILE%\.claude\skills\iverto-app-builder\scripts\build-apk.mjs --dir mobile
```

**Regenerating API types:** with the server running, `npm run gen:api` in `web/` or `mobile/` rebuilds the TypeScript types from `/openapi.json`.

## Layout

```
server/
  fitmine/data/          generator.py (synthetic training data + ground truth), store.py (SQLite or Supabase), geo.py
  fitmine/algorithms/    from-scratch algorithms, one module each, no domain knowledge
  fitmine/analyses/      one module per feature: cleaning, suggestions, fitness_level, personas, data_checks,
                         routines_routes; verify (library cross-checks)
  fitmine/pipeline.py    trains everything, writes artifacts/*.json and artifacts/models.pkl
  fitmine/models_runtime.py  applies the trained models to one user's workouts
  fitmine/live.py        accounts, tokens, the user's own workouts, the live profile
  api/                   FastAPI: routers/account.py (auth + /api/me), routers/models.py (admin model reports)
  tests/                 pytest
web/src/pages/app/       Today, Log, Insights, Routes, Profile, Workout
web/src/pages/models/    admin model pages, one per feature, and Verification
mobile/app/              expo-router screens: sign-in, tabs (today, record, insights, routes, profile), workout/[id]
```
