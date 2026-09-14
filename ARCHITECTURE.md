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

**Five layers, one goal: turn raw RF recordings into *explainable* parameter estimates.** The request path is fully async — the browser fires an analysis job, Celery executes the DSP pipeline in the background, and the frontend polls the job status until results land in Postgres.

---

## 📐 System Design Diagram

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'background': '#ffffff',
    'primaryColor': '#0f172a',
    'primaryTextColor': '#e2e8f0',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#64748b',
    'secondaryColor': '#1e293b',
    'tertiaryColor': '#0f172a',
    'fontFamily': 'Inter, ui-sans-serif, system-ui, sans-serif',
    'fontSize': '14px'
  },
  'flowchart': { 'curve': 'basis', 'nodeSpacing': 45, 'rankSpacing': 55, 'padding': 10 }
}}%%
flowchart TB
    subgraph CLIENT["👤 Client"]
        U["👩‍💻 Analyst<br/><span style='opacity:.75;font-size:12px'>browser session</span>"]
    end

    subgraph FRONTEND["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/nextdotjs/e2e8f0' height='15'/> &nbsp;<b>Frontend</b> · Next.js 14"]
        direction LR
        N["React / TypeScript · Tailwind<br/><span style='opacity:.75;font-size:12px'>upload · workspace · 2 s job polling</span>"]
    end

    subgraph API["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/fastapi/4f94ef' height='15'/> &nbsp;<b>API</b> · FastAPI"]
        direction LR
        A["REST /api/* · JWT auth<br/><span style='opacity:.75;font-size:12px'>uploads · projects · job dispatch</span>"]
    end

    subgraph WORKER["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/celery/e2e8f0' height='15'/> &nbsp;<b>Compute</b> · Celery worker"]
        direction TB
        C["signalscope_dsp<br/><span style='opacity:.75;font-size:12px'>load → spectrum → burst → modulation →<br/>symbol-rate → demod → FEC → evidence</span>"]
    end

    subgraph DATA["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/postgresql/dc7a3a' height='15'/> &nbsp;<b>Data</b>"]
        direction LR
        P["PostgreSQL<br/><span style='opacity:.75;font-size:12px'>projects · estimates · jobs</span>"]
        R["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/redis/e2e8f0' height='14'/> Redis<br/><span style='opacity:.75;font-size:12px'>job queue + status</span>"]
        V["📦 Volume<br/><span style='opacity:.75;font-size:12px'>raw RF files on disk</span>"]
    end

    U -->|"① upload a recording"| N
    N -->|"② POST /estimate-parameters"| A
    A -->|"③ job.delay(project_id)"| R
    A -.->|"202 · { job_id }"| N
    R -->|"④ consume task"| C
    C -->|"⑤ read RF file"| V
    C -->|"⑤ upsert estimates"| P
    C -.->|"mark SUCCESS"| R
    N -->|"⑥ poll /jobs/{id} → estimates + evidence"| A
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