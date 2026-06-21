# ATLAS — Implementation Status Report

> **Audience:** internal team handoff document.
> **Purpose:** describe exactly what is built, what works, what is broken,
> and what the open decisions are — so anyone joining can pick up without
> re-discovering things the hard way.
>
> **Companion file:** [README.md](README.md) is the pitch-style overview.
> This file is the honest engineering reality.

---

## 1. Big picture

ATLAS is a self-contained decision-support tool for traffic operations,
built from the Astram event dataset (Bengaluru, Nov 2023 → Apr 2024,
8,173 rows).

The system has three layers:

1. **Offline pipeline** (`backend/pipeline/`) — turns the raw CSV into
   precomputed artifacts (cleaned parquet, ML model, calibration, cascade
   graph, validation report, etc.).
2. **Live API** (`backend/app/`, FastAPI) — serves those artifacts plus a
   click-to-drop simulator.
3. **Web UI** (`frontend/`, React + Vite + deck.gl + MapLibre) — the ops
   console: map, event drop panel, forecast panel, audit ribbon,
   co-pilot, validation/trust display.

Everything runs locally. No external APIs (except the public OSM/Carto
basemap tiles and the Nominatim geocoder used only by the search box).

---

## 2. Repository layout (current state)

```
phase2/
├── backend/
│   ├── app/
│   │   ├── main.py                      FastAPI entrypoint
│   │   ├── core/
│   │   │   ├── config.py                paths + tunables (Settings dataclass)
│   │   │   └── data_loader.py           lazy artifact loaders + helpers
│   │   ├── api/
│   │   │   ├── artifacts_router.py      read-only artifact endpoints
│   │   │   ├── simulator_router.py      POST /api/simulate
│   │   │   └── copilot_router.py        POST /api/copilot/query
│   │   └── models/
│   │       └── simulator.py             ESI + cascade + deployment logic
│   ├── pipeline/                        offline build, eight steps
│   │   ├── step01_clean.py
│   │   ├── step02_fingerprint.py
│   │   ├── step03_cascade.py
│   │   ├── step04_esi.py
│   │   ├── step05_stations.py
│   │   ├── step06_audit.py
│   │   ├── step07_corridors.py
│   │   ├── step08_validation.py         (added in this iteration)
│   │   └── run_all.py
│   ├── scripts/                         ad-hoc inspection scripts
│   │   ├── inspect_text_quality.py      Kannada/script audit
│   │   ├── inspect_taxonomy.py          event_type/event_cause audit
│   │   ├── probe_esi.py                 ESI calibration probe
│   │   └── test_esi_cases.py            two-scenario simulator test
│   └── artifacts/                       pipeline output (gitignored)
├── frontend/
│   ├── src/
│   │   ├── App.jsx, main.jsx
│   │   ├── components/
│   │   │   ├── MapCanvas.jsx            deck.gl + MapLibre wrapper
│   │   │   ├── EventDropPanel.jsx       location search + simulate form
│   │   │   ├── ForecastPanel.jsx        ESI card + driver breakdown + trust
│   │   │   ├── KpiBar.jsx, AuditRibbon.jsx, CopilotPanel.jsx, FingerprintClock.jsx
│   │   ├── layers/index.js              deck.gl layer factories
│   │   ├── hooks/useAnimation.js        throttled animation tick
│   │   ├── api/client.js                axios client + Nominatim geocode
│   │   ├── utils/colors.js              ESI/probability color ramps
│   │   └── styles/globals.css           full app stylesheet
│   ├── vite.config.js                   /api proxied to 127.0.0.1:8000
│   └── package.json
├── setup-frontend.ps1                   corp-safe mirror+install+run helper
├── README.md                            pitch overview
├── STATUS.md                            this file
└── Astram event data_anonymized*.csv    source dataset (~8k rows)
```

---

## 3. Data inventory

### 3.1 Raw schema

The raw CSV has **46 columns** (we previously said 47; we confirmed it
is 46 by direct inspection). Of those:

- **25 columns are actively used or transformed** by the pipeline.
- **21 columns are currently ignored**, mostly because they are either
  empty (`comment`, `map_file`, `meta_data` are 100% null) or low-signal
  (audit IDs, addresses already redundant with lat/lng).

### 3.2 Event taxonomy (audited)

`event_type` is a *workflow flag*, not a category:

| event_type | rows | share |
|---|---|---|
| unplanned | 7,706 | 94.3% |
| planned   | 467   | 5.7% |

`event_cause` is the actual incident kind. Distribution:

