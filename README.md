# ATLAS — Astram-Trained Live-Adaptive System

> **Event-Driven Congestion forecasting & response planning, built entirely from a city's own incident history.**
> Zero external feeds. Zero API keys. Zero cloud dependencies. One CSV → a precognitive ops control room.

ATLAS is a self-contained traffic intelligence system that turns the **Astram event dataset** (Bengaluru, ~8,200 incidents, Nov 2023 → Apr 2024) into:

- **Behavioral Fingerprints** per corridor — every junction's recurring rhythm, learned without any calendar or holiday list.
- **Cascade Graphs** — Hawkes-style spatio-temporal point process modelling how one breakdown triggers the next.
- **Event Severity Index (ESI)** — calibrated regression with conformal 90% prediction intervals.
- **Counterfactual Deployment Audit** — the single most powerful number in the pitch: *"if ATLAS had been live, X officer-hours saved, response-time gini reduced from A to B."*
- **Drop-an-event simulator** — right-click anywhere on the map, drop a rally / festival / VIP movement / construction zone, and watch ATLAS forecast cascading impact and recommend manpower, barricades, and diversions in real time.

---

## What ATLAS answers (the brief)

| Brief sub-question | ATLAS surface |
|---|---|
| Forecast event-related traffic impact | Cascade ripple + ESI with conformal interval |
| Recommend optimal manpower | Deployment arcs (station → deployment point with officer count + ETA) |
| Recommend barricading | Pin drops at predicted closure-trigger junctions |
| Recommend diversion | Highlighted alternate corridors with predicted residual load |
| "Event impact not quantified today" | Live ESI counter + officer-hours-saved counter |
| "Experience-driven deployment" | Side-by-side: current vs ATLAS allocation |
| "No post-event learning" | Predictability Score per corridor, Bayesian online update after each event |

---

## Tech stack (all free, all local)

- **Backend** — Python 3.10+, FastAPI, pandas, scikit-learn, scipy, statsmodels.
- **Frontend** — React 18 + Vite, deck.gl, react-map-gl, MapLibre GL, D3.
- **Map tiles** — Carto dark raster (public) / OSM raster fallback. **No Mapbox token required.**
- **Co-pilot** — retrieval-grounded templated NLG. No external LLM API. (Optional: plug a local Phi-3 / Llama-3 8B for paraphrasing — pure local inference.)

---

## Quick start

