# SignalScope AI — Lean MVP

An offline, explainable RF signal-analysis workbench for **authorized** `.iq`,
`.wav`, and SigMF recordings. This is the lean, dependency-light slice of the
full production spec: a real Python DSP core plus a Streamlit UI, no
Docker / Postgres / Redis / Celery required.

**Scope reminder:** offline file analysis only. No live RF capture, no
geolocation, no decryption of protected communications.

## What's implemented

- **File import** — WAV (mono/stereo→I/Q, all common PCM/float widths), raw IQ
  (int8/uint8/int16/uint16/int32/float32/float64, interleaved or separate I/Q,
  either endianness), and SigMF (`.sigmf-meta` + `.sigmf-data`).
- **Provenance-tracked metadata** — every reported value (sample rate, center
  frequency, modulation, symbol rate, SNR, ...) carries a `source`
  (`metadata` / `user_supplied` / `measured` / `estimated` / `hypothesis` /
  `unknown`) and, where relevant, a confidence score and evidence. Nothing
  is ever shown as exact when it isn't.
- **Visualization** — time waveform, PSD, waterfall/spectrogram, I/Q scatter,
  decided constellation.
- **Burst detection** — adaptive-threshold energy detector with
  duration/repetition/duty-cycle stats.
- **Feature extraction** — occupied bandwidth, SNR, spectral centroid/flatness,
  crest factor, zero-crossing rate.
- **Modulation classification** — explainable, feature-based (envelope
  variance, M-th-power spectral peakiness for PSK order, tone/ring clustering
  for FSK/QAM), returns top-3 hypotheses with evidence.
- **Symbol-rate estimation** — cyclostationary candidate search, returns
  multiple candidates when evidence is ambiguous.
- **Demodulation** — BPSK/QPSK/8-PSK, 16/64-QAM, 2/4-FSK. Hard bits + a crude
  soft-decision margin, decided-constellation output.
- **De-interleaving** — block, convolutional, diagonal (block/convolutional
  wired into the UI; diagonal available in the library).
- **FEC** — rate-1/2 convolutional encode + hard-decision Viterbi decode
  (configurable constraint length), CRC-16 validation, sync-word search.
- **Bit-stream correlation** — autocorrelation, sliding pattern match with
  Hamming tolerance, repeated-sequence/header detection.
- **Synthetic signal generator** — built-in demo-data generator so the whole
  pipeline is testable with zero external datasets; the UI's "Generate
  synthetic demo signal" mode uses it directly and shows ground truth so you
  can sanity-check BER end to end.
- **Report export** — JSON report with provenance-tagged parameters.

## Known limitations (intentional, for an MVP)

- Demodulators sample symbol centers directly; there's no closed-loop
  Costas/PLL carrier recovery or Gardner/M&M timing recovery loop yet. Works
  well on the synthetic generator (which lets you dial in/remove a known
  carrier offset) and on real captures with a clean, near-baseband, near-zero
  residual carrier. A real off-air capture with drifting carrier/timing will
  need those loops added — that's the natural next increment.
- The synthetic generator uses rectangular (NRZ) pulse shaping rather than a
  band-limited RRC pulse, specifically so the receiver's naive symbol-center
  sampling is exactly ISI-free without needing a matched filter yet.
- FEC support is rate-1/2 convolutional/Viterbi only (hard-decision). Reed-
  Solomon, LDPC, and soft-decision (LLR) decoding are in the full spec but not
  in this MVP.
- No auth, no database, no job queue, no Docker — single-process, in-memory,
  local use only.

## Running it

```bash
pip install -r requirements.txt
PYTHONPATH=. streamlit run app.py
```

Then open the URL Streamlit prints (default `http://localhost:8501`).

## Running the tests

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -v
```

20 tests cover file I/O (WAV/raw-IQ/SigMF), the convolutional encode/Viterbi
decode round trip (including error correction), CRC, block/convolutional
de-interleaving round trips, bit correlation, and end-to-end
generate→demodulate BER checks for BPSK/QPSK/16-QAM/2-FSK plus modulation
classification and symbol-rate estimation.

## Layout

```
signalscope_dsp/     # the DSP core — usable standalone, no Streamlit/UI dependency
  common.py           # Estimate/Source/Recording — the provenance model everything else uses
  io/                 # wav_loader, raw_iq_loader, sigmf_loader
  preprocessing/       # DC removal, normalization, IQ imbalance, filtering
  features/            # PSD, waterfall, spectral features
  detection/            # burst detector
  modulation/            # classifier, symbol-rate estimator
  demodulation/           # PSK/QAM/FSK demodulators
  interleaving/            # block/convolutional/diagonal (de)interleavers
  fec/                      # convolutional encode/Viterbi decode, CRC, sync search
  correlation/               # autocorrelation, pattern match, repeated-sequence search
  synth/                      # synthetic signal generator (demo data + test fixtures)
app.py                # Streamlit UI
tests/                 # pytest suite (20 tests)
```

## Where this goes next

This MVP intentionally skips the production-hardening items from the full
spec (Postgres persistence, auth, Celery workers, Docker Compose, GNU Radio
integration, neural modulation classifier, LDPC/Reed-Solomon, closed-loop
carrier/timing recovery, multi-user job queue, full documentation set). The
DSP core is written with clean module boundaries specifically so those can be
layered on without a rewrite — e.g. a FastAPI service can wrap
`signalscope_dsp` directly, and a Celery worker can call the same functions
this Streamlit app calls today.
