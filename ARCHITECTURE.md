<div align="center">

# 🏗️ SignalScope AI — System Architecture

**A deep dive into how the pieces fit together: services, tech stacks, and the DSP processing flow.**

---

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.5-37814A?style=for-the-badge&logo=celery&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-2.2-013243?style=for-the-badge&logo=numpy&logoColor=white)
![SciPy](https://img.shields.io/badge/SciPy-1.15-8CAAE6?style=for-the-badge&logo=scipy&logoColor=white)

</div>

---

## 🗺️ System Overview

**Six layers, one goal: turn raw RF recordings into *explainable* parameter estimates.** The request path is fully async — the browser fires an analysis job, Celery executes the DSP pipeline in the background, and the frontend polls the job status until results land in Postgres.

---

## 📐 System Design Diagram

```mermaid
flowchart TB
    subgraph CLIENTS["👤 Client Layer"]
        U["🖥️ Operator / Analyst Browser"]
    end

    subgraph FRONTEND["🌐 Presentation Layer — Next.js 14 (Docker :3000)"]
        direction LR
        NEXT["⚛️ Next.js App Router<br/>React 18 · TypeScript 5 · TailwindCSS · shadcn/ui"]
        QUERY["🔗 TanStack Query 5<br/>server-state cache & polling"]
        PLOTLY["📊 Plotly.js<br/>waveform · IQ scatter · waterfall · spectrum"]
        UI["🧩 Provenance UI<br/>confidence tiers + expandable evidence"]
    end

    subgraph API["📡 Application Layer — FastAPI (Docker :8000)"]
        direction TB
        ROUTERS["🗂️ Routers<br/>auth · uploads · projects · recordings<br/>jobs · dashboard"]
        AUTH["🔐 JWT auth (httpOnly cookie)<br/>python-jose + passlib/argon2"]
        RATE["⏱️ Rate limiting<br/>login 10/min · upload 30/min"]
        VALID["🧾 Upload validation<br/>WAV · raw-IQ · SigMF · 200MB cap"]
        SCH["📝 Pydantic v2 schemas"]
    end

    subgraph WORKER["⚙️ Compute Layer — Celery Worker (Docker)"]
        direction LR
        CELERY["🐝 Celery 5.5 worker<br/>redis broker"]
        DSP["🔬 signalscope_dsp<br/>(pip install -e — shared with API)"]
    end

    subgraph DATA["💾 Data Layer"]
        subgraph PG["PostgreSQL 16 (Docker :5432)"]
            MODELS["🏛️ SQLAlchemy 2.0 async models<br/>users · projects · recordings<br/>parameter_estimates · jobs"]
        end
        subgraph RD["Redis 7 (Docker :6379)"]
            B1["db 0 — cached/rate-limit state"]
            B2["db 1 — Celery broker"]
            B3["db 2 — Celery result backend"]
        end
        VOL["📦 uploads_data volume<br/>raw recordings on disk"]
    end

    subgraph PIPELINE["🧠 DSP Pipeline (inside signalscope_dsp)"]
        direction TB
        LOAD["📂 Signal loader<br/>WAV · raw-IQ · SigMF · synthetic gen"]
        ROI["✂️ ROI crop"]
        PSD["📈 Spectral analysis<br/>PSD · waterfall · spectral features"]
        BURST["⚡ Burst detection + stats"]
        MOD["📶 Modulation classification<br/>BPSK · QPSK · 16-QAM · 2-FSK"]
        SYM["🏷️ Symbol-rate estimation<br/>(multi-candidate + evidence)"]
        DEMOD["🔉 Demodulation"]
        DEINT["🔀 De-interleaving"]
        FEC["🛡️ FEC — rate-1/2<br/>convolutional + Viterbi"]
        BITS["🧬 Bit correlation"]
        PROV["✅ Provenance assembly<br/>source · confidence · evidence · warnings"]
    end

    U -->|HTTPS :3000| NEXT
    NEXT --> PLOTLY
    NEXT --> UI
    NEXT --> QUERY
    QUERY -->|"GET /api/... {JWT cookie}"| ROUTERS
    ROUTERS --> AUTH
    ROUTERS --> RATE
    ROUTERS --> VALID
    ROUTERS --> SCH
    ROUTERS -->|"POST estimate-parameters → job_id (202)"| SCH
    SCH -->|"job.delay() → enqueue"| B2
    B2 -->|"consume task"| CELERY
    CELERY --> DSP
    DSP --> LOAD --> ROI --> PSD & BURST
    PSD --> MOD
    BURST --> MOD
    MOD --> SYM
    MOD & SYM --> DEMOD --> DEINT --> FEC --> BITS
    BITS --> PROV
    CELERY -->|"SQLAlchemy upsert"| MODELS
    ROUTERS -->|"health / dashboards / list"| MODELS
    ROUTERS -->|"read/write files"| VOL
    ROUTERS -->|"rate limit + job lookup"| B1
    DSP -->|"reads recording file"| VOL
    ROUTERS -->|"job status {PENDING→SUCCESS}"| B3
    QUERY -->|"polls GET /api/jobs/{id} every 2s"| ROUTERS
```

---

## 🧩 Decomposition Notes

### 1. Client Layer
The browser is a pure **JWT cookie-authenticated** SPA. TanStack Query owns server-state: the job is polled every **2 s** while `queued`/`running`, and the parameter-estimate query is **invalidated and refetched automatically the moment the job flips to `completed`**. No hard refreshes — results stream in.

### 2. Application Layer (FastAPI)
- Auth with `argon2` password hashing, JWT in an httpOnly cookie (Bearer fallback for API tooling).
- All uploads validated for type (`wav/raw/sigmf`) and size (200 MB cap).
- `POST /api/projects/{id}/estimate-parameters` returns **202 Accepted** with a `job_id` — the client never blocks.

### 3. Compute Layer (Celery Worker)
- Consumes tasks from **Redis db 1**, reports results to **Redis db 2**.
- Runs `signalscope_dsp` — the same library is `pip install -e`'d into the worker **and** the API, so estimates and pre-checks can never drift out of sync.

### 4. DSP Pipeline
`load → crop → spectral/burst analysis → modulation → symbol rate → demod → de-interleave → FEC → bit correlation → provenance assembly`. Every stage emits candidates with **evidence strings**; the final `Estimate` carries `{name, value, unit, source, confidence, alternatives, warnings}`.

### 5. Data Layer
- **Postgres** — relational store for users, projects, recordings, jobs, and `parameter_estimates` (JSONFlex `value_json` + `evidence_json`).
- **Redis db 0** — rate-limit counters and job-metadata lookups.
- **Volume** — recorded RF files kept on disk, referenced from the DB, never in-memory.

---

## 🔄 Request / Lifecycle Flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as FastAPI
    participant R as Redis Broker
    participant W as Celery Worker
    participant P as Postgres

    B->>A: POST /estimate-parameters (JWT)
    A->>R: job.delay(project_id)
    A-->>B: 202 { job_id, status:"queued" }
    B->>W: worker picks task
    W->>W: signalscope_dsp pipeline
    W->>P: upsert parameter_estimates
    W-->>R: mark SUCCESS
    loop every 2s
        B->>A: GET /jobs/{id}
        A-->>B: status:"running"
    end
    B->>A: GET /jobs/{id}
    A-->>B: status:"completed"
    B->>A: GET /projects/{id}/parameters (refetched)
    A-->>B: estimates[ ] with source+confidence+evidence
```

---

## 💻 Local Development Topology

| Container | Image build | Exposed port | Role |
|-----------|-------------|--------------|------|
| `web` | `docker/Dockerfile.web` | `3000` | Next.js standalone server |
| `api` | `docker/Dockerfile.api` | `8000` | FastAPI + `/docs` |
| `worker` | `docker/Dockerfile.worker` | — | Celery DSP executor |
| `postgres` | `postgres:16-alpine` | `5432` | Primary datastore |
| `redis` | `redis:7-alpine` | `6379` | Broker + backend + cache |

> The dev overlay (`docker-compose.dev.yml`) adds hot-reload for api/worker. Run the web dev server on the host for frontend HMR.

---

<div align="center">

**_"Every number is an estimate. Every estimate has a source, a confidence, and evidence you can read."_**

[← Back to README](./README.md)

</div>