| event_cause | rows | share |
|---|---|---|
| vehicle_breakdown | 4,896 | 59.9% |
| others            | 638   | 7.8% |
| pot_holes         | 537   | 6.6% |
| construction      | 480   | 5.9% |
| water_logging     | 458   | 5.6% |
| accident          | 365   | 4.5% |
| tree_fall         | 284   | 3.5% |
| road_conditions   | 170   | 2.1% |
| congestion        | 136   | 1.7% |
| public_event      | 84    | 1.0% |
| procession        | 72    | 0.9% |
| vip_movement      | 20    | 0.2% |
| protest           | 15    | 0.2% |
| Debris            | 12    | 0.1% |
| (others)          | <10 each |

**Implication:** the dataset is overwhelmingly short-duration vehicle
breakdowns. Planning-style events (rally, festival, sports_match, VIP,
protest) together total ~200 rows. Any model claim about "what will an
IPL match do?" stands on very thin evidence.

### 3.3 Language audit (Kannada)

About **13% of `description` rows (870 of 6,813)** are in Kannada
script. Smaller amounts in `address` (31), `end_address` (24),
`reason_breakdown` (14), `cargo_material` (9). Examples:

```
ಬಿಎಂಟಿಸಿ ಬಸ್ ಕೆಟ್ಟು ನಿಂತಿದೆ ಸರ್        — "BMTC bus has broken down sir"
ಊರ್ವಶಿ ಜಂಕ್ಷನ್ ನಲ್ಲಿ ಒಳಚರಂಡಿ ಚೇಂಬರ್…  — drainage chamber at Urvashi junction
```

**Current handling:** none. The pipeline's English-only keyword regex
(`weather_flag`, `event_kw_flag`) silently misses these rows. This is a
known gap — see "Open issues" below.

---

## 4. Pipeline (eight steps)

`python -m pipeline.run_all` runs all eight in order, ~90s on the
shipped dataset.

| Step | File | What it produces |
|---|---|---|
| 01-clean | `step01_clean.py` | `events_clean.parquet` (50 columns including derived features) |
| 02-fingerprint | `step02_fingerprint.py` | `fingerprint.json` — corridor heatmaps, predictability score, anomaly days, DVI by zone |
| 03-cascade | `step03_cascade.py` | `cascade_edges.json` — police-station cascade graph, 466 edges across 54 nodes, permutation-tested |
| 04-esi | `step04_esi.py` | `esi_model.pkl`, `esi_q05.pkl`, `esi_q95.pkl`, `esi_calibration.json` |
| 05-stations | `step05_stations.py` | `stations.json` — per-station perf profiles + hourly load |
| 06-audit | `step06_audit.py` | `audit.json` — counterfactual deployment audit |
| 07-corridors | `step07_corridors.py` | `corridors.geojson`, `corridor_state.json` — synthetic polylines + per-hour ESI |
| 08-validation | `step08_validation.py` | `validation_report.json` — out-of-time holdout metrics, calibration, slices |

### 4.1 Step 01 — cleaning

- Timestamps parsed to IST timezone.
- Bounding-box filter for Bengaluru (~12.70–13.25 lat, 77.35–77.85 lng) drops 132 rows.
- Derives: `duration_min`, `planned_duration_min`, `response_min`,
  `hour`, `dow`, `month`, `is_weekend`, `weather_flag`, `event_kw_flag`,
  `road_closure`, `priority_high`.
- Extracts new features from previously unused columns:
  `desc_len_bucket`, `direction`, `gba_identifier`, `cargo_type`,
  `truck_age`, `was_reassigned`, `has_assigned_officer`,
  `has_distinct_closer`, `has_kgid`, `has_end_address`, `has_route_path`,
  `route_points`, `has_veh_no`, `is_commercial_veh`.

Result: 8,041 rows × 50 columns.

### 4.2 Step 04 — ESI training (current)

- Target: `log(duration_min)`, capped at 12h.
- Model: `GradientBoostingRegressor` (400 trees, depth 4, lr 0.05).
- Features: 9 categorical (one-hot encoded with `min_frequency=10`) + 20 numeric.
- Holdout: random 20% for conformal calibration.
- Also trains two quantile heads (5th and 95th) for direct prediction intervals.

### 4.3 Step 08 — validation report (current numbers)

Out-of-time holdout (latest ~20% of rows by `start_datetime`):

