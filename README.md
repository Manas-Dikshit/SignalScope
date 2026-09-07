# SignalScope AI — Lean MVP

An offline, explainable RF signal-analysis workbench for **authorized** `.iq`,
`.wav`, and SigMF recordings. The DSP core is the lockstep-tested
`signalscope_dsp` library; Phase 2 wraps it in a persistent FastAPI backend
(PostgreSQL + Celery) served by a Next.js frontend.

**Scope reminder:** offline file analysis only. No live RF capture, no
geolocation, no decryption of protected communications.

## Architecture

```
apps/web/              # Next.js 14 frontend (App Router, shadcn/ui, react-plotly)
services/api/          # FastAPI backend (auth, upload, projects, recordings, jobs, dashboard)
services/dsp-worker/   # signalscope_dsp — the DSP core (lockstep-tested, reusable standalone)
  signalscope_dsp/     #   the provenance-tracked DSP library
docker/                # Dockerfiles for api / worker / web
docs/                  # setup + spec docs
```

Layout notes:

- The DSP core at `services/dsp-worker/signalscope_dsp/` is the same module
  the original MVP exercised — it is installed editable into the API/worker
  images with `pip install -e`, so both FastAPI and the Celery worker call the
  exact same functions.
- Alembic migrations live at `services/api/alembic/` and are applied on
  container start (`alembic upgrade head`).
- Auth is JWT in an HTTP-only cookie (with Bearer fallback); every parameter
  the DSP reports carries a `source`, `confidence`, and evidence — nothing is
  shown as exact when it isn't.

## What's implemented

- **Persistent backend** — FastAPI + SQLAlchemy (async) + PostgreSQL.
- **Auth** — register/login, JWT cookies, password hashing.
- **File import** — WAV, raw IQ, and SigMF (`.sigmf-meta` + `.sigmf-data`)
  upload, stored under `DATA_DIR`.
- **Projects & recordings** — grouping, metadata, per-recording DSP preview
  (waveform + I/Q scatter).
- **DSP jobs** — Celery worker runs the full `signalscope_dsp` pipeline
  (bursts, features, modulation classification, symbol-rate estimation,
  demodulation, de-interleaving, FEC, bit correlation) with provenance
  recorded per estimate.
- **Dashboard** — `/api/dashboard/stats` aggregates recordings, projects,
  recent activity, and running jobs.
- **Synthetic signal generator** — built into the DSP core so the whole
  pipeline is testable with zero external datasets.

The original Streamlit MVP (`app.py`) was superseded by the web app and is
gone from the tree.

## Running it

### Quick start (Docker Compose, recommended)

```bash
cp .env.example .env         # then set SECRET_KEY
cp apps/web/.env.example apps/web/.env.local
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

> `docker-compose.dev.yml` is an overlay on the base `docker-compose.yml`
> (which declares Postgres, Redis, and the `uploads_data` volume) — always merge
> the two as shown. The Makefile `dev` target does the same. The dev overlay
> enables API/worker hot-reload; the web container runs the standalone Next
> server (use `npm run dev` on the host for frontend hot-reload).

- API: `http://localhost:8000` (docs at `/docs`)
- Web: `http://localhost:3000`
- Migrations run automatically on API container start.

### Local (without Docker)

```bash
# 1. Backend
cd services/api
pip install -e ../dsp-worker . 
alembic upgrade head
uvicorn app.main:app --reload

# 2. Worker (optional, needed for DSP jobs)
celery -A app.tasks worker --loglevel=info

# 3. Frontend
cd apps/web
npm install
npm run dev
```

See `docs/LOCAL_SETUP.md` for a detailed walkthrough.

## Running the tests

```bash
cd services/dsp-worker && python -m pytest tests/ -q     # DSP core (20 tests)
cd services/api       && python -m pytest tests/ -q      # API (27 tests)
cd apps/web           && npm test                        # component tests (Vitest)
```

