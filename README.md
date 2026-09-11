<div align="center">

# 📡 SignalScope AI

**Explainable RF Signal-Analysis Workbench**

An offline, provenance-tracked, AI-assisted RF signal analysis platform for **authorized** `.iq`, `.wav`, and SigMF recordings — from raw spectrum to demodulated bits, with every estimate backed by evidence.

![Status](https://img.shields.io/badge/status-production%20ready-2ea44f?style=for-the-badge&logo=vercel&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-8A2BE2?style=for-the-badge&logo=semver&logoColor=white)

---

**🏆 Never guesses. Never hides uncertainty. Every number has a `source`, a `confidence`, and evidence you can read.**

</div>

---

## ✨ Why SignalScope?

Traditional signal analyzers output a single number and call it truth. SignalScope treats every parameter as a **provenance-tracked estimate**:

| Feature | The SignalScope way |
|---------|-------------------|
| **Explanable** | Every estimate ships with `source`, `confidence`, and human-readable evidence |
| **Offline & private** | 100% local processing — your RF data never leaves your machine |
| **Multi-format** | WAV, raw I/Q, and SigMF (`-meta` + `-data` pairs) |
| **End-to-end** | Modulation → symbol rate → bursts → demodulation → de-interleaving → FEC → bits |
| **Self-verifying** | Synthetic signal generator built in, so the entire pipeline runs without external datasets |
| **Future-proof** | Clean DSP module boundaries — neural classifiers and new coding schemes layer on without a rewrite |

---

## 🧱 Tech Stack

<div align="center">

### Frontend
![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-3-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)
![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-000000?style=for-the-badge&logo=shadcnui&logoColor=white)
![TanStack Query](https://img.shields.io/badge/TanStack%20Query-5-FF4154?style=for-the-badge&logo=reactquery&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly.js-3F4F75?style=for-the-badge&logo=plotly&logoColor=white)
![Zustand](https://img.shields.io/badge/Zustand-4-5A67D8?style=for-the-badge)
![Vitest](https://img.shields.io/badge/Vitest-5-6E9F18?style=for-the-badge&logo=vitest&logoColor=white)

### Backend
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Alembic](https://img.shields.io/badge/Alembic-1.15-D2B48C?style=for-the-badge)
![Celery](https://img.shields.io/badge/Celery-5.5-37814A?style=for-the-badge&logo=celery&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-2-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![JWT](https://img.shields.io/badge/JWT%20Auth-000000?style=for-the-badge&logo=jsonwebtokens&logoColor=white)

### Data & Infra
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)

### DSP Core
![NumPy](https://img.shields.io/badge/NumPy-2.2-013243?style=for-the-badge&logo=numpy&logoColor=white)
![SciPy](https://img.shields.io/badge/SciPy-1.15-8CAAE6?style=for-the-badge&logo=scipy&logoColor=white)
![Pytest](https://img.shields.io/badge/Pytest-8-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)

</div>

---

## 🏗️ Architecture

> **📐 Ready the full system design —** [**`ARCHITECTURE.md`**](./ARCHITECTURE.md) contains the complete Mermaid system-design diagram of every layer (frontend, API, Celery worker, Redis, Postgres), the DSP processing pipeline, and the async job lifecycle sequence. Tech-stack badges included.

---

## 🚀 Getting Started

### Prerequisites

- [Docker](https://docker.com) + Docker Compose
- Node.js 18+ (only for frontend hot-reload)
- Python 3.11+ (only for running tests natively)

### Quick start (recommended)

```bash
# 1. Clone & configure
git clone <repo-url> signalscope
cd signalscope

cp .env.example .env                        # then set a strong SECRET_KEY
cp apps/web/.env.example apps/web/.env.local

# 2. Build & launch the full stack
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

| Service | URL |
|---------|-----|
| 🌐 Web app | http://localhost:3000 |
| 🔌 API | http://localhost:8000 |
| 📚 Swagger docs | http://localhost:8000/docs |
| 🐘 Postgres | `localhost:5432` |
| 🧮 Redis | `localhost:6379` |

> The dev overlay (`docker-compose.dev.yml`) merges with the base file — always pass **both**. It enables API/worker hot-reload. For frontend hot-reload, run `npm run dev` in `apps/web` on the host.

### Manual development

```bash
# Frontend (hot reload)
cd apps/web && npm install && npm run dev

# API + worker natively (requires local Postgres/Redis, or just use Docker)
cd services/api && pip install -r requirements.txt && uvicorn app.main:app --reload
```

See [`docs/LOCAL_SETUP.md`](docs/LOCAL_SETUP.md) for a full walkthrough.

---

## 🧪 Testing

| Suite | Command | Scope |
|-------|---------|-------|
| DSP core | `cd services/dsp-worker && python -m pytest tests/ -q` | 20 tests — loading, mod/demod BER, FEC, modulation classification, symbol rates |
| API | `cd services/api && python -m pytest tests/ -q` | 27 tests — auth, upload, projects, jobs, isolation, rate limiting |
| Frontend | `cd apps/web && npm test` | Vitest + RTL — provenance badge, file-format inference |

Together they verify: WAV/raw-IQ/SigMF loading, convolutional-encode/Viterbi-decode round trips, CRC, de-interleaving, bit correlation, `generate + demodulate` BER for BPSK/QPSK/16-QAM/2-FSK, modulation classification, symbol-rate estimation — plus full API behavior and cross-user data isolation.

---

## 📡 DSP Pipeline & Provenance Model

Every estimate the pipeline produces carries a **provenance record**:

```json
{
  "name": "symbol_rate",
  "value": 250000.0,
  "unit": "symbols/s",
  "source": "spectral_correlator",
  "confidence": 0.93,
  "evidence": [
    "dominant spectral peak at 250.0 kHz (±2.5 kHz) in the cyclostationary profile",
    "agrees within 1.2% of candidate from zero-crossing analysis"
  ],
  "alternatives": [
    { "value": 256000.0, "evidence": ["second harmonic candidate"] }
  ],
  "warnings": []
}
```

**Pipeline stages** — burst detection → spectral features → modulation classification → symbol-rate estimation → demodulation → de-interleaving → FEC decoding → bit correlation.

Nothing is presented as *exact* when it isn't — the UI color-codes confidence (green → yellow → red) and lets you expand the evidence behind each claim.

---

## 🔌 API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` · `/login` · `/me` | POST/GET | JWT auth via httpOnly cookie |
| `/api/uploads` | POST | Upload WAV / raw-IQ / SigMF (validated) |
| `/api/projects` | CRUD | Group recordings into analysis projects |
| `/api/projects/{id}/estimate-parameters` | POST | Dispatch estimation job → Celery |
| `/api/projects/{id}/parameters` | GET | Provenance-tracked estimates |
| `/api/recordings` | CRUD | Recording metadata + preview |
| `/api/jobs/{id}` | GET | Async job status (`queued → running → completed`) |
| `/api/dashboard/stats` | GET | Aggregate metrics |
| `/api/health` | GET | Liveness probe |

Full interactive docs at `/docs` (Swagger UI).

---

## ⚠️ Scope & Limitations

**Intentionally out of scope (MVP):**
- ❌ No live RF capture or SDR streaming
- ❌ No geolocation / direction finding
- ❌ No decryption of protected communications — **authorized recordings only**
- ⚠️ Demodulators sample symbol centers directly — no closed-loop Costas/PLL or Gardner/M&M timing recovery yet
- ⚠️ FEC is rate-1/2 convolutional/Viterbi (hard-decision) only; LDPC/Reed-Solomon/soft-decision are future work
- ⚠️ API tests run against SQLite for speed (Postgres path exercised by Docker deployment)

---

## 🧭 Roadmap

- [ ] Hardened multi-user deployment (key rotation, external object storage)
- [ ] GNU Radio integration
- [ ] Neural-network modulation classifier
- [ ] LDPC / Reed-Solomon / soft-decision LLR decoding
- [ ] Closed-loop carrier & timing recovery (Costas / PLL / Gardner)

---

## 📄 License

All usage must be limited to **authorized** spectrum analysis. The author assumes no responsibility for misuse of the DSP capabilities.

---

<div align="center">

**Made by [Team DevX](https://github.com/your-org/devx) with ❤️** — building explainable tools for the radio spectrum.

</div>