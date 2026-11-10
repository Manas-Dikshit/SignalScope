<div align="center">

# SignalScope AI — Detailed Technical Architecture

**A low-level view: every service, port, data store, message hop, DSP stage, and optional AI hop.**

</div>

---

## Service topology

| Container | Tech | Port | Role |
|-----------|------|------|------|
| `web` | Next.js 14 · React 18 · TypeScript 5 · Tailwind · shadcn/ui | `3000` | SPA + SSR shell, TanStack Query polling, Plotly visualizations, web manifest |
| `api` | FastAPI 0.115 · Pydantic v2 · SQLAlchemy 2.0 async | `8000` | REST gateway: auth, uploads, recordings, projects, jobs, insights, dashboard |
| `worker` | Celery 5.5 · `signalscope_dsp` (editable) | — | Background executor for DSP and insight tasks |
| `ai` *(optional)* | FastAPI · Gemma 4 | `8100` | Cited analyst brief, allowlisted DSP tools, evidence-image validation |
| `postgres` | PostgreSQL 16 | `5432` | Primary relational store |
| `redis` | Redis 7 | `6379` | db0 app cache (configured, unused) · db1 Celery broker · db2 result backend |
| `uploads_data` | Docker volume | — | Raw RF recordings on disk (never in memory) |
| `ai_models` | Docker volume | — | Optional local Gemma 4 weights / HF cache |

---

