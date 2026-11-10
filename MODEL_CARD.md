# Model Card: SignalScope RF Analyst Agent (Gemma 4 E2B-it)

## 1. Model Details

- **Model Name:** SignalScope RF Analyst Agent
- **Base Foundation Model:** `google/gemma-4-E2B-it` (Google Gemma 4, 2B effective parameters, multimodal instruction-tuned)
- **Base Model License:** Apache 2.0 (Google Gemma Open Model Terms)
- **Harness & Application License:** MIT License (SignalScope AI)
- **Harness Architecture:** Token-bounded multi-step tool-calling agent with deterministic DSP grounding, multimodal visual verification, and anti-hallucination numeric placeholder substitution
- **Release Date:** November 2026
- **Repository:** [https://github.com/Manas-Dikshit/SignalScope](https://github.com/Manas-Dikshit/SignalScope)

---

## 2. Intended Use & Scope

### Primary Use Case
SignalScope RF Analyst Agent is designed to assist signals intelligence operators, researchers, and RF engineering students in triaging authorized radio-frequency (RF) signal recordings. It acts as an automated, offline reasoning partner that:
1. Ingests structured `EvidenceBundle` metadata compiled deterministically from NumPy/SciPy DSP pipelines (parameter estimates, confidence intervals, competing alternatives, warnings).
2. Reviews pre-rendered visual spectral representations (PSD, spectrogram/waterfall, constellation scatter, and M-th-power cyclostationary spectra) to perform visual cross-validation.
3. Detects inconsistencies across analysis stages (e.g., modulation hypothesis indicates QPSK, but symbol-clock line or constellation clustering is ambiguous).
4. Invokes allowlisted DSP tools to gather follow-up evidence (alternative demodulation schemes, FEC decoders, or rare-signal gallery searches).
5. Synthesizes a structured intelligence brief with citations back to raw DSP evidence.

### Out-of-Scope & Prohibited Uses
- **Decryption / Cryptanalysis:** Not intended or equipped to break, decrypt, or circumvent encrypted communications or access-controlled protocols.
- **Direction Finding / Geolocation:** Does not provide operational tactical bearings or target geolocation. Interferometric analysis is strictly limited to relative antenna baseline discrimination (sky vs. local observatory multipath).
- **Live Transmission / Electronic Warfare:** Designed strictly for post-capture analysis of stored recordings (WAV, raw I/Q, SigMF); contains no transmission, jamming, or live RF interception capabilities.
- **Unauthorized Interception:** Restricted to authorized research, educational signals, and recordings owned by or explicitly permitted to the operator.

---

## 3. Architecture & Anti-Hallucination Protocol

```text
       +-----------------------------------------------------------+
       |                  PostgreSQL 16 Database                   |
       |  (parameter_estimates, recordings, signal_fingerprints)  |
       +-----------------------------+-----------------------------+
                                     |
                                     v
                       +---------------------------+
                       | Celery Worker (DSP Core)  |
                       |  - Builds EvidenceBundle  |
                       |  - Renders Evidence PNGs  |
                       +-------------+-------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  SignalScope AI Sidecar (services/ai)                   |
|                                                                         |
|  1. Prompt Assembly:                                                    |
|     - Multimodal image tokens (PSD, Waterfall, Constellation, M-th)    |
|     - Structured EvidenceBundle JSON                                    |
|     - System prompt forbidding numeric invention                        |
|                                                                         |
|  2. Agent Tool Loop (max 6 steps, token-gated internal route):          |
|     - get_project_evidence                                              |
|     - run_deep_analysis                                                 |
|     - try_demodulation                                                  |
|     - try_fec                                                           |
|     - search_similar_recordings                                         |
|                                                                         |
|  3. Anti-Hallucination Validation Layer (services/ai/app/validation.py):|
|     - Schema Validation: Pydantic InsightResponse                       |
|     - Citation Verification: All evidence_refs must match DSP output    |
|     - Strict Placeholder Substitution: Model outputs {{estimate:name}}; |
|       the backend injects the true numeric value from DB provenance     |
|     - Provenance Tagging: Saved with source = "ai_hypothesis"           |
+------------------------------------+------------------------------------+
                                     |
                                     v
                 +---------------------------------------+
                 |       Web UI (InsightPanel.tsx)       |
                 |  "AI-Generated — Evidence is Primary" |
                 +---------------------------------------+
```

### The Strict Numeric Honesty Principle
Large Language Models are prone to hallucinating floating-point precision in technical domains. SignalScope resolves this fundamentally:
1. **Model Never Outputs Authoritative Numbers:** The model prompt strictly prohibits writing numeric values. Instead, it emits template tags such as `{{estimate:symbol_rate}}` or `{{estimate:snr_db}}`.
2. **Backend Substitution:** The API backend matches placeholders against the deterministic `EvidenceBundle` stored in PostgreSQL. If an unknown token or fabricated number is detected, validation rejects the output.
3. **Deterministic Fallback:** If the model fails validation twice, a deterministic rule-based brief derived directly from DSP evidence is emitted, ensuring zero hallucinated metrics reach the operator.

---

## 4. Input & Output Specifications

### Inputs
- **EvidenceBundle (JSON):** Recording parameters (sample rate, center frequency, duration), occupied bandwidth, SNR, spectral flatness, ranked modulation candidates, symbol rate candidates, and FEC verdicts.
- **Evidence Images (PNG data URIs):**
  - Spectrogram / Waterfall (time-frequency distribution)
  - Power Spectral Density (PSD with 99% bandwidth containment)
  - Constellation Diagram (I/Q scatter with symbol center sampling)
  - M-th Power Spectra (2nd, 4th, and 8th-power cyclostationary peaks)
  - *Hard Limit:* Max 300 KB per image; max 1 MB total image payload.
  - *Non-Goal:* Raw complex I/Q is never ingested by the neural network.

### Outputs
- **Structured JSON (`InsightResponse`):**
  - `summary_template`: Cited text with parameter placeholders.
  - `hypothesis`: Modulation label, agreement score with DSP, confidence note.
  - `conflicts`: Discrepancies between spectral features and candidate modulation.
  - `anomalies`: Unexpected frequency drift, spurious bursts, or SNR drops.
  - `recommended_actions`: Concrete follow-up DSP recommendations (e.g. `try_fec` with LDPC).
  - `unknowns`: Explicit statement of unresolvable ambiguities ("Unknown" is a valid and valued answer).
  - `limitations`: Contextual constraints and reminders that output is an AI hypothesis.
  - `citations`: Direct pointer to database provenance records.
  - `tool_trace`: Complete chronological record of agent tool invocations and returned metrics.

---

## 5. Quantitative Evaluation & Verification

The harness and AI integration are verified across the automated test suite:

| Test Suite | File | Verified Invariant |
|---|---|---|
| **Agent Tool Loop** | `services/ai/tests/test_agent.py` | Low-confidence modulation triggers follow-up tool calls; execution halts at `AI_MAX_TOOL_STEPS`. |
| **Numeric Guard** | `services/ai/tests/test_agent.py` | Output with unsanctioned numeric values is rejected; valid `{{estimate:...}}` substitutions pass. |
| **Evidence Citations** | `services/ai/tests/test_agent.py` | Every cited reference must exist in the supplied `EvidenceBundle`. |
| **Image Audit & Caps** | `services/ai/tests/test_images.py` | Payloads exceeding byte limits or invalid MIME types are rejected; valid PNGs include SHA-256 and dimensions. |
| **Rare-Signal Gallery** | `services/api/tests/test_similar_signals.py` | Cosine similarity flags true spectral outliers while matching same-family modulations; empty galleries return `null`. |
| **Fallback Stability** | `services/ai/tests/test_agent.py` | AI service outage or schema mismatch yields deterministic fallback brief without breaking UI. |

---

## 6. Environmental & Computational Footprint

- **Inference Runtime:** Local edge deployment via Hugging Face Transformers (`bfloat16` / `int4`) or GGUF quantization (QAT Q4_0) via llama.cpp.
- **Hardware Requirements:**
  - Standard demo / CPU: Runs on modern laptop CPUs (~4.5 GB RAM footprint with Q4_0 GGUF).
  - Accelerated: Consumer GPU with >= 6 GB VRAM (e.g., RTX 3060/4060).
- **Zero Cloud Reliance:** Inference runs 100% locally. Zero RF data, client metadata, or recording samples leave the host machine.

---

## 7. Model Card Authors & Citation

**Authors:** SignalScope AI Team (Debashish Pradhan, Manas Ranjan Dikshit, Bibhuprasad Samal)  
**Track:** Open Innovation Track 1 (Best Use of Gemma 4) & Track 2 (Best Open-Source AI Project)  
**Date:** November 2026
