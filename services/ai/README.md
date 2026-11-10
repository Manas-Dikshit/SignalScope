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

The Transformers path is a scaffold for Phase 0/1. The tool-calling loop and
image rendering are added in later phases of
`docs/GEMMA4_IMPLEMENTATION_PLAN.md`.

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
