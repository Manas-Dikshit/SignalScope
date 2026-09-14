<div align="center">

# 🛠️ SignalScope AI — Detailed Technical Architecture

**A complete, low-level view: every service, port, data store, message hop, and DSP stage.**

</div>

---

## 🧱 Service Topology

| Container | Tech | Port | Role |
|-----------|------|------|------|
| `web` | Next.js 14 · React 18 · TypeScript 5 · Tailwind · shadcn/ui | `3000` | SPA + SSR shell, TanStack Query polling, Plotly visualizations |
| `api` | FastAPI 0.115 · Pydantic v2 · SQLAlchemy 2.0 async | `8000` | REST gateway: auth, uploads, projects, recordings, jobs, dashboard |
| `worker` | Celery 5.5 · `signalscope_dsp` (editable) | — | Background executor for the DSP pipeline |
| `postgres` | PostgreSQL 16 | `5432` | Primary relational store |
| `redis` | Redis 7 | `6379` | db0 rate-limit/cache · db1 Celery broker · db2 result backend |
| `uploads_data` | Docker volume | — | Raw RF recordings on disk (never in memory) |

---

## 🧠 Detailed System Diagram

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
    'tertiaryColor': '#111c33',
    'fontFamily': 'Inter, ui-sans-serif, system-ui, sans-serif',
    'fontSize': '13px'
  },
  'flowchart': { 'curve': 'basis', 'nodeSpacing': 35, 'rankSpacing': 45, 'padding': 8 }
}}%%
flowchart TB
    subgraph CLIENT["👤 Client Layer"]
        U["👩‍💻 Analyst / Operator<br/><span style='opacity:.75;font-size:11px'>authenticated browser session · JWT cookie</span>"]
    end

    subgraph WEB["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/nextdotjs/e2e8f0' height='14'/> Frontend — Next.js 14 · Docker :3000"]
        direction LR
        APP["⚛️ App Router · RSC<br/><span style='opacity:.75;font-size:11px'>React 18 · TypeScript 5 · Tailwind · shadcn/ui</span>"]
        TSQ["🔁 TanStack Query 5<br/><span style='opacity:.75;font-size:11px'>server-state cache · 2 s job polling · refetch on complete</span>"]
        PLT["📊 Plotly.js<br/><span style='opacity:.75;font-size:11px'>waveform · IQ scatter · waterfall · spectrum</span>"]
        UI2["🧩 Evidence UI<br/><span style='opacity:.75;font-size:11px'>confidence tiers · ProofPanel drill-down · FEC selector<br/>inline expand (desktop) · bottom sheet (≤375 px)</span>"]
        APP --> TSQ
        APP --> PLT
        APP --> UI2
    end

    subgraph API["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/fastapi/4f94ef' height='14'/> Backend API — FastAPI · Docker :8000"]
        direction TB
        ROUTERS["🗂️ Routers<br/><span style='opacity:.75;font-size:11px'>auth · uploads · projects · recordings · jobs · dashboard</span>"]
        AUTH["🔐 Auth<br/><span style='opacity:.75;font-size:11px'>JWT httpOnly cookie · python-jose · passlib/argon2</span>"]
        RATE["⏱️ Rate limiting<br/><span style='opacity:.75;font-size:11px'>login 10/min · upload 30/min (Redis db0)</span>"]
        VALID["🧾 Upload validation<br/><span style='opacity:.75;font-size:11px'>WAV · raw-IQ · SigMF · 200 MB cap</span>"]
        SCH["📝 Pydantic v2 schemas<br/><span style='opacity:.75;font-size:11px'>request/response contracts</span>"]
        ORM["🗄️ SQLAlchemy 2.0 async<br/><span style='opacity:.75;font-size:11px'>asyncpg driver</span>"]
        ROUTERS --- AUTH
        ROUTERS --- RATE
        ROUTERS --- VALID
        ROUTERS --- SCH
        ROUTERS --- ORM
    end

    subgraph WORKER["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/celery/e2e8f0' height='14'/> Compute — Celery Worker · Docker"]
        direction TB
        TASK["🐝 estimate_parameters_task<br/><span style='opacity:.75;font-size:11px'>single job = one recording analysed end-to-end</span>"]
        DSP["🔬 signalscope_dsp<br/><span style='opacity:.75;font-size:11px'>pip install -e · shared with API (no drift)</span>"]
        subgraph PIPELINE["🧠 DSP Pipeline (stage order)"]
            direction TB
            LOAD["📂 Loader<br/><span style='opacity:.75;font-size:11px'>WAV · raw-IQ · SigMF · synthetic gen</span>"]
            ROI["✂️ ROI crop"]
            SPECT["📈 Spectral analysis<br/><span style='opacity:.75;font-size:11px'>PSD · waterfall · features</span>"]
            BURST["⚡ Burst detection<br/><span style='opacity:.75;font-size:11px'>+ stats + alternatives</span>"]
            MOD["📶 Modulation class<br/><span style='opacity:.75;font-size:11px'>BPSK · QPSK · 16-QAM · 2-FSK</span>"]
            SYM["🏷️ Symbol-rate estimate<br/><span style='opacity:.75;font-size:11px'>multi-candidate + proof</span>"]
            DEMOD["🔉 Demodulation"]
            DEINT["🔀 De-interleave<br/><span style='opacity:.75;font-size:11px'>block · conv · diagonal · pseudo-random</span>"]
            FEC["🛡️ FEC decode<br/><span style='opacity:.75;font-size:11px'>Viterbi · Reed–Solomon · LDPC<br/>concatenated RS+conv · CRC verify</span>"]
            BITS["🧬 Bit correlation"]
            PROV["✅ Provenance assembly<br/><span style='opacity:.75;font-size:11px'>source · confidence · evidence · warnings<br/>alternatives · proof spectra</span>"]
            LOAD --> ROI --> SPECT
            SPECT --> BURST
            SPECT --> MOD
            BURST --> MOD
            MOD --> SYM
            MOD --> DEMOD
            SYM --> DEMOD
            DEMOD --> DEINT --> FEC --> BITS --> PROV
        end
        TASK --> DSP
        DSP --> PIPELINE
    end

    subgraph DATA["<img style='vertical-align:middle' src='https://cdn.simpleicons.org/postgresql/dc7a3a' height='14'/> Data Layer"]
        direction LR
        subgraph PG["PostgreSQL 16 · :5432"]
            TBLS["🏛️ Tables<br/><span style='opacity:.75;font-size:11px'>users · projects · recordings<br/>parameter_estimates (value_json +<br/>evidence_json) · jobs</span>"]
        end
        subgraph RD["Redis 7 · :6379"]
            D0["db0 — rate limits / cache"]
            D1["db1 — Celery broker (queue)"]
            D2["db2 — Celery result backend<br/><span style='opacity:.75;font-size:11px'>job status ⟳</span>"]
        end
        VOL["📦 uploads_data volume<br/><span style='opacity:.75;font-size:11px'>raw RF files</span>"]
    end

    U -->|"① upload recording (WAV/raw/SigMF)"| APP
    APP -->|"② REST /api/* · {JWT}"| ROUTERS
    ROUTERS -->|"POST /projects/{id}/estimate-parameters"| SCH
    SCH -->|"job.delay(project_id)"| D1
    SCH -.->|"202 · { job_id, queued }"| TSQ
    D1 -->|"③ consume task"| TASK
    TASK -->|"④ run pipeline"| DSP
    PIPELINE -->|"⑤ read RF file"| VOL
    PIPELINE -->|"evidence + proofs"| PROV
    PROV -->|"⑥ upsert estimates"| ORM
    ORM --> TBLS
    TASK -->|"mark SUCCESS"| D2
    TASK -->|"clear running flag"| D1
    TSQ -->|"⑦ poll GET /jobs/{id} · 2 s"| ROUTERS
    ROUTERS -->|"job status lookup"| D2
    ROUTERS -->|"GET /projects/{id}/deep-analysis?fec_type=…"| ORM
    ORM --> TBLS
    ROUTERS -->|"rate limit counters"| D0
    ROUTERS -->|"8️⃣ uploads/previews"| VOL
```

---

## 🔄 Async Job Lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as FastAPI
    participant R as Redis
    participant W as Celery Worker
    participant P as Postgres
    participant V as uploads volume

    B->>A: POST /projects/{id}/estimate-parameters
    A->>A: validate project + recording
    A->>R: broker.enqueue(job_id, project_id)
    A-->>B: 202 { job_id, status: "queued" }
    R->>W: deliver task
    W->>V: open recording file
    W->>W: signalscope_dsp full pipeline
    activate W
    W->>P: upsert parameter_estimates(+evidence_json)
    W-->>R: result-backend: mark SUCCESS
    deactivate W
    loop every 2 s on client
        B->>A: GET /jobs/{id}
        A->>R: read status
        R-->>A: running / pending
        A-->>B: status
    end
    B->>A: GET /jobs/{id}
    A-->>B: status: "completed"
    B->>A: GET /projects/{id}/deep-analysis
    A->>P: read estimates
    P-->>A: rows with evidence + proof spectra
    A-->>B: estimates + candidates + proofs
    B->>B: render ProofPanels (inline / bottom sheet)
```

---

<div align="center">

**_"Every number is an estimate. Every estimate has a source, a confidence, and evidence you can read."_**

[← Back to README](./README.md)

</div>