| Metric | Value |
|---|---|
| n_total | 2,380 |
| n_train | 1,904 |
| n_holdout | 476 |
| interval_kind | quantile_90 |
| **MAE (min)** | **35.39** |
| Median AE (min) | 19.64 |
| RMSE (min) | 64.21 |
| MAPE | 0.704 |
| Within 15 min | 0.397 |
| **90% coverage (quantile)** | **0.884** |
| Avg interval width (quantile) | 151.34 min |
| Conformal coverage (legacy) | 0.956 |
| Conformal avg width | 183.69 min |

Per-cause slice:

| Cause | n | MAE (min) | Coverage |
|---|---|---|---|
| vehicle_breakdown | 308 | 25.93 | 0.880 |
| water_logging | 53 | 53.26 | 0.868 |
| tree_fall | 47 | 67.99 | 0.894 |

**Reading:** the model is well-calibrated (coverage near 90%), but
point accuracy is mediocre for high-variance causes. For the planning
kinds (sports_match, rally, etc.) there is **no slice** because there
aren't enough rows.

---

## 5. API surface

| Endpoint | Returns |
|---|---|
| `GET /api/health` | service + per-artifact load status |
| `GET /api/city` | dataset summary + DVI per zone |
| `GET /api/corridors` | corridor polylines (GeoJSON) |
| `GET /api/corridors/state` | per corridor: 24h breathing + ESI by hour |
| `GET /api/corridors/{name}/fingerprint` | per-corridor detail |
| `GET /api/stations` | station list + performance profiles |
| `GET /api/cascade` | cascade nodes + significance-tested edges |
| `GET /api/audit` | counterfactual deployment audit summary |
| `GET /api/fingerprint` | full city + per-corridor fingerprint |
| `GET /api/validation` | model validation report (new) |
| `POST /api/simulate` | click-to-drop simulator: cascade + plan + diversions |
| `POST /api/copilot/query` | retrieval-grounded NL Q&A with citations |

---

## 6. Simulator (the ESI engine)

File: `backend/app/models/simulator.py`.

### 6.1 What it does

For an input (lat, lng, event_kind, expected_size, duration_min,
requires_road_closure):

1. Resolves the **corridor** (nearest dataset row) and **nearest police
   station** (haversine over stations.json).
2. Builds a one-row feature frame matching the model's training schema.
3. Runs the GBM to predict event duration in minutes, plus the two
   quantile heads for a 90% interval.
4. Computes the **ESI score 0–10** by combining operational priors with
   data-driven signals (see 6.2).
5. Computes the **cascade ripple** by walking the cascade graph from
   the seed station, scaling probabilities by ESI.
6. Computes the **deployment plan**: primary officers near the event +
   secondaries near the top first-hop cascade targets.
7. Adds barricades (4 around the event) and diversion lines (3 nearest
   alternate corridors).

### 6.2 ESI formula (current state — under active discussion)

```
duration_norm = clip((effective_duration − p10) / (p90 − p10), 0, 1)
effective_duration = max(GBM_pred, planner_input, kind_prior_min)
                     for planning kinds; else just GBM_pred

ESI = (kind_base[kind]
     + (1.5 if closure else 0)
     + size_pts[size]            # 0 / 1 / 2
     + 2.0 * duration_norm
     + 1.0 * cascade_norm
     + 0.7 * corridor_norm
     ) * night_factor            # 1.1 if 22:00–05:00 IST, else 1.0
ESI = clip(ESI, 0, 10)
```

The response includes a full driver breakdown so a planner can see
exactly where each point came from.

### 6.3 Known issues with the current formula

These were identified by direct probe testing
(`scripts/test_esi_cases.py`):

- **Over-saturation.** `kind_base` for `sports_match` is 5.5; add
  closure (1.5), large size (2.0), strong duration (2.0) and you are
  already at 11 before any data signal contributes. Result: many real
  cases hit the 10.0 ceiling and there is no headroom for data signal
  to discriminate.
- **Insufficient discrimination between similar scenarios.** Two
  stadium events at different times of day, with different
  corridor/cascade context, produce nearly identical scores.
- **Dropdown vs data mismatch.** The UI offers 7 event kinds but the
  dataset only has meaningful support for 3 (`construction` 480,
  `public_event` 84, `procession` 72). Others (`vip_movement` 20,
  `protest`/`rally` 15) cannot be learned reliably.

### 6.4 Fixes already applied in this iteration

| Bug | Fix |
|---|---|
| `cascade_count_by_zone` lookup keyed by zone, but the dict is keyed by police station — pinned `cascade_norm` to 0 for every input | Use `seed_station` for the lookup |
| `duration_min` from the UI was completely ignored by the model | For planning kinds, `effective_duration = max(GBM, planner, kind_prior)` |
| `month/hour` taken from `datetime.utcnow()` so night_factor used UTC, not IST | Switched to IST via `ZoneInfo("Asia/Kolkata")` |
| Officer count derived only from ESI (max 5) | Now scales with size as well (large + ESI 10 → 33 officers) |
| No kind-specific severity prior for planning kinds | Added `KIND_SEVERITY_BASE` table; needs rebalancing per 6.3 |

---

## 7. Frontend (React + Vite + deck.gl)

### 7.1 What's on screen

- **Top bar:** brand block + 4-KPI bar (events analyzed, corridors
  profiled, officer-hours saved, response-time delta).
- **Toolbar (centered, top):** Ops / Fingerprint / Audit / Co-pilot tabs.
- **Map:** dim Carto-light basemap underneath, deck.gl overlays on top
  (corridors color-coded by ESI for the current hour, station glow
  dots, event pin, cascade impact zones with rank + label, deployment
  arcs, barricades, diversions).
- **Left side panel (Ops):** event drop panel — location search
  (Nominatim or "lat,lng"), event kind/size/duration/closure controls,
  Simulate button.
- **Right side panel (Ops):** forecast — ESI card + driver breakdown,
  trust card (confidence %, interval width, evidence count), cascade
  list, deployment list, barricades, diversions.
- **Bottom ribbon:** audit summary numbers.
- **Floating legend (Map guide):** explains the color/symbol meaning;
  hidden on narrow screens.

### 7.2 Recent UX fixes

- Lag fix: animation hook throttled to ~10fps and paused when document
  is hidden. Removed the redundant `corridorGlowLayer` re-render every
  frame.
- Cascade rework: replaced confusing expanding-rings ripple with
  **numbered labeled impact zones** (rank #1..#6 + "% likelihood · ~N
  min" label). Each circle has a tooltip with the source→target detail.
- Map z-order fix: DeckGL now renders as a sibling of the MapLibre
  basemap, not as a child. Overlays were previously hidden underneath
  the basemap.
- Confidence panel: every forecast shows a confidence percentage with
  a plain-language explanation of how it was computed and how many
  historical events back the prediction.

### 7.3 Frontend dev workflow (Windows + corp restrictions)

`H:\` is mapped to a network home drive, and AppLocker blocks
`esbuild.exe` from running on UNC paths. The repo therefore ships
`setup-frontend.ps1` which:

1. Mirrors `frontend/` → `%LOCALAPPDATA%\atlas-frontend` (robocopy /MIR,
   excluding `node_modules`, `dist`, `package-lock.json`).
2. Runs `npm install --ignore-scripts` once.
3. Sets `ESBUILD_BINARY_PATH` to the whitelisted esbuild at
   `C:\Users\$USER\ds\tools\esbuild\esbuild.exe`.
4. Runs `npm run dev` or `npm run build`.

Available modes: `dev`, `build`, `install`, `clean`.

Vite proxy: `/api → http://127.0.0.1:8000` (changed from `localhost`
because Windows can resolve `localhost` to IPv6 and Uvicorn binds to
IPv4 here).

---

## 8. Validation and reliability story

Three different signals are surfaced to the user to convey reliability:

1. **Validation report** (`/api/validation`) — out-of-time MAE/RMSE,
   90% interval coverage, per-cause slice metrics. Numbers in §4.3.
2. **Forecast confidence card** — combines interval width and cascade
   p-value into a 0–100% confidence figure, shown next to every ESI.
3. **Audit ribbon** — historical replay numbers (officer-hours saved,
   Gini before/after, etc.).

**Truth disclaimer that we tell users:** ESI is decision-support, not a
certainty. The displayed band is a 90% prediction interval from
quantile regression heads; for high-variance causes (water_logging,
tree_fall) it is intentionally wide.

---

## 9. Open issues, known limits, and what we have NOT done

### 9.1 Honest gaps

- **Kannada text not translated.** 13% of `description` rows are
  invisible to the `weather_flag` / `event_kw_flag` features.
- **ESI saturation.** Current weights cause many inputs to clip at
  10/10. The formula needs rebalancing; see §6.3.
- **Event-kind taxonomy mismatch.** UI dropdown over-promises relative
  to dataset support; see §6.3.
- **Predicted-duration vs planner-duration blending** is currently
  `max(...)`. A weighted Bayesian blend would be more defensible.
- **No spatial neighborhood features.** We use zone/corridor but no
  H3-cell-level density or kNN neighborhood lags.
- **No translation of `description` for text features.** No
  multilingual sentence embeddings yet (this is the next obvious win).
