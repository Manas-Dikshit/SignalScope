<div align="center">

# SignalScope AI — System Architecture

**How the frontend, API, Celery worker, DSP core, data stores, and optional Gemma 4 sidecar fit together.**

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
![Gemma](https://img.shields.io/badge/Gemma%204-optional-4285F4?style=for-the-badge&logo=google&logoColor=white)

</div>

---

## System overview

SignalScope turns raw RF recordings into **explainable parameter estimates**.

The deterministic path is fully async: the browser uploads a recording, the API validates it with the same DSP loaders used by the worker, Celery runs the analysis pipeline in the background, and provenance rows land in PostgreSQL. The UI polls job status and refetches results when the job completes.

An optional Gemma 4 sidecar adds a cited analyst brief on top of the stored evidence. It is **not** part of the deterministic truth path: it reads evidence, calls allowlisted DSP tools, and returns `ai_hypothesis` output whose numbers are substituted by the backend.

---

## System design diagram

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
    subgraph CLIENT["Client"]
        U["Analyst<br/><span style='opacity:.75;font-size:12px'>authenticated browser session · JWT cookie</span>"]
    end

    subgraph FRONTEND["Frontend · Next.js 14"]
        direction LR
        N["Dashboard · Recording library · Analysis workspace<br/><span style='opacity:.75;font-size:12px'>Waveform · I/Q scatter · PSD · waterfall · proof panels</span>"]
        Q["TanStack Query<br/><span style='opacity:.75;font-size:12px'>2 s job polling · invalidate on completion</span>"]
        N --- Q
    end

    subgraph API["API · FastAPI"]
        direction LR
        A["REST /api/* · JWT auth<br/><span style='opacity:.75;font-size:12px'>auth · uploads · projects · recordings · jobs</span>"]
        I["Insights router<br/><span style='opacity:.75;font-size:12px'>POST/GET /api/projects/{id}/insights</span>"]
        T["Private DSP tools<br/><span style='opacity:.75;font-size:12px'>/internal/dsp-tools/{tool} + token</span>"]
        A --- I
        A --- T
    end

    subgraph WORKER["Compute · Celery worker"]
        direction TB
        C["estimate_parameters_task<br/><span style='opacity:.75;font-size:12px'>load → condition → spectrum → bursts → modulation →<br/>symbol-rate → interferometry → provenance</span>"]
        G["generate_insight_task<br/><span style='opacity:.75;font-size:12px'>evidence bundle → images → AI sidecar → validation</span>"]
    end

    subgraph AI["Optional · Gemma 4 sidecar"]
        direction LR
        M["Local model<br/><span style='opacity:.75;font-size:12px'>fake · transformers</span>"]
        L["Agent loop<br/><span style='opacity:.75;font-size:12px'>allowlisted tools · max steps · timeout</span>"]
        V["Validation<br/><span style='opacity:.75;font-size:12px'>schema · citations · numeric guard</span>"]
        M --- L --- V
    end

    subgraph DATA["Data"]
        direction LR
        P["PostgreSQL 16<br/><span style='opacity:.75;font-size:12px'>users · recordings · projects · jobs ·<br/>parameter_estimates · analysis_insights</span>"]
        R["Redis 7<br/><span style='opacity:.75;font-size:12px'>Celery broker · result backend</span>"]
        D["Upload volume<br/><span style='opacity:.75;font-size:12px'>raw RF files on disk</span>"]
    end

    U -->|"① upload / load demo"| N
    N -->|"② REST + JWT"| A
    A -->|"③ job.delay(project_id)"| R
    A -.->|"202 · { job_id }"| N
    R -->|"④ consume task"| C
    C -->|"⑤ read recording"| D
    C -->|"⑥ upsert estimates + evidence"| P
    C -.->|"mark SUCCESS"| R
    N -->|"⑦ poll /jobs/{id} · 2 s"| A
    A -->|"⑧ estimates + proof payloads"| P
    N -.->|"⑨ optional: POST /insights"| I
    I -->|"queue"| G
    G -->|"⑩ EvidenceBundle + PNGs"| A
    A -->|"⑪ /v1/insight"| M
    M -->|"tool calls"| L
    L -->|"X-Internal-Token"| T
    T -->|"DSP results"| L
    V -->|"validated cited brief"| G
    G -->|"⑫ analysis_insights row"| P
    N -->|"⑬ AI brief labelled ai_hypothesis"| P
```

---

## Layer decomposition

### 1. Client layer

- Next.js 14 App Router SPA with JWT cookie authentication.
- TanStack Query owns server state. Parameter jobs poll every 2 s and insight jobs every 1.5 s while `queued`/`running`; results are invalidated when the job flips to `completed`.
- Plotly renders waveform, I/Q scatter, PSD, waterfall, constellation, proof spectra, and ranked candidate bars.
- `ProofPanel` drills into evidence inline on desktop and as a bottom sheet at ≤375 px.
- The UI is installable (web manifest + icons) and responsive.

### 2. Application layer (FastAPI)

- Auth with Argon2 password hashing and JWT in an httpOnly cookie (Bearer fallback for tooling).
- Uploads validated for format (`wav`, `raw_iq`, `sigmf`), size (200 MB cap), and content using the DSP loaders; files are streamed to disk with SHA-256 hashing and duplicate detection.
- `POST /api/projects/{id}/estimate-parameters` returns **202 Accepted** with a job id.
- Deep analysis runs synchronously over a bounded ROI window for interactive proof and FEC experiments.
- The optional `POST /api/projects/{id}/insights` route queues an AI brief and returns **202**; it returns **503** when `AI_ENABLED=false`.
- `/internal/dsp-tools/{tool_name}` is a private, shared-secret route used only by the AI sidecar. An empty `INTERNAL_API_TOKEN` disables it.

### 3. Compute layer (Celery worker)

- Consumes tasks from Redis db 1 and reports to Redis db 2.
- Runs `signalscope_dsp` — installed editable into both the worker and API so pre-checks and estimates cannot drift.
- `estimate_parameters_task`: full-recording analysis and provenance persistence.
- `generate_insight_task`: builds an evidence bundle, renders evidence images, calls the AI sidecar, validates the response, and stores `analysis_insights`.
- AI failure never destroys DSP results; the failure is stored with an error message for the UI.

### 4. DSP pipeline

```text
load → ROI crop → condition → PSD/waterfall → spectral features
     → burst detection → modulation classification
     → symbol-rate candidates → interferometric origin
     → demodulation → de-interleaving → FEC → bit correlation
     → provenance assembly
```

Every stage emits candidates with **evidence strings**. The final `Estimate` carries:

```json
{
  "name": "symbol_rate",
  "value": 250000.0,
  "unit": "symbols/s",
  "source": "estimated",
  "confidence": 0.93,
  "evidence": ["dominant spectral peak at 250.0 kHz ..."],
  "alternatives": [],
  "warnings": []
}
```

**Sources** — `metadata`, `user_supplied`, `measured`, `estimated`, `hypothesis`, `ai_hypothesis`, `unknown`.

**Interferometric origin** — when a raw-IQ recording contains simultaneous antenna channels (`channels >= 2`, interleaved `I0 Q0 I1 Q1 ...` frames), the worker correlates antennas and returns `sky`, `near_field_observatory`, or `inconclusive`. Coherence, phase-slope linearity, delay, and optional `baseline_m` bounds are included in the evidence.

### 5. AI layer (optional)

- `services/ai` is a separate FastAPI service on port `8100`, started with the `ai` Compose profile.
- Backends: deterministic `fake` (no model download) and `transformers` (local Gemma 4). Other local runtimes (GGUF/Ollama-class) can be added behind the same `InsightBackend` protocol.
- Default model: `google/gemma-4-E4B-it` (Apache-2.0).
- Rendered evidence images (PSD, waterfall, constellation, M-th power) are generated with Pillow and sent as bounded PNG data URIs; raw I/Q is never sent.
- The model may call only: `get_project_evidence`, `run_deep_analysis`, `try_demodulation`, `try_fec`.
- Tool count and duration are bounded by `AI_MAX_TOOL_STEPS` and `AI_TOOL_TIMEOUT_SECONDS`.
- Validation enforces strict JSON schema, evidence references, numeric substitution (`{{estimate:name}}`), and allowlisted tool traces. Failures retry once, then fall back safely.

### 6. Data layer

- **PostgreSQL 16** — users, recordings, metadata, projects, jobs, parameter estimates (`value_json` + `evidence_json`), and analysis insights (`response_json`, `tool_trace_json`, `citations_json`).
- **Redis db 0** — configured via `REDIS_URL` for app cache (currently unused).
- **Redis db 1** — Celery broker.
- **Redis db 2** — Celery result backend and job status.
- **Upload volume** — raw RF files on disk, referenced from the database and never held in memory beyond a bounded window.

---

## Request / lifecycle flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as FastAPI
    participant R as Redis
    participant W as Celery Worker
    participant P as Postgres
    participant G as Gemma 4 sidecar

    B->>A: POST /projects/{id}/estimate-parameters (JWT)
    A->>R: enqueue estimate_parameters
    A-->>B: 202 { job_id, status: "queued" }
    R->>W: deliver task
    W->>W: load → DSP pipeline → provenance
    W->>P: upsert parameter_estimates
    W-->>R: mark SUCCESS

    loop every 2 s
        B->>A: GET /jobs/{id}
        A-->>B: status: running
    end

    B->>A: GET /jobs/{id}
    A-->>B: status: completed
    B->>A: GET /projects/{id}/parameters
    A-->>B: estimates[] with source + confidence + evidence

    opt AI enabled
        B->>A: POST /projects/{id}/insights
        A->>R: enqueue generate_insight
        A-->>B: 202 { job_id }
        R->>W: deliver insight task
        W->>P: read evidence bundle
        W->>G: POST /v1/insight (evidence + PNGs)
        G->>A: allowlisted DSP tool calls
        A-->>G: tool results
        G-->>W: validated cited brief (ai_hypothesis)
        W->>P: insert analysis_insights
        B->>A: GET /projects/{id}/insights
        A-->>B: cited brief + tool trace + citations
    end
```

---

## Local development topology

| Container | Image build | Port | Role |
|---|---|---|---|
| `web` | `docker/Dockerfile.web` | `3000` | Next.js standalone server |
| `api` | `docker/Dockerfile.api` | `8000` | FastAPI + `/docs` |
| `worker` | `docker/Dockerfile.worker` | — | Celery DSP/insight executor |
| `ai` (optional) | `services/ai/Dockerfile` | `8100` | Local Gemma 4 sidecar |
| `postgres` | `postgres:16-alpine` | `5432` | Primary datastore |
| `redis` | `redis:7-alpine` | `6379` | Broker + backend + cache |

> The dev overlay (`docker-compose.dev.yml`) adds hot-reload for API and worker. Run the web dev server on the host for frontend HMR. The AI service is opt-in via `docker compose --profile ai up`.

---

## Scaling and failure behavior

| Concern | Behavior |
|---|---|
| Large recordings | Uploads are streamed; interactive analysis reads a bounded window (200k samples); the worker processes the ROI with the full pipeline. |
| Worker down | Jobs remain queued; the UI keeps polling and surfaces the state instead of hanging. |
| AI down or invalid | DSP results are untouched; the insight row records the error and the UI shows an explicit fallback. |
| Cross-user access | Every project, recording, job, and insight route checks ownership. |
| Rate limiting | In-process fixed-window limits per client IP: login 10/min, upload 30/min. |
| Secrets | `SECRET_KEY` must be overridden; `INTERNAL_API_TOKEN` gates the private DSP tool route. |
| AI numeric honesty | Numbers in the brief are backend-substituted from provenance; the model never writes authoritative values. |

---

<div align="center">

**_"Every number is an estimate. Every estimate has a source, a confidence, and evidence you can read."_**

[← Back to README](./README.md)

</div>
