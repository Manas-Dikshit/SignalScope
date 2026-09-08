# RUN.md — Run SignalScope AI (everything)

Verified against the current repo: **API tests (27) ✅, DSP tests (20) ✅,
frontend tests (20) ✅, frontend build ✅, full Docker stack (postgres + redis +
api + worker + web) all healthy ✅.**

Pick ONE of the three modes below. Mode 1 (Docker, all-in-one) is the
recommended default. Modes 2–3 run each piece in its own terminal so you can
see/log each service independently.

Prereqs everywhere: **Docker Desktop running** (Mode 1 only), **Python 3.11+**,
**Node 20+**.

---

## Mode 1 — Docker Compose (recommended, everything in one command)

Everything (DB + cache + API + worker + web) runs in containers. Usually takes
1 terminal.

```powershell
# 0. One-time env prep
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local

# 1. Build + start (dev overlay = API/worker hot-reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Or production-mode (no hot-reload, detached):

```powershell
docker compose up --build -d
docker compose ps            # all 5 should be (healthy)
```

Useful:
```powershell
docker compose down          # stop (data persists in volumes)
docker compose down -v       # stop AND wipe DB/upload data
docker compose logs -f api   # watch one service's logs
```

URLs:
- Web:    http://localhost:3000
- API:    http://localhost:8000  (Swagger docs at http://localhost:8000/docs)
- DB:      localhost:5432  (user/pass/db = `signalscope`)
- Redis:   localhost:6379

Migrations (`alembic upgrade head`) run automatically when the API container
starts — you don't run alembic yourself in this mode.

---

## Mode 2 — Full native (each piece in its own terminal + Docker DB/cache)

The database and cache run in Docker; the API, worker, and web run natively in
separate terminals (easiest way to watch each one independently).

### Terminal A — database (Postgres + Redis in Docker)

```powershell
docker compose up -d postgres redis
docker compose ps    # both should be (healthy)
```

The `.env` already points at `postgres`/`redis` hostnames, which only resolve
inside the Docker network. For native clients, either change `.env` to
`localhost` or add the two lines below. Simplest: edit `.env` once:
```
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

### Terminal C — Celery worker (required for DSP/parameter-estimation jobs)

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

URLs: web http://localhost:3000, API http://localhost:8000/docs.

---

## Mode 3 — Run the test suites

Run the three test suites (any order). Each in its own terminal if you want
them parallel.

### Terminal A — backend API tests (27)

```powershell
cd services/api
python -m pytest tests/ -q
```

### Terminal B — DSP core tests (20)

```powershell
cd services/dsp-worker
python -m pytest tests/ -q
```

### Terminal C — frontend tests + build (20 tests, type-check)

```powershell
cd apps/web
npm install
npm test      # vitest run
npm run build # next build (also type-checks)
```

---

## End-to-end smoke test

1. Open http://localhost:3000 → Register a user at the login screen.
2. http://localhost:8000/docs → log in, or reuse the web session.
3. Upload a `.wav` / `.iq` / `.sigmf-meta`+`.sigmf-data` recording.
4. In the UI, open the recording → **Analyze** → a Celery job should run and
   parameter estimates (bandwidth, SNR, modulation, symbol rate, …) appear.
5. Check the worker terminal for task logs and the API `/dashboard` stats.

## Port clash note

If you already run a native Postgres on 5432, it shadows Docker's port for
host-local tools. Docker's own containers still reach it on the private
network. To psql the Docker DB: `docker compose exec postgres psql -U signalscope -d signalscope`.

## Troubleshooting

- **Jobs never complete** → worker container/process down, or `signalscope_dsp`
  not installed editable. Reinstall with `pip install -e ..\dsp-worker`.
- **API won't start / table errors** → schema missing: run `alembic upgrade head`.
- **Web can't reach API** → `NEXT_PUBLIC_API_URL` in `apps/web/.env.local` must
  match the API, and backend `CORS_ORIGINS` must include the web origin.