## Detailed system diagram

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
    subgraph CLIENT["Client Layer"]
        U["Analyst / Operator<br/><span style='opacity:.75;font-size:11px'>authenticated browser session · JWT cookie</span>"]
    end

    subgraph WEB["Frontend — Next.js 14 · Docker :3000"]
        direction LR
        APP["App Router · RSC<br/><span style='opacity:.75;font-size:11px'>React 18 · TypeScript 5 · Tailwind · shadcn/ui</span>"]
        TSQ["TanStack Query 5<br/><span style='opacity:.75;font-size:11px'>server-state cache · 2 s job polling · refetch on complete</span>"]
        PLT["Plotly.js<br/><span style='opacity:.75;font-size:11px'>waveform · IQ scatter · waterfall · spectrum · constellation</span>"]
        UI2["Evidence UI<br/><span style='opacity:.75;font-size:11px'>confidence tiers · ProofPanel drill-down · FEC selector<br/>demo samples · AI brief · bottom sheet ≤375 px</span>"]
        APP --> TSQ
        APP --> PLT
        APP --> UI2
    end

    subgraph API["Backend API — FastAPI · Docker :8000"]
        direction TB
        ROUTERS["Routers<br/><span style='opacity:.75;font-size:11px'>auth · uploads · recordings · projects · jobs · insights · dashboard</span>"]
        AUTH["Auth<br/><span style='opacity:.75;font-size:11px'>JWT httpOnly cookie · python-jose · passlib/argon2</span>"]
        RATE["Rate limiting<br/><span style='opacity:.75;font-size:11px'>login 10/min · upload 30/min (in-process per IP)</span>"]
        VALID["Upload validation<br/><span style='opacity:.75;font-size:11px'>WAV · raw-IQ · SigMF · 200 MB cap · SHA-256 · duplicate check</span>"]
        SCH["Pydantic v2 schemas<br/><span style='opacity:.75;font-size:11px'>request/response contracts</span>"]
        TOOLS["Private DSP tools<br/><span style='opacity:.75;font-size:11px'>/internal/dsp-tools/{tool} · X-Internal-Token</span>"]
        IMG["Evidence images<br/><span style='opacity:.75;font-size:11px'>Pillow PNGs · per-image + bundle caps · SHA-256 audit</span>"]
        ORM["SQLAlchemy 2.0 async<br/><span style='opacity:.75;font-size:11px'>asyncpg driver</span>"]
        ROUTERS --- AUTH
        ROUTERS --- RATE
        ROUTERS --- VALID
        ROUTERS --- SCH
        ROUTERS --- TOOLS
        ROUTERS --- IMG
        ROUTERS --- ORM
    end

    subgraph WORKER["Compute — Celery Worker · Docker"]
        direction TB
        TASK["estimate_parameters_task<br/><span style='opacity:.75;font-size:11px'>single job = one recording analysed end-to-end</span>"]
        INS["generate_insight_task<br/><span style='opacity:.75;font-size:11px'>evidence bundle + images + AI call + validation</span>"]
        DSP["signalscope_dsp<br/><span style='opacity:.75;font-size:11px'>pip install -e · shared with API (no drift)</span>"]
        subgraph PIPELINE["DSP Pipeline (stage order)"]
            direction TB
            LOAD["Loader<br/><span style='opacity:.75;font-size:11px'>WAV · raw-IQ · SigMF · synthetic gen</span>"]
            ROI["ROI crop"]
            SPECT["Spectral analysis<br/><span style='opacity:.75;font-size:11px'>PSD · waterfall · features</span>"]
            BURST["Burst detection<br/><span style='opacity:.75;font-size:11px'>+ stats + alternatives</span>"]
            MOD["Modulation class<br/><span style='opacity:.75;font-size:11px'>BPSK · QPSK · 8-PSK · 16-QAM · 2-FSK</span>"]
            SYM["Symbol-rate estimate<br/><span style='opacity:.75;font-size:11px'>multi-candidate + proof</span>"]
            INTER["Interferometric origin<br/><span style='opacity:.75;font-size:11px'>sky · near-field · inconclusive</span>"]
            DEMOD["Demodulation"]
            DEINT["De-interleave<br/><span style='opacity:.75;font-size:11px'>block · conv · diagonal · pseudo-random</span>"]
            FEC["FEC decode<br/><span style='opacity:.75;font-size:11px'>Viterbi · Reed–Solomon · LDPC<br/>concatenated RS+conv · CRC verify</span>"]
            BITS["Bit correlation"]
            PROV["Provenance assembly<br/><span style='opacity:.75;font-size:11px'>source · confidence · evidence · warnings<br/>alternatives · proof spectra</span>"]
            LOAD --> ROI --> SPECT
            SPECT --> BURST
            SPECT --> MOD
            BURST --> MOD
            MOD --> SYM
            MOD --> DEMOD
            SYM --> DEMOD
            SPECT --> INTER
            DEMOD --> DEINT --> FEC --> BITS --> PROV
        end
        TASK --> DSP
        INS --> DSP
        DSP --> PIPELINE
    end

    subgraph AI["Optional AI — Gemma 4 sidecar · Docker :8100"]
        direction LR
        MODEL["Local model<br/><span style='opacity:.75;font-size:11px'>fake · transformers</span>"]
        LOOP["Agent loop<br/><span style='opacity:.75;font-size:11px'>max steps · tool timeout · trace</span>"]
        VALIDATE["Validation<br/><span style='opacity:.75;font-size:11px'>schema · citations · numeric guard</span>"]
        MODEL --> LOOP --> VALIDATE
    end

    subgraph DATA["Data Layer"]
        direction LR
        subgraph PG["PostgreSQL 16 · :5432"]
            TBLS["Tables<br/><span style='opacity:.75;font-size:11px'>users · projects · recordings · jobs<br/>parameter_estimates (value_json + evidence_json)<br/>analysis_insights (response/tool_trace/citations)</span>"]
        end
        subgraph RD["Redis 7 · :6379"]
            D0["db0 - app cache (configured, unused)"]
            D1["db1 — Celery broker (queue)"]
            D2["db2 — Celery result backend<br/><span style='opacity:.75;font-size:11px'>job status</span>"]
        end
        VOL["uploads_data volume<br/><span style='opacity:.75;font-size:11px'>raw RF files</span>"]
        MODELS["ai_models volume<br/><span style='opacity:.75;font-size:11px'>optional model cache</span>"]
    end

    U -->|"① upload / load demo"| APP
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
    TSQ -->|"⑦ poll GET /jobs/{id} · 2 s"| ROUTERS
    ROUTERS -->|"job status lookup"| D2
    ROUTERS -->|"GET /projects/{id}/analysis?fec_type=…"| ORM
    ORM --> TBLS
    ROUTERS -->|"⑧ previews / uploads"| VOL
    ROUTERS -.->|"⑨ optional POST /insights"| INS
    INS -->|"⑩ evidence bundle + PNGs"| IMG
    INS -->|"⑪ /v1/insight"| MODEL
    LOOP -->|"allowlisted tool call"| TOOLS
    TOOLS -->|"DSP result"| LOOP
    VALIDATE -->|"⑫ validated cited brief"| INS
    INS -->|"⑬ analysis_insights row"| TBLS
    MODEL -->|"read weights"| MODELS
