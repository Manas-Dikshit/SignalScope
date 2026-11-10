# Local Setup Guide — SignalScope AI

This walkthrough stands up the full stack (API + worker + web) on a single
machine for development. The optional Gemma 4 analyst sidecar is covered at the
end.

## Prerequisites

- Python 3.11–3.13 (pinned NumPy/SciPy have no Python 3.14 wheels)
- Node 20+
- Docker + Docker Compose (recommended path), or a local PostgreSQL + Redis

---

## Option A — Docker Compose (recommended)

```bash
cp .env.example .env                       # set SECRET_KEY to a random hex string
cp apps/web/.env.example apps/web/.env.local

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

> `docker-compose.dev.yml` overlays the base `docker-compose.yml` (which
> declares Postgres, Redis, and the shared `uploads_data` volume). It is **not**
> a standalone file — always merge the two with the command above.

The dev overlay gives backend hot-reload (the API/worker mount `./services/api`
and `./services/dsp-worker` into the containers and override the entrypoint so
the compose command runs migrations + `uvicorn --reload`). The `web` service uses
the standalone Next server from the image (the web image ships no dev toolchain,
so there is no `next dev` inside Docker; run `npm run dev` on the host for
frontend hot-reload).

What starts:

| Service | Container | URL |
|---|---|---|
| API | `api` | http://localhost:8000 (`/docs`) |
| Worker | `worker` | Celery, no HTTP |
| Database | `postgres` | `:5432` |
| Cache | `redis` | `:6379` |
| Web | `web` | http://localhost:3000 |

On API startup the container runs `alembic upgrade head`, so the schema is
created automatically — **you do not need to run Alembic yourself**. Uploaded
files are stored in the `uploads_data` volume (`/data` inside the container,
i.e. `DATA_DIR`).

> **Port clash warning:** if your host already runs a native PostgreSQL on port
> 5432, it shadows Docker Postgres for host-local connections. Docker clients
> (API/worker containers) are unaffected — they reach Postgres on the private
> network. Don't point local tools (psql, Alembic) at `localhost:5432` for the
> Docker database; run them via `docker compose exec postgres psql ...` instead.

Stop with `Ctrl-C`; restart with the same command. Rebuild images after
dependency changes:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml build
```

### Demo signals

From http://localhost:3000, use the **Demo signals** section to load a QPSK,
2-FSK, 16-QAM, BPSK-burst, or 8-PSK recording instantly. Sample files also live
in `samples/` and can be regenerated:

```bash
python scripts/generate_samples.py
```

### Tests

```bash
# DSP core — 69 tests
cd services/dsp-worker && python -m pytest tests/ -q

# API — 51 tests
cd services/api && python -m pytest tests/ -q

# AI sidecar — 19 tests (includes evidence-image caps)
cd services/ai && python -m pytest tests/ -q

# Frontend — 26 tests
cd apps/web && npm install && npm test
```

---

## Option B — Local processes (no Docker)

You need a reachable PostgreSQL and Redis first.

```bash
# 1. Backend environment
cd services/api
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e ../dsp-worker

# 2. Create services/api/.env with your local URLs (Pydantic reads it):
#    DATABASE_URL=postgresql+asyncpg://signalscope:signalscope@localhost:5432/signalscope
#    DATABASE_URL_SYNC=postgresql://signalscope:signalscope@localhost:5432/signalscope
#    REDIS_URL=redis://localhost:6379/0
#    CELERY_BROKER_URL=redis://localhost:6379/1
#    CELERY_RESULT_BACKEND=redis://localhost:6379/2
#    DATA_DIR=./data
#    SECRET_KEY=<random hex>
#    CORS_ORIGINS=http://localhost:3000

# 3. Create the schema + run the API
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 4. In another terminal: the worker (same venv, needed for DSP/insight jobs)
cd services/api
celery -A app.tasks worker --loglevel=info --concurrency=2

# 5. Frontend in a third terminal
cd apps/web
npm install
cp .env.example .env.local      # Windows: copy .env.example .env.local
npm run dev
```

---

## Configuration reference

Backend settings live in `services/api/app/config.py` and are overridable with
environment variables (or `.env`). The defaults below match `.env.example` /
Docker Compose; running natively, point the URLs at `localhost`.

### Core

| Variable | Default (Compose) | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async SQLAlchemy URL |
| `DATABASE_URL_SYNC` | `postgresql://...` | Sync URL (worker DB access) |
| `REDIS_URL` | `redis://redis:6379/0` | App Redis URL (db 0; currently unused) |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery task broker |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2` | Celery result backend |
| `DATA_DIR` | `/data` | Upload + working files |
| `MAX_UPLOAD_BYTES` | `209715200` | Upload size cap (200 MB) |
| `SECRET_KEY` | `change-me...` | JWT signing — **must be overridden** |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed frontend origins (comma-separated or JSON array) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime |

### Optional Gemma 4 sidecar

| Variable | Default | Purpose |
|---|---|---|
| `AI_ENABLED` | `false` | Enable the insights endpoint and Celery task |
| `AI_SERVICE_URL` | `http://ai:8100` | AI sidecar URL |
| `AI_MODEL` | `google/gemma-4-E4B-it` | Model identifier |
| `AI_BACKEND` | `fake` | `fake` or `transformers` (AI service) |
| `AI_TIMEOUT_SECONDS` | `120` | Whole-brief timeout |
| `AI_PROMPT_VERSION` | `2026-11-01` | Stored with each insight |
| `AI_MAX_TOOL_STEPS` | `6` | Agent loop cap |
| `AI_TOOL_TIMEOUT_SECONDS` | `30` | Per-tool timeout |
| `INTERNAL_API_TOKEN` | empty | Shared secret for `/internal/dsp-tools/*`; empty disables the route |
| `API_INTERNAL_URL` | `http://api:8000` | API URL used by the AI service |
| `AI_EVIDENCE_IMAGES_ENABLED` | `true` | Render PSD/waterfall/constellation/M-th-power PNGs |
| `AI_MAX_IMAGE_BYTES` | `300000` | Per-image cap |
| `AI_MAX_TOTAL_IMAGE_BYTES` | `1000000` | Whole-bundle cap |

AI runtime variables (set on the `ai` service or in `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `AI_DEVICE` | `auto` | Transformers device selection |
| `AI_ENABLE_THINKING` | `false` | Gemma thinking mode for hard cases |
| `AI_MAX_NEW_TOKENS` | `1024` | Generation cap |
| `AI_INSTALL_TRANSFORMERS` | `0` | Build arg that installs the optional runtime |

Frontend: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

---

## Optional local Gemma 4 AI service

The AI service is **not** part of the default stack. The core product works
unchanged with `AI_ENABLED=false`.

### Fake backend (fast, deterministic, no download)

```dotenv
AI_ENABLED=true
AI_BACKEND=fake
INTERNAL_API_TOKEN=change-me
```

```bash
docker compose --profile ai up -d --build
```

### Transformers backend

```dotenv
AI_ENABLED=true
AI_BACKEND=transformers
AI_MODEL=google/gemma-4-E4B-it
AI_INSTALL_TRANSFORMERS=1
INTERNAL_API_TOKEN=change-me
```

```bash
docker compose --profile ai up -d --build
```

The service starts at http://localhost:8100 (`/health` reports status, backend,
and model). In the web UI, completed projects show the **AI Analyst Brief**
panel, which generates cited, provenance-checked briefs and displays the
`ai_hypothesis` badge, citations, and tool trace.

Set the same `INTERNAL_API_TOKEN` on `api`, `worker`, and `ai`. The AI service
only POSTs to the API's private DSP tool route; the model never chooses a URL or
executes code.

See [`services/ai/README.md`](../services/ai/README.md) for the full contract.

---

## Verification

1. Open `http://localhost:8000/docs` — Swagger UI loads.
2. Register a user, then upload a `.wav`, `.iq`, or `.sigmf-meta`/`.sigmf-data`
   pair — or load a demo signal.
3. Start parameter estimation — confirm a job runs and estimate records appear
   with provenance (source + confidence + evidence).
4. Open `http://localhost:3000/recordings` — the recording lists with a real
   waveform thumbnail.
5. Open the project workspace — confirm waveform/I/Q/PSD/waterfall, proof
   panels, deep-analysis tabs, and FEC selection.
6. Optional: with the AI profile running, click **Generate AI Brief** and verify
   the brief is labelled `ai_hypothesis`.

---

## Troubleshooting

- **Migrations don't run** — confirm the `api` image ran `alembic upgrade head`;
  check `services/api/alembic/versions/` contains revisions.
- **Jobs never complete** — confirm the `worker` is up and reachable on Redis;
  check worker logs for `signalscope_dsp` import errors (it must be installed
  editable).
- **Frontend can't reach the API** — `NEXT_PUBLIC_API_URL` must point at the
  API, and the backend `CORS_ORIGINS` must include the web origin.
- **AI endpoint returns 503** — set `AI_ENABLED=true` and start the `ai` profile.
- **AI tool calls fail** — make `INTERNAL_API_TOKEN` match on `api` and `ai`; an
  empty token disables the private route.
- **First AI request is slow** — the Transformers backend downloads/loads the
  model on first use. Use `AI_BACKEND=fake` for demos.
- **Python 3.14** — pinned NumPy/SciPy have no 3.14 wheels; use 3.11–3.13.
