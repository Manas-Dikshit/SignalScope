# Local Setup Guide — SignalScope AI

This walks through standing up the full stack (API + worker + web) on a single
machine for development.

## Prerequisites

- Python 3.11+
- Node 20+
- Docker + Docker Compose (recommended path), or a local PostgreSQL + Redis

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
into the container and `entrypoint` is overridden so the compose `command`
runs migrations + `uvicorn --reload`). The `web` service uses the standalone
Next server from the image (the web image ships no dev toolchain, so there is
no `next dev` inside Docker; run `npm run dev` on the host for frontend
hot-reload).

What starts:

| Service  | Container | URL                 |
|----------|-----------|---------------------|
| API      | `api`     | http://localhost:8000 (`/docs`) |
| Worker   | `worker`  | Celery, no HTTP     |
| Database | `postgres`| :5432 (from docker-compose.yml) |
| Cache    | `redis`   | :6379 (from docker-compose.yml) |
| Web      | `web`     | http://localhost:3000 |

On API startup the container runs `alembic upgrade head`, so the schema is
created automatically — **you don't need to run alembic yourself**. Uploaded
files are stored in the `uploads_data` volume (`/data` inside the container,
i.e. `DATA_DIR`).

> **Port clash warning:** if your host already runs a native PostgreSQL on
> port 5432, it shadows Docker's Postgres for host-local connections. Docker
> clients (API/worker containers) are unaffected — they reach Postgres on the
> private network. Just don't point local tools (psql, alembic) at
> `localhost:5432` for the Docker database; run them via `docker compose exec
> postgres psql ...` instead.

Stop with `Ctrl-C`; restart with the same command. Rebuild images after
dependency changes with `docker compose -f docker-compose.yml -f docker-compose.dev.yml build`.

### Frontend tests

```bash
cd apps/web
npm install
npm test        # Vitest + React Testing Library (component tests)
```

### Backend (DSP + API) tests

```bash
cd services/dsp-worker && python -m pytest tests/ -q   # DSP core
cd services/api       && python -m pytest tests/ -q    # API
```

## Option B — Local processes (no Docker)

You'll need a reachable PostgreSQL and Redis first.

```bash
# 1. Backend environment
cd services/api
python -m venv .venv && . .venv/bin/activate    # or .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e ../dsp-worker

# 2. Env (edit to point at your Postgres/Redis)
set DATABASE_URL=postgresql+asyncpg://signalscope:signalscope@localhost:5432/signalscope
set DATABASE_URL_SYNC=postgresql://signalscope:signalscope@localhost:5432/signalscope
set REDIS_URL=redis://localhost:6379/0
set CELERY_BROKER_URL=redis://localhost:6379/1
set CELERY_RESULT_BACKEND=redis://localhost:6379/2
set DATA_DIR=./data
set SECRET_KEY=some-long-random-hex
set CORS_ORIGINS=http://localhost:3000

# 3. Create the schema + run the API
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 4. In another terminal: the worker (needed for DSP jobs)
cd services/api
. .venv/bin/activate
celery -A app.tasks worker --loglevel=info --concurrency=2

# 5. Frontend
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

## Configuration reference

All backend settings live in `services/api/app/config.py` and are overridable
with environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async SQLAlchemy URL |
| `DATABASE_URL_SYNC` | `postgresql://...` | Sync URL (worker DB access) |
| `REDIS_URL` | `redis://redis:6379/0` | App Redis (listings, locks) |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery task broker |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2` | Celery result backend |
| `DATA_DIR` | `/data` | Upload + working files |
| `MAX_UPLOAD_BYTES` | `209715200` | Upload size cap (200 MB) |
| `SECRET_KEY` | `change-me...` | JWT signing **must be overridden** |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed frontend origins |

Frontend: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

## Verification

1. Open `http://localhost:8000/docs` — Swagger UI loads.
2. Register a user, then upload a `.wav` or `.sigmf-meta`/`.sigmf-data` pair.
3. Start parameter estimation — confirm a job runs and estimate records appear
   with provenance (source + confidence).
4. Open `http://localhost:3000/recordings` — the uploaded recording lists, and
   the project page shows the preview waveform / I/Q scatter.

## Troubleshooting

- **Migrations don't run** — confirm the `api` image ran `alembic upgrade
  head`; check `services/api/alembic/versions/` contains a revision.
- **Jobs never complete** — confirm the `worker` container is up and reachable
  on Redis; check worker logs for `signalscope_dsp` import errors (it must be
  installed editable).
- **Frontend can't reach the API** — `NEXT_PUBLIC_API_URL` must point at the
  API, and the backend's `CORS_ORIGINS` must include the web origin.