> **Windows + corp/UNC home drive note.** Network-mapped drives (e.g. `H:\`)
> often refuse to spawn the `esbuild.exe` that Vite invokes at build time
> (Group Policy / AppLocker). The repo ships a `setup-frontend.ps1` script
> that mirrors the frontend into `%LOCALAPPDATA%\atlas-frontend` and runs
> Vite from there. The backend has no such restriction and runs fine in
> place on the network drive. If you are on a regular Linux/Mac/local-disk
> Windows setup, just `npm install && npm run dev` inside `frontend/`.

### 1. One-time setup

```powershell
# Backend (runs in place on H:\ or wherever the repo lives)
cd backend
pip install -r requirements.txt

# Frontend (mirrored to %LOCALAPPDATA%\atlas-frontend due to UNC restrictions)
cd ..
.\setup-frontend.ps1 -Mode install
```

### 2. Build the intelligence artifacts (one-shot)

```powershell
cd backend
python -m pipeline.run_all
```

This produces `backend/artifacts/*.{parquet,json,pkl}` — the precomputed
intelligence the API serves at boot. Roughly 60s end-to-end on the bundled
Bengaluru dataset.

### 3. Run ATLAS

Open two terminals.

**Terminal 1 — backend (`http://localhost:8000`)**

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend (`http://localhost:5173`)**

```powershell
.\setup-frontend.ps1 -Mode dev
```

Open http://localhost:5173 → click anywhere on the map → drop an event →
ATLAS predicts the cascade, recommends manpower, barricades, and diversions.

### 4. (Optional) Production build

```powershell
.\setup-frontend.ps1 -Mode build
# static SPA at  %LOCALAPPDATA%\atlas-frontend\dist\
```

---

## Repository layout

```
phase2/
├── backend/                Python FastAPI + ML pipeline
│   ├── app/                Live API
│   │   ├── main.py
│   │   ├── core/           Config + data loaders
│   │   ├── api/            One router per concern
│   │   └── models/         Wrappers around precomputed artifacts
│   ├── pipeline/           Reproducible 7-step build
│   │   ├── step01_clean.py
│   │   ├── step02_fingerprint.py
│   │   ├── step03_cascade.py
│   │   ├── step04_esi.py
│   │   ├── step05_stations.py
│   │   ├── step06_audit.py
│   │   ├── step07_corridors.py
│   │   └── run_all.py
│   ├── artifacts/          Pipeline output (.gitignored)
│   └── requirements.txt
├── frontend/               React + deck.gl ops control room
│   ├── src/
│   │   ├── App.jsx, main.jsx
│   │   ├── components/     MapCanvas, EventDropPanel, KpiBar, ...
│   │   ├── layers/         deck.gl layer factories
│   │   ├── hooks/, api/, utils/, styles/
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── setup-frontend.ps1      One-shot mirror + install + run helper
└── Astram event data_anonymized*.csv   Source dataset
```

---

## API surface

| Endpoint | What it returns |
|---|---|
| `GET  /api/health`            | service + artifact load status |
| `GET  /api/city`              | dataset summary + DVI per zone |
| `GET  /api/corridors`         | corridor polylines (GeoJSON) |
| `GET  /api/corridors/state`   | per corridor: 24h breathing + ESI by hour |
| `GET  /api/corridors/{name}/fingerprint` | per-corridor fingerprint detail |
| `GET  /api/stations`          | station list + perf profiles |
| `GET  /api/cascade`           | cascade nodes & significance-tested edges |
| `GET  /api/audit`             | counterfactual deployment audit summary |
| `GET  /api/fingerprint`       | full city + per-corridor fingerprint payload |
| `POST /api/simulate`          | the click-to-drop simulator (cascade + plan + diversions) |
| `POST /api/copilot/query`     | retrieval-grounded NL Q&A with citations |

---

## What ATLAS does NOT do (honest framing)

- **No claim of "4 years" of data.** The dataset is 5 months. We say "thousands of incidents" instead.
- **No live monsoon claim.** The window has no monsoon — what we ship is a **Drainage Vulnerability Index** mined from the dataset itself, surfaced as a "Stress Mode" toggle.
- **No external LLM.** The co-pilot is templated NLG fed by SQL-style queries over the parquet. No data leaves the building.
- **No fabricated cascade GNN.** The cascade graph is a **multivariate Hawkes-style point process** with permutation-tested edge significance — defensible against any stats-savvy judge.
- **ESI ships with a 90% conformal prediction interval**, not a fake point estimate.

---

## The pitch in one sentence

> ATLAS reads a city's own incident history and rebuilds it as a precognitive, self-contained, self-healing nerve system — no sensors, no APIs, no external dependencies, deployable to any Indian city by uploading one CSV.

---

## Verified numbers (from the bundled Bengaluru run)

| Metric | Value |
|---|---|
| Events ingested | **8,041** (after BBOX filter, from 8,173 raw) |
| Date range | 2023-11-10 → 2024-04-08 |
| Corridors profiled | 21 (with predictability score, 24h breathing pattern, anomaly day list) |
| Police stations profiled | 54 (with hourly load, response/resolution stats, top causes) |
| Cascade graph | 466 significance-tested edges across 54 stations |
| ESI model | GradientBoosting, RMSE(log)=0.96, conformal q90=1.54 → 90% prediction interval |
| Counterfactual audit | **78.4 officer-hours saved** (extrapolated), avg response 10.0 → 9.5 min, P90 13.0 → 12.3 min |
| Equity Gini (response across zones) | 0.031 → 0.029 (lower is fairer) |
| Pipeline runtime | ~60s end-to-end |
| Frontend build | 1,305 modules, 1.9 MB / 526 kB gzipped |

These are real numbers produced by `python -m pipeline.run_all` on the
shipped CSV. Nothing is mocked.

---

## What you'll see in the UI

- **Top bar:** brand · KPI bar (events analyzed · corridors profiled · officer-hours saved · response-time delta)
- **Tabbed left/right side panels:** *Ops · Fingerprint · Audit · Co-pilot*
- **Map (deck.gl + MapLibre):**
  - corridor breathing layer (color = ESI for the current hour, opacity pulses with the learned cadence)
  - police-station glowing dots (radius = event volume)
  - cascade ripple animation when an event is dropped (concentric expanding rings + secondary event halos sized by uncertainty)
  - deployment arcs from station → deployment point with officer counts and ETA
  - barricade pins around the closure perimeter
  - diversion lines highlighting the recommended alternate corridor
- **Bottom audit ribbon:** events audited · response delta · officer-hours saved · equity Gini · P90 tail.
- **Co-pilot:** retrieval-grounded answers, every number has a citation back to the dataset row count. If the filters resolve zero rows the co-pilot **refuses** instead of hallucinating.

---

## Repository layout
