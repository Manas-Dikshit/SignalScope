# 🤝 Contributing to SignalScope AI

Thanks for helping build explainable RF analysis. Every contribution must respect the core rule:

> **Never fake success.** Every estimate ships with `source`, `confidence`, and evidence you can read. If the signal is beyond the pipeline's capability, fail loudly — never present a guess as truth.

---

## 🧠 Project Layout

| Path | Stack | What lives here |
|------|-------|-----------------|
| `services/dsp-worker/` | Python · NumPy · SciPy | `signalscope_dsp` — the DSP library (loaders, spectral, bursts, modulation, symbol-rate, interferometry, demod, de-interleave, FEC, correlation, synth) |
| `services/api/` | FastAPI · SQLAlchemy 2.0 async · Celery | REST routers, Pydantic schemas, Celery estimation/insight tasks, evidence-image rendering |
| `services/ai/` | FastAPI · Gemma 4 | Optional analyst sidecar: evidence bundle, allowlisted tool loop, validation, fake/transformers backends |
| `apps/web/` | Next.js 14 · React 18 · TypeScript · Tailwind | Frontend — dashboard, recording library, workspace, demo samples, evidence/ProofPanel, InsightPanel |
| `streamlit_prototype/` | Streamlit · Plotly | Standalone lean DSP/UI prototype |
| `docs/` | Markdown | Setup, architecture, design, traceability, Gemma plan |

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
| AI sidecar | `cd services/ai && python -m pytest tests/ -q` |
| Frontend | `cd apps/web && npm test` |
| TypeScript | `cd apps/web && npx tsc --noEmit` |

Current counts: **74 DSP · 63 API · 22 AI · 29 frontend**. Add or update a test
with every endpoint, DSP stage, or formatting change. The AI suite must keep
passing with `AI_ENABLED=false` for the core product.

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
- Multi-antenna analysis uses interleaved frames `I0 Q0 I1 Q1 …`; interferometric results are estimates (`sky`, `near_field_observatory`, `inconclusive`), never certainties.
- Beyond capability → raise/fail loudly. No fabricated values.

### API (`services/api`)
- Pydantic v2 schemas for every request/response; enrich response data with `evidence`/`warnings`.
- Add a test alongside new endpoints or task changes (see `services/api/tests/test_evidence.py`).
- Async engine URLs must be sanitized (`+asyncpg`/`+aiosqlite`) before building sync engines in Celery tasks.
- AI insights must never overwrite or hide DSP results; store failures in `analysis_insights.error_message`.

### AI sidecar (`services/ai`)
- AI output is always `Source.AI_HYPOTHESIS`; never present it as measured or metadata.
- Numeric values come from backend placeholder substitution, not the model.
- Tool calls are limited to the fixed allowlist and the private token-gated route.
- Raw I/Q is never sent to the model; only bounded, audited PNG data URIs.
- New tools or schema fields need validation tests plus a low-confidence/tool-loop test.

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
- [ ] AI output is labelled `ai_hypothesis` and never replaces DSP results
- [ ] Traceability doc updated if a requirement changed
- [ ] No secrets, keys, or recordings in the diff

---

## 📄 License

By contributing, you agree your work is licensed under the [MIT License](./LICENSE).

All analysis must remain limited to **authorized** spectrum. Keep misuse liability in mind — the platform is for legal, permissioned RF work only.