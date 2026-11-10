# RUN.md — Run SignalScope AI end to end

SignalScope ships four test suites (**188 tests**): **74 DSP**, **63 API**, **22 AI**,
and **29 frontend**. The default stack is deterministic and offline; the Gemma 4
analyst sidecar is optional.

Pick one of the modes below. **Mode 1 (Docker, all-in-one)** is the recommended
default. Modes 2–3 run each piece in its own terminal so you can watch each
service independently.

**Prerequisites**

- **Docker Desktop running** (Mode 1 only)
- **Python 3.11–3.13** for native backend work — pinned NumPy/SciPy have no
  Python 3.14 wheels
- **Node 20+** for frontend development and tests

---

## Mode 1 — Docker Compose (recommended)

Everything (Postgres + Redis + API + worker + web) runs in containers. Usually
takes one terminal.

```powershell
# 0. One-time env prep
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local

# Generate a real secret and put it in .env as SECRET_KEY
openssl rand -hex 32
# No openssl? Use: python -c "import secrets; print(secrets.token_hex(32))"

# 1. Build + start (dev overlay = API/worker hot-reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Or production-mode (no hot-reload, detached):

```powershell
docker compose up --build -d
docker compose ps            # all services should be healthy
```

Useful commands:

```powershell
docker compose down          # stop (data persists in volumes)
docker compose down -v       # stop AND wipe DB/upload data
docker compose logs -f api   # watch one service
docker compose exec postgres psql -U signalscope -d signalscope
```

URLs:

| Service | URL |
|---|---|
| Web | http://localhost:3000 |
| API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |
| Postgres | `localhost:5432` (`signalscope` / `signalscope`) |
| Redis | `localhost:6379` |

Migrations (`alembic upgrade head`) run automatically when the API container
starts — you do not run Alembic yourself in this mode.

---

## Mode 2 — Full native (each piece in its own terminal)

The database and cache run in Docker; the API, worker, and web run natively in
separate terminals.

### Terminal A — database (Postgres + Redis in Docker)

```powershell
docker compose up -d postgres redis
docker compose ps
```

The `.env` points at `postgres`/`redis` hostnames, which only resolve inside the
Docker network. For native clients, edit `.env` once:

```dotenv
DATABASE_URL=postgresql+asyncpg://signalscope:signalscope@localhost:5432/signalscope
DATABASE_URL_SYNC=postgresql://signalscope:signalscope@localhost:5432/signalscope
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

### Terminal B — backend API

```powershell
cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e ..\dsp-worker
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Terminal C — Celery worker

Required for DSP/parameter-estimation jobs and AI insight jobs.

```powershell
cd services/api
.\.venv\Scripts\Activate.ps1
celery -A app.tasks worker --loglevel=info --concurrency=2
```

### Terminal D — frontend

```powershell
cd apps/web
npm install
npm run dev
```

URLs: web http://localhost:3000, API docs http://localhost:8000/docs.

---

## Mode 3 — Test suites

Run the suites in any order. Each in its own terminal if you want them parallel.

| Suite | Tests | Command |
|---|---:|---|
| API | 51 | `cd services/api && python -m pytest tests/ -q` |
| DSP core | 69 | `cd services/dsp-worker && python -m pytest tests/ -q` |
| AI sidecar | 19 | `cd services/ai && python -m pytest tests/ -q` |
| Frontend | 26 | `cd apps/web && npm install && npm test` |

Frontend type-check/build:

```powershell
cd apps/web
npm run build
```

The AI suite includes validation, cited brief generation, low-confidence tool
follow-ups, max-step/timeout handling, and evidence-image caps. The DSP suite
covers interferometric origin, dual-antenna raw-IQ frames, FEC round trips, and
bounded-window loading.

> If you have local scratch tests (for example an untracked debug test that
> intentionally fails), remove or exclude them before running the full suite.

---

## Mode 4 — Optional Gemma 4 AI analyst

The AI sidecar is disabled by default. The core stack runs unchanged with
`AI_ENABLED=false`.

### Fake backend (no model download)

```dotenv
AI_ENABLED=true
AI_BACKEND=fake
INTERNAL_API_TOKEN=change-me
```

```powershell
docker compose --profile ai up --build
```

### Local Transformers backend

```dotenv
AI_ENABLED=true
AI_BACKEND=transformers
AI_MODEL=google/gemma-4-E2B-it
AI_INSTALL_TRANSFORMERS=1
INTERNAL_API_TOKEN=change-me
```

```powershell
docker compose --profile ai up --build
```

The `ai` service listens on http://localhost:8100. `GET /health` reports the
active backend and model. Model weights are downloaded into the `ai_models`
volume on first start.

Set the **same** `INTERNAL_API_TOKEN` for `api`, `worker`, and `ai`. An empty
token disables the private `/internal/dsp-tools/{tool}` route.

Generate a brief from a completed project with **Generate AI Brief** in the
workspace, or:

```powershell
curl -X POST http://localhost:8000/api/projects/<project_id>/insights ^
  -H "Authorization: Bearer <token>"
```

See [`services/ai/README.md`](services/ai/README.md) and
[`docs/GEMMA4_IMPLEMENTATION_PLAN.md`](docs/GEMMA4_IMPLEMENTATION_PLAN.md) for
model options, tool schemas, and GPU notes.

---

## End-to-end smoke test

1. Open http://localhost:3000 and register a user.
2. From the dashboard, click a **demo signal** (QPSK, 2-FSK, 16-QAM, BPSK bursts,
   or 8-PSK) — or upload a `.wav`, `.iq`, or SigMF pair.
3. Open the recording → **Analyze**. A Celery job runs and estimates
   (bandwidth, SNR, modulation, symbol rate, interferometric origin, …) appear.
4. Expand **View proof** on a confidence-bearing estimate.
5. Switch to the deep-analysis tabs for demodulated bits, de-interleaving
   candidates, FEC selection, and correlation.
6. Optional: click **Generate AI Brief** and inspect the `ai_hypothesis` badge,
   citations, and tool trace.
7. Check worker logs and `GET /api/dashboard/stats`.

There is also a scripted smoke test:

```powershell
python scripts/smoke_test.py
```

---

## Port clash notes

- If a native PostgreSQL already listens on 5432, it shadows Docker Postgres for
  host-local tools. Containers still reach it on the private network. Use
  `docker compose exec postgres psql -U signalscope -d signalscope` for the
  Docker database.
- If port 3000 or 8000 is occupied, stop the conflicting process or change the
  compose port mapping.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Jobs never complete | Worker container/process down, or `signalscope_dsp` not installed editable. Reinstall with `pip install -e ..\dsp-worker`. |
| API won't start / table errors | Schema missing: run `alembic upgrade head`. |
| Web can't reach API | `NEXT_PUBLIC_API_URL` in `apps/web/.env.local` must match the API, and backend `CORS_ORIGINS` must include the web origin. |
| AI route returns 503 | Set `AI_ENABLED=true` and start the `ai` profile. |
| AI tool calls fail | `INTERNAL_API_TOKEN` must match on `api` and `ai`; an empty token disables the route. |
| Insight generation fails | Check the `ai` service logs and the `analysis_insights.error_message` row. DSP results are preserved. |
| Slow first AI request | Model download/load happens on first use with the Transformers backend. Use `AI_BACKEND=fake` for fast offline demos. |