- **Confidence card metric is heuristic**, not a rigorous score (it is
  weighted by interval width × cascade significance).

### 9.2 What we explicitly did not build (and why)

- **No GNN, no transformer, no fine-tuned LLM.** 8k rows is far too
  small; these would either overfit, hallucinate, or both. We use
  GradientBoosting + quantile regression because it is honest at this
  data size.
- **No external API calls for prediction** (only optional Nominatim
  geocode for the location search input).
- **No fake real-time stream.** All artifacts are precomputed; the live
  layer is the simulator and the API serving them.

### 9.3 Strategic option on the table (not implemented)

A **self-sufficient learned ESI** would replace the hand-coded weights
entirely:

1. Define a **severity_observed** target on historical rows as a
   data-derived combination of duration, response time, closure, and
   cascade count (weights from PCA on those four signals).
2. Train one GBM to predict severity_observed (plus quantile heads).
3. Add a kNN evidence index: at inference, count how many historical
   rows match (cause, zone, hour-band, closure). Use that count to
   gate the output:
   - **n ≥ 100** → show ESI with narrow band, label "data-driven".
   - **20 ≤ n < 100** → show ESI with wider band + "limited evidence".
   - **n < 20** → refuse to show a number; suggest a fallback prior.
4. Trim the UI dropdown accordingly so the system never claims to know
   something it doesn't.

This was discussed but not built. Pending team decision.

---

## 10. How to run everything (current state)

```powershell
# 1. Backend (no venv changes; uses corp-allowed system Python)
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Frontend (corp-safe mirror workflow)
.\setup-frontend.ps1 -Mode dev
# UI at http://localhost:5173, proxied /api → http://127.0.0.1:8000

# 3. Rebuild artifacts (if dataset or pipeline code changed)
cd backend
python -m pipeline.run_all
```

Smoke tests:

```powershell
# Health
Invoke-RestMethod 'http://127.0.0.1:8000/api/health'

# Validation report
Invoke-RestMethod 'http://127.0.0.1:8000/api/validation' | ConvertTo-Json -Depth 6

# Side-by-side ESI test (Wilson Garden vs Chinnaswamy)
cd backend
python -m scripts.test_esi_cases
```

---

## 11. Decision log (what we agreed and why)

- **Use the system Python.** Corp policy blocks creating new venvs; we
  install nothing globally and run pipeline + uvicorn directly.
- **Run frontend from `%LOCALAPPDATA%\atlas-frontend`.** AppLocker
  blocks esbuild on UNC. Mirror script handles this.
- **No external LLM, no Mapbox token.** Keeps everything reproducible
  and demoable offline.
- **Vite proxies to 127.0.0.1, not localhost.** Avoids IPv4/IPv6
  mismatch on Windows.
- **Quantile regression, not just conformal width.** Tighter intervals
  for the same coverage.
- **ESI shows full driver breakdown.** Score must be auditable; no
  black box on the front page.

---

## 12. Pending decisions (need team input)

1. **Severity = pure model?** Replace the hand-coded ESI formula with a
   purely learned severity score (§9.3). Yes/no/hybrid.
2. **Trim the UI dropdown** to match dataset support? Or keep all
   options but show evidence counts and confidence labels?
3. **Multilingual embeddings on description?** Adds a small model
   (~80MB, CPU) and unblocks 13% of the dataset.
4. **Do we drop the "officer-hours saved" framing** if the underlying
   counterfactual is sample-extrapolated? Or keep it with a clear
   methodology note?
5. **Confidence card formula** — keep heuristic or replace with the
   model-derived band width only?

---

## 13. Latest verified numbers (snapshot)

| Thing | Value |
|---|---|
| Raw CSV rows | 8,173 |
| Cleaned rows | 8,041 |
| Cleaned columns | 50 (was 35 before this iteration's feature expansion) |
| Police-station nodes (cascade) | 54 |
| Cascade edges (significance-tested) | 466 |
| Corridors profiled | 21 |
| ESI model features | 29 (9 categorical + 20 numeric) |
| ESI MAE on out-of-time holdout | 35.39 min |
| ESI median AE | 19.64 min |
| ESI 90% coverage (quantile) | 0.884 |
| Officer-hours saved (audit) | 78.4 |
| Gini baseline → ATLAS | 0.031 → 0.033 |
| Frontend bundle | 1,305 modules, ~1.9 MB raw / ~528 kB gzipped |
| Full pipeline runtime | ~90 s |

---

*Last updated: 2026-06-18*