Tests cover wav/raw-IQ/SigMF loading, convolutional encode/Viterbi decode
round trips, CRC, de-interleaving, bit correlation, end-to-end
generate+demodulate BER for BPSK/QPSK/16-QAM/2-FSK, modulation classification,
symbol-rate estimation, plus auth, upload, projects, recordings, jobs, and the
frontend provenance badge (source x confidence) + file-format inference.

## Known limitations (intentional, for an MVP)

- Demodulators sample symbol centers directly; no closed-loop Costas/PLL
  carrier or Gardner/M&M timing recovery yet. Works well on the synthetic
  generator and clean near-baseband captures.
- FEC is rate-1/2 convolutional/Viterbi only (hard-decision). Reed-Solomon,
  LDPC, and soft-decision LLR decoding are not in this MVP.
- Tests run against SQLite (with eager Celery), not Testcontainers Postgres —
  the Postgres path is exercised by the Docker deployment.

## Verified status (Phase 2 acceptance — all checks pass)

| Check | Status | Notes |
|-------|--------|-------|
| DSP tests (20) | ✅ | All green |
| API tests (27) | ✅ | All green |
| Frontend tests (20) | ✅ | Vitest + React Testing Library |
| Docker build + stack | ✅ | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build` → all 5 healthy |
| Base compose (production) | ✅ | `docker compose up --build` → all 5 healthy |
| Auth: register/login/me | ✅ | JWT via httpOnly cookie; Bearer fallback |
| Auth: 401 bad password / 409 duplicate | ✅ | |
| Upload: WAV, raw IQ, SigMF | ✅ | All return 201 |
| Upload: corrupt file rejected | ✅ | 422 |
| User-supplied metadata shown as `user_supplied` | ✅ | |
| Preview endpoint | ✅ | Waveform + I/Q scatter |
| Project create + estimate-parameters | ✅ | Job runs to `completed`, estimates persisted |
| Job status with `n_sources` | ✅ | |
| `detect-bursts`, `segments` | ✅ | Return 200 |
| Cross-user isolation (recordings + projects) | ✅ | 403 |
| Persistence across restarts | ✅ | Data survives `docker compose down && up` |
| Rate limiting: login 10/min, upload 30/min | ✅ | |
| `GET /api/jobs/{id}` requires auth | ✅ | |
| `GET /api/recordings/{id}/metadata` | ✅ | Was missing; added |
| Celery jobs reach workers (no queue drift) | ✅ | `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` on separate Redis DBs |
| Web `/health` endpoint | ✅ | Dockerfile healthcheck uses `127.0.0.1` (was broken on `[::1]`) |
| Frontend: ProvenanceBadge 6 sources | ✅ | Distinct icon + label per source |
| Frontend: 4 confidence tiers | ✅ | Green / yellow / red / hidden (null) |
| Frontend: file-format inference | ✅ | Extracted to `inferFormatFromFilename` — tested |
| Dev compose api/worker entrypoint | ✅ | Fixed shadowing; `entrypoint: []` in dev-yml |

### Known deviations from spec

- **SQLite vs Testcontainers** — API tests use `sqlite+aiosqlite:///./test.db` (not
  Testcontainers Postgres as spec §10 requests). The Postgres path is exercised
  by the Docker deployment; local tests run faster on SQLite.
- **Frontend: `next dev` not available inside Docker** — the web Dockerfile builds
  a standalone Next server (no dev toolchain). For frontend hot-reload, run
  `npm run dev` on the host instead.
- **No Vitest config for frontend path aliases** — tests resolve `@/` via Vite
  alias; no `tsconfig.json` changes were needed.

## Where this goes next

Postgres persistence is included, but hardened multi-user deployment (proper
key rotation, external object storage, GNU Radio integration, neural
modulation classifier, LDPC/Reed-Solomon, closed-loop carrier/timing recovery)
remains future work. The DSP core keeps clean module boundaries specifically
so those layer on without a rewrite.
