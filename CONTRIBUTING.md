# 🤝 Contributing to SignalScope AI

Thanks for helping build explainable RF analysis. Every contribution must respect the core rule:

> **Never fake success.** Every estimate ships with `source`, `confidence`, and evidence you can read. If the signal is beyond the pipeline's capability, fail loudly — never present a guess as truth.

---

## 🧠 Project Layout

| Path | Stack | What lives here |
|------|-------|-----------------|
| `services/dsp-worker/` | Python · NumPy · SciPy | `signalscope_dsp` — the DSP library (loaders, spectral, bursts, modulation, symbol-rate, demod, de-interleave, FEC, correlation) |
| `services/api/` | FastAPI · SQLAlchemy 2.0 async · Celery | REST routers, Pydantic schemas, the Celery estimation task |
| `apps/web/` | Next.js 14 · React 18 · TypeScript · Tailwind | Frontend — dashboard, workspace, uploads, evidence/ProofPanel UI |
| `docs/` | Markdown | `REQUIREMENTS_TRACEABILITY.md`, `LOCAL_SETUP.md`, `DESIGN_NOTES.md` |

Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) (and for the deep tech view, [`detailedarch.md`](./detailedarch.md)) before touching cross-service flows.

---

## 🚀 Getting Started

```bash
git clone <repo-url> signalscope
cd signalscope

# Full stack (Docker)
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The dev overlay bind-mounts `services/api` **and** `services/dsp-worker` into the api/worker containers and hot-reloads both (`uvicorn --reload-dir /app --reload-dir /dsp-worker`). Frontend hot-reload: `cd apps/web && npm run dev` on the host.

Native setup walkthrough: [`docs/LOCAL_SETUP.md`](docs/LOCAL_SETUP.md).

---

## 🧪 Running Tests (before you push)

| Suite | Command |
|-------|---------|
| DSP core | `cd services/dsp-worker && python -m pytest tests/ -q` |
| API | `cd services/api && python -m pytest tests/ -q` |
| Frontend | `cd apps/web && npm test` |
| TypeScript | `cd apps/web && npx tsc --noEmit` |

There is one **pre-existing** `tsc` error in `apps/web/src/components/__tests__/ProvenanceBadge.test.tsx` (`toBeInTheDocument` matcher type is not augmented). Don't "fix" it in a PR aimed at something else; leave it untouched or fix it in a dedicated PR.

---

## 🧭 Workflow

1. **Branch** from `main`: `git checkout -b feat/short-description` (prefixes: `feat/`, `fix/`, `docs/`, `test/`, `refactor/`, `chore/`).
2. **Make focused commits.** Keep each commit to one logical change. Match the existing commit style (concise, conventional-ish, lowercase).
3. **Reference phase work where relevant** (e.g. "Phase 6 …"). Update the traceability table in `docs/REQUIREMENTS_TRACEABILITY.md` if you close or change a requirement.
4. **Run the suites** above for everything you touched.
5. **Open a PR** to `main` with a short description of what changed and why.

---

## 📐 Coding Conventions

### DSP (`services/dsp-worker`)
- Pure NumPy/SciPy; no new runtime dependencies without discussion.
- **Every estimate is an object** with `{value, unit, source, confidence, evidence, alternatives, warnings}`. Never return a bare number from a stage.
- Proof data comes from DSP internals (`mth_power_spectrum`, `symbol_clock_spectrum`, `run_length_histogram`) — never duplicate this logic in the API layer.
- Beyond capability → raise/fail loudly. No fabricated values.

### API (`services/api`)
- Pydantic v2 schemas for every request/response; enrich response data with `evidence`/`warnings`.
- Add a test alongside new endpoints or task changes (see `services/api/tests/test_evidence.py`).
- Async engine URLs must be sanitized (`+asyncpg`/`+aiosqlite`) before building sync engines in Celery tasks.

### Frontend (`apps/web`)
- TypeScript strict. New confidence-bearing cards take `evidence` / `warnings` / `proof` props and render a `<ProofPanel>`.
- Reuse `lib/utils.ts` helpers (`formatFrequency`, `summarizeEstimate`, `downloadJSON`) — add vitest coverage when you change formatting logic.
- Keep `tsc --noEmit` clean (except the documented pre-existing test file).

---

## ✅ PR Checklist

- [ ] Tests pass in every affected suite
- [ ] `tsc --noEmit` clean (excluding the documented test-file error)
- [ ] No new dependency added for something a few lines of stdlib can do
- [ ] Estimates carry `source` + `confidence` + `evidence`
- [ ] Traceability doc updated if a requirement changed
- [ ] No secrets, keys, or recordings in the diff

---

## 📄 License

By contributing, you agree your work is licensed under the [MIT License](./LICENSE).

All analysis must remain limited to **authorized** spectrum. Keep misuse liability in mind — the platform is for legal, permissioned RF work only.