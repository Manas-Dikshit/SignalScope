# SignalScope AI sidecar

Optional local Gemma 4 service for the SignalScope analyst brief.

## Run with the fake backend (no model download)

```bash
cd services/ai
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

`GET /health` -> `{"status":"ok","backend":"fake",...}`

## Run with a local Gemma 4 model

Install the optional runtime on the GPU host:

```bash
python -m pip install -r requirements.txt -r requirements-transformers.txt
```

Then:

```bash
AI_BACKEND=transformers \
AI_MODEL=google/gemma-4-E4B-it \
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

The Transformers path loads the model lazily, so API/worker processes and tests
never import torch unless `AI_BACKEND=transformers` is selected.

## Phase 3 multimodal evidence

The API worker renders four small PNGs from the bounded project window:
PSD, waterfall, constellation, and M-th power spectrum. They are sent as
`data:image/png;base64,...` URIs, never as raw IQ. Each image is capped by
`AI_MAX_IMAGE_BYTES` (default 300 KB), the bundle by
`AI_MAX_TOTAL_IMAGE_BYTES` (default 1 MB), and the evidence bundle carries an
`evidence_images` audit record with `mime`, `bytes`, `sha256`, width, and height.
The sidecar rejects any image value that is not an allowed image data URI.

Images are placed before the text prompt so Gemma treats them as a visual
second opinion; the numeric evidence remains authoritative. The FakeBackend
records the visual review in the hypothesis note and limitations so the path is
visible without downloading weights.

## Model

`AI_MODEL` defaults to `google/gemma-4-E4B-it` (Apache 2.0). E2B/E4B accept
text, image, and audio; the 26B/31B variants are text+image only. See
`docs/GEMMA4_IMPLEMENTATION_PLAN.md` for memory guidance. The deterministic
`FakeBackend` is the default for tests and offline demos.

## Phase 2 tool loop

The analyst may call four allowlisted DSP tools:

| Tool | Purpose |
|---|---|
| `get_project_evidence` | Re-read stored estimates and recording metadata |
| `run_deep_analysis` | Re-run PSD/features/modulation/demod/FEC over the ROI |
| `try_demodulation` | Try a specific PSK/QAM/FSK order |
| `try_fec` | Try a specific FEC decoder and report convergence/CRC |

Tool calls are bounded by `AI_MAX_TOOL_STEPS` (default 6) and per-call
`AI_TOOL_TIMEOUT_SECONDS` (default 30). Dispatch only POSTs to the API's private
`/internal/dsp-tools/{tool_name}` route with `X-Internal-Token`; the model can
never choose a URL or execute code.

Set the same `INTERNAL_API_TOKEN` on the `api` and `ai` services. An empty token
disables the private route. Tool results are persisted in
`analysis_insights.tool_trace_json` and rendered by `InsightPanel`.

## Contract

`POST /v1/insight`

```json
{
  "project_id": "uuid",
  "prompt_version": "2026-11-01",
  "evidence": { "estimates": [] },
  "images": {}
}
```

The response is validated before it leaves the service. Numeric values are never
written by the model; `summary_template` uses `{{estimate:name}}` placeholders and
the server substitutes provenance values.
