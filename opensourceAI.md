# SignalScope AI — Open-Source AI Integration

Submission document for the **Best Open-Source AI Project** track.

SignalScope is an **explainable RF signal-analysis workbench**: signal and audio
recordings are turned into provenance-tracked parameter estimates (modulation,
symbol rate, SNR, demodulation, FEC, fingerprints) with every number backed by
evidence. Open-source / open-weight AI is one of the two pillars of the
product: an **open-weight language model is the analyst that explains the
results**, running fully locally inside the same stack.

| # | Component | What it is | License |
|---|-----------|------------|---------|
| 1 | SignalScope (this repo) | DSP + API + web workbench + **original model harness** | **MIT** ([./LICENSE](./LICENSE)) |
| 2 | [`google/gemma-4-E4B-it`](https://huggingface.co/google/gemma-4-E4B-it) | The open-weight analyst model that powers the AI insight feature | **Apache 2.0** (open-source *and* open-weight) |
| 3 | Runtime stack | Hugging Face `transformers`, `torch`, `accelerate`, FastAPI | BSD/Apache/OSI-approved |

We do **not** call any closed or hosted model. No OpenAI, Anthropic, or cloud
API is used anywhere; after the weights are downloaded once via Hugging Face,
the entire product runs **offline on the operator's machine**.

---

## 1. Approach: open-weight LLM integration + an original model harness

The challenge allows several approaches; we use **two of them together**:

1. **Open-weight model integration** — the Gemma 4 SLM is the reasoning core of
   the "AI analyst" feature.
2. **Model harness, built from scratch** — `services/ai/` is our own harness
   that manages prompts, context, tools, memory of past tool results, and
   actions around the model ([services/ai/app/agent.py](services/ai/app/agent.py) et al.).
   It is an original build, not a fork, so no "significant changes to an
   existing harness" requirement applies.

> Note on *agent skills*: we are not distributing an Agent Skills package, so
> that conditional standard does not apply to this submission. The harness is
> submitted as a self-contained service with its own repo documentation above.

## 2. The open-weight model

| Property | Value |
|---|---|
| Model | `google/gemma-4-E4B-it` ([Hugging Face](https://huggingface.co/google/gemma-4-E4B-it)) |
| Terms / license | **Apache 2.0** — the weights can be downloaded and run under the model provider's terms; the license is listed on the model card linked here |
| Size class | Effective ~4B parameters → **small language model** (≤ 10 B per the challenge definition) |
| Modalities | Text + image + audio for the E2B/E4B variants |
| Where weights live | Downloaded from Hugging Face into the `ai_models` Docker volume (`HF_HOME=/models`), never baked into the image |

Gemma 4 was chosen because the task is *engineering explanation, not
generation for its own sake*: we need a small, local, license-clean model that
(1) follows a strict JSON output contract, (2) emits tool calls reliably, and
(3) fits a laptop demo. E4B hits all three while staying under the SLM limit.

**What the model actually does** — it is the "Generate insight" feature:

Given the numeric evidence bundle produced by the deterministic DSP pipeline
(parameter estimates with confidences, spectral features, fingerprints, and up
to four rendered evidence plots), the model produces a parsed, validated
`analysis_insight` row:

* a plain-English **summary** of what the signal looks like,
* a labelled **AI hypothesis** (e.g. modulation class agreement/disagreement),
* **conflicts** between different DSP viewpoints,
* **anomalies** worth a second look,
* **recommended next actions** — e.g. "low modulation confidence → try QPSK
  demodulation at 2 samples/symbol", which a human (or the tool loop, below)
  can then execute,
* **unknowns and limitations**, so the UI never shows false certainty.

Every claim must cite an evidence name; numbers are never written by the model
itself (§4). The task it "solves" is the one domain experts do manually after
every analysis: *interpret the measurement set and decide what to check next.*

## 3. End-to-end data flow

```
recording upload → DSP pipeline (estimates, deep analysis, fingerprints)
        │
        ▼
Celery task generate_insight          (services/api/app/tasks.py)
  ├─ builds the evidence bundle        (estimates, recording metadata, fingerprint)
  ├─ renders bounded evidence PNGs     (PSD, waterfall, constellation, M-th power)
  │   └─ ≤ 300 KB/image, ≤ 1 MB total, sha256 audit record
  └─ HTTP POST /v1/insight ───────────►  AI sidecar (services/ai, port 8100)
                                            │
                                            ▼
                                      run_analyst() model harness
                                        ├─ system prompt + evidence prompt
                                        ├─ model chat (tools schema attached)
                                        ├─ allowlisted tool execution ──┐
                                        │   (private /internal/dsp-tools│
                                        │    route with shared token)   │
                                        │        ◄──────────────────────┘
                                        ├─ loop bounded: ≤ 6 steps, ≤ 8 calls
                                        └─ validate → retry once → deterministic fallback
        │
        ▼
AnalysisInsight persisted (Postgres): response_json, tool_trace_json,
citations_json, model_name, prompt_version → rendered in web UI (InsightPanel)
```

Failures are isolated by design: **if the model is down, hangs, or produces
dishonest output, the DSP results survive.** A failed or rejected insight is
persisted with a clear `error_message`, and the UI shows a deterministic brief
instead of a hallucination.

## 4. The harness: what our open-source code controls

`services/ai/` is a self-contained FastAPI service. The safety contract lives
in [[prompts.py](services/ai/app/prompts.py)] and is enforced in code, not just
asked for politely:

| Guard | Mechanism | File |
|---|---|---|
| Model can never invent a number | The model emits `{{estimate:name}}` placeholders; the **server substitutes provenance values** (`render_template`) and turns unknown names into explicit `[unknown:x]` | [validation.py](services/ai/app/validation.py) |
| Model can never run arbitrary code / URLs | Tool dispatch only accepts names in a 5-tool allowlist; arguments are validated with strict Pydantic models; execution goes exclusively to the API's private `/internal/dsp-tools/{tool}` route with a shared `INTERNAL_API_TOKEN` | [tools.py](services/ai/app/tools.py) |
| Dishonest output is rejected | `validate_insight` checks shape, citation existence, placeholder existence, and tool allowlist; invalid responses get one retry with the validator's error, then fall back to a deterministic brief that only restates stored evidence | [validation.py](services/ai/app/validation.py), [backend.py](services/ai/app/backend.py) |
| A confused model can't hog resources | `MAX_TOOL_STEPS` (6) and `MAX_TOOL_CALLS` (8) bound the loop; per-call 30 s timeout; tool results capped at 24 000 chars | [agent.py](services/ai/app/agent.py) |
| Untrusted data stays untrusted | Rule 2 of the system prompt: filenames, metadata, and recording contents are treated as data; evidence fields are JSON, and nothing from evidence is ever executed | [prompts.py](services/ai/app/prompts.py) |
| Images can't smuggle payloads | Only `data:image/png;base64` URIs accepted, per-image and total byte caps, sha256/bytes/dimensions audited into the evidence bundle | [schemas.py](services/ai/app/schemas.py) |
| Similarity is never presented as identification | Gallery neighbours may be summarised as "close to known neighbours" or "a rare-signal candidate" — never a transmitter name | [prompts.py](services/ai/app/prompts.py) |

The tool loop gives the model **actions**, not just text: with one tool call it
can trigger a real DSP job (`run_deep_analysis` with a chosen FEC, a specific
`try_demodulation` order, `try_fec`, or `search_similar_recordings` against the
user's own fingerprint gallery), read the result, and fold it into the final
brief. The full call sequence is persisted to `analysis_insights.tool_trace_json`
and visualised in the UI, so every AI action is auditable.

## 5. Public & open

* The code is published in a **public GitHub repository** under the **MIT
  license** ([./LICENSE](./LICENSE)).
* The model's weights are published on Hugging Face under **Apache 2.0**
  ([model card](https://huggingface.co/google/gemma-4-E4B-it)).
* The current model + prompt version (`2026-11-01`) are stamped onto every
  generated insight (`model_name`, `prompt_version` columns), so results stay
  reproducible and attributable.
* Implementation history and memory guidance: [docs/GEMMA4_IMPLEMENTATION_PLAN.md](docs/GEMMA4_IMPLEMENTATION_PLAN.md).

## 6. Requirements checklist

| Rule | How this project satisfies it |
|---|---|
| **Core feature: open-source/open-weight AI** | The Gemma 4 analyst powers the "Generate insight" feature of every project workspace; the AI brief is one of the three main views (Dashboard, Recordings, Workspace/Insight) |
| **Public repo, open-source license** | Public GitHub repo, MIT (`./LICENSE`) |
| **Agent skill standard** | N/A — no agent-skill package is distributed; the harness is submitted in the "open-weight LLM integration / original model harness" approach instead |
| **Model harness: original build** | `services/ai/` is an original from-scratch harness (agent loop + allowlisted tool dispatch + validation + fallback), not an adapted existing harness |
| **"Open weight" named + licensed** | Gemma 4 E4B-it, Apache 2.0, linked above |
| **SLM ≤ 10 B / LLM > 10 B classification** | E4B ≈ 4B effective parameters → submitted in the **small** language model class |

## 7. Running it

The AI analyst is opt-in so the deterministic DSP stack is never a hostage of a
model download. Default (`AI_ENABLED=false`) → everything except AI insight
runs as usual, and the `fake` backend produces validated, model-free briefs for
tests and UI work.

```bash
# 1. enable the AI sidecar + persistent weights volume
#    .env:
AI_ENABLED=true
AI_BACKEND=transformers          # real Gemma 4 weights, loaded lazily
AI_MODEL=google/gemma-4-E4B-it
AI_DEVICE=auto                   # CUDA when present, else CPU
INSTALL_TRANSFORMERS=1           # pulls torch>=2.6 / transformers>=5.10.1

# 2. boot the whole stack
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile ai up --build
```

Memory guidance and sizing: [docs/GEMMA4_IMPLEMENTATION_PLAN.md](docs/GEMMA4_IMPLEMENTATION_PLAN.md).
On AI failure the task records a `failed` insight with the reason — nothing
else in the product changes.

Tests: `cd services/ai && python -m pytest tests/ -q` (22 tests; the suite runs
against the deterministic backend so CI never downloads weights).

## 8. Files that make this up

| Path | Role |
|---|---|
| [services/ai/app/agent.py](services/ai/app/agent.py) | The model harness: message builder, bounded tool loop, retry, fallback |
| [services/ai/app/backend.py](services/ai/app/backend.py) | Backend protocol, in-process Transformers backend (lazy weights), deterministic FakeBackend |
| [services/ai/app/tools.py](services/ai/app/tools.py) | Allowlist, Pydantic argument validation, private-route dispatch, payload caps |
| [services/ai/app/prompts.py](services/ai/app/prompts.py) | The single source of truth for the honesty contract |
| [services/ai/app/validation.py](services/ai/app/validation.py) | Placeholder substitution, citation/trace validation |
| [services/api/app/tasks.py](services/api/app/tasks.py) | Evidence bundle builder + persistence (Celery) |
| [services/api/app/ai_client.py](services/api/app/ai_client.py) | Sidecar client with timeout |
| [docker-compose.yml](docker-compose.yml) | `ai` profile, weights volume, env contract |
