# SignalScope AI — Research References

Curated references actually used or directly relevant to this project's
implementation. Grouped by area; kept to what's necessary, not exhaustive.

## File formats & data
- **SigMF (Signal Metadata Format) specification** — the sidecar-metadata
  format this project's `load_sigmf` implements.
  https://github.com/sigmf/SigMF
- **NTIA SigMF namespace extension** (reference for how real-world agencies
  extend SigMF with sensor/measurement metadata).
  https://github.com/NTIA/sigmf-ns-ntia
- **WAV/RIFF format reference** (used by `load_wav`).
  http://soundfile.sapp.org/doc/WaveFormat/

## Modulation & demodulation theory
- **GNU Radio project** — reference implementation for constellation
  receiver (Costas loop), quadrature demod, and the FEC API this project's
  demod/FEC design deliberately parallels.
  https://www.gnuradio.org/
- **GNU Radio FEC API docs** (Viterbi, async/general FEC block structure).
  https://wiki.gnuradio.org/index.php/FEC
- **Cyclostationary feature detection for modulation/symbol-rate
  estimation** (background for the `|diff(samples)|²` spectral-line method
  used in `estimate_symbol_rate_candidates`).
  https://en.wikipedia.org/wiki/Cyclostationary_process
- **Digital Modulation Classification survey** (background for the
  handcrafted-feature classifier approach — envelope variance, M-th-power
  method for PSK order, constellation ring counting for QAM).
  https://en.wikipedia.org/wiki/Automatic_modulation_classification

## Error-correction coding (FEC)
- **CCSDS 131.0-B TM Synchronization and Channel Coding (Blue Book)** —
  defines the rate-1/2, K=7, generator-polynomial (171,133)₈ convolutional
  code used as this project's default; also the standard reference for
  Reed-Solomon and concatenated-code parameters in the next FEC phase.
  https://public.ccsds.org/Pubs/131x0b5.pdf
- **Viterbi algorithm** (background for `viterbi_decode`).
  https://en.wikipedia.org/wiki/Viterbi_algorithm
- **Reed–Solomon codes** (reference for the planned RS decoder).
  https://en.wikipedia.org/wiki/Reed%E2%80%93Solomon_error_correction
- **Low-Density Parity-Check codes (Gallager codes)** (reference for the
  planned LDPC decoder).
  https://en.wikipedia.org/wiki/Low-density_parity-check_code
- **CRC (cyclic redundancy check)** — CRC-16/CCITT as used in
  `crc16_ccitt`.
  https://en.wikipedia.org/wiki/Cyclic_redundancy_check

## Interleaving
- **Forney/Ramsey convolutional interleaver** (reference design for
  `convolutional_interleave`/`deinterleave`).
  https://en.wikipedia.org/wiki/Burst_error-correcting_code#Interleaving

## Core scientific/DSP libraries
- **NumPy** — https://numpy.org/doc/stable/
- **SciPy Signal processing** (`scipy.signal.welch`, `spectrogram`,
  `butter`/`sosfiltfilt` — used throughout `preprocessing/` and
  `features/`). https://docs.scipy.org/doc/scipy/reference/signal.html
- **SciPy WAV I/O** (`scipy.io.wavfile`, used by `load_wav`).
  https://docs.scipy.org/doc/scipy/reference/io.html#module-scipy.io.wavfile

## Application stack
- **Streamlit docs** (current prototype UI). https://docs.streamlit.io/
- **Plotly.js / Python** (all charts). https://plotly.com/python/
- **FastAPI** (Phase 2+ backend). https://fastapi.tiangolo.com/
- **SQLAlchemy 2.0** (ORM/persistence). https://docs.sqlalchemy.org/en/20/
- **Alembic** (DB migrations). https://alembic.sqlalchemy.org/en/latest/
- **Next.js App Router** (frontend). https://nextjs.org/docs
- **shadcn/ui** (component base). https://ui.shadcn.com/

## Design references (UI phases)
- **awesome-design-md** — brand design-system writeups used as reference
  for the visual/UI phases.
  https://github.com/VoltAgent/awesome-design-md
  - ElevenLabs entry (cinematic, waveform-motif reference):
    `design-md/elevenlabs/DESIGN.md` in the repo above.
  - Together AI entry (technical/blueprint reference):
    `design-md/together-ai/DESIGN.md` in the repo above.

## Problem statement
- Original SIH problem statement (RF signal parameter extraction,
  demodulation, de-interleaving, FEC, bit-stream correlation) — kept here
  as the canonical source of truth for `docs/REQUIREMENTS_TRACEABILITY.md`.
  *(pasted directly into project chat/docs — no public URL)*