```

---

## Async job lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as FastAPI
    participant R as Redis
    participant W as Celery Worker
    participant P as Postgres
    participant V as uploads volume
    participant G as Gemma 4 sidecar

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
    B->>A: GET /projects/{id}/parameters
    A->>P: read estimates
    P-->>A: rows with evidence + proof spectra
    A-->>B: estimates + candidates + proofs
    B->>B: render ProofPanels (inline / bottom sheet)

    opt AI enabled
        B->>A: POST /projects/{id}/insights
        A->>R: enqueue generate_insight
        A-->>B: 202 { job_id }
        R->>W: deliver insight task
        W->>P: read evidence bundle
        W->>W: render PSD / waterfall / constellation / M-th power
        W->>G: POST /v1/insight (evidence + PNGs)
        G->>A: allowlisted DSP tool call + token
        A-->>G: tool result
        G-->>W: validated cited brief (ai_hypothesis)
        W->>P: insert analysis_insights
        B->>A: GET /projects/{id}/insights
        A-->>B: brief + citations + tool trace
    end
```

---

## Stage contracts

### Loader layer

- WAV: mono or stereo I/Q; stereo modes `left_is_i_right_is_q`, `left_only`, `right_only`, `mono_mix`.
- Raw I/Q: dtype selection, endianness, `interleaved` / `separate_iq` / `real_only`, optional `sample_rate_hz`, `center_frequency_hz`, and `channels` for simultaneous antenna frames.
- SigMF: paired `-meta` + `-data` files, including standard metadata fields.
- Bounded windows (`sample_offset`, `max_samples`) keep interactive endpoints from loading multi-hundred-MB files.

### Estimate contract

```json
{
  "name": "modulation",
  "value": "QPSK",
  "unit": null,
  "source": "hypothesis",
  "confidence": 0.64,
  "evidence": ["4th-power spectral peakiness=0.88"],
  "alternatives": [
    { "value": "16-QAM", "confidence": 0.41, "evidence": ["amplitude-ring structure"] }
  ],
  "warnings": ["Modulation classification is a hypothesis."]
}
```

### Proof payloads

| Proof | Attached to | Produced by |
|---|---|---|
| M-th power spectra `order_2/4/8` | Modulation hypothesis | `modulation/classifier.py::mth_power_spectrum` |
| Symbol-clock spectrum | Symbol-rate candidates | `modulation/symbol_rate.py::symbol_clock_spectrum` |
| Run-length histogram + score | De-interleave candidates | `interleaving/block.py` |
| FEC detail (corrected, erasures, CRC, stage failure) | FEC result | `fec/` result dataclasses |
| Interferometric coherence / delay / bearing | Origin verdict | `interferometry/interferometric.py` |

---

## AI integration contract

| Piece | Details |
|---|---|
| API contract | `POST /v1/insight` with `project_id`, `prompt_version`, `evidence`, `images` |
| Response | Strict JSON: summary template, hypothesis, conflicts, anomalies, recommendations, unknowns, limitations, citations, tool trace |
| Numeric honesty | Model writes `{{estimate:name}}` placeholders; backend substitutes provenance values and rejects unsupported numbers |
| Tool allowlist | `get_project_evidence`, `run_deep_analysis`, `try_demodulation`, `try_fec` |
| Tool route | Private `/internal/dsp-tools/{tool_name}` with `X-Internal-Token` |
| Bounds | `AI_MAX_TOOL_STEPS`, `AI_TOOL_TIMEOUT_SECONDS`, `AI_TIMEOUT_SECONDS` |
| Images | PSD, waterfall, constellation, M-th power; PNG data URIs only; per-image and bundle caps |
| Failure behavior | Retry once with validation error; then deterministic fallback; DSP results preserved |
| Provenance | `Source.AI_HYPOTHESIS`; UI badge **AI-generated — verify evidence** |

---

## Local development topology

| Container | Image build | Exposed port | Role |
|-----------|-------------|--------------|------|
| `web` | `docker/Dockerfile.web` | `3000` | Next.js standalone server |
| `api` | `docker/Dockerfile.api` | `8000` | FastAPI + `/docs` |
| `worker` | `docker/Dockerfile.worker` | — | Celery DSP/insight executor |
| `ai` | `services/ai/Dockerfile` | `8100` | Optional Gemma 4 sidecar (`--profile ai`) |
| `postgres` | `postgres:16-alpine` | `5432` | Primary datastore |
| `redis` | `redis:7-alpine` | `6379` | Broker + backend + cache |

> The dev overlay (`docker-compose.dev.yml`) adds hot-reload for API and worker. Run the web dev server on the host for frontend HMR. The AI service is absent from the default stack and can be enabled with `docker compose --profile ai up`.

---

<div align="center">

**_"Every number is an estimate. Every estimate has a source, a confidence, and evidence you can read."_**

[← Back to README](./README.md)

</div>
