# DSP Fix Plan — `signalscope_dsp`

Review date: 2026-09-12 · Baseline: `pytest tests/` 20/20 pass.
Each item: fix → verify. Check off as completed.

## Bug fixes (do these)

- [x] **1. `demod_fsk` NaNs at low samples-per-symbol** — `demodulation/demod.py:137-142`
  - Cause: `guard = max(1, sps // 5)` exceeds half the symbol span when `sps <= 2`,
    so the per-symbol slice is empty and `np.mean([])` → NaN tones/decisions.
    Reproduced: `sps=2` → `has_nan=True`, all decisions 0.
  - Fix: clamp `guard = min(guard, (samples_per_symbol - 1) // 2)` (0 allowed → full-span mean).
  - Verify: synth 2-FSK probe at `sps=2` has no NaNs; `pytest tests/test_demod_and_classification.py`.

- [x] **2. Unsigned raw-IQ scales to half amplitude** — `io/raw_iq_loader.py:50-59`
  - Cause: `uint8/uint16` subtracts the midpoint (128) but divides by max (255),
    so full-scale maps to ~±0.5, while `io/wav_loader.py:18-22` maps uint8 to ±1.0.
  - Fix: divide by the midpoint after offset
    (`(raw - midpoint) / midpoint`); leave signed/float paths untouched.
  - Verify: max uint8 sample ≈ 0.99; `pytest tests/test_io.py`.

- [x] **3. Stale symbol-rate evidence string** — `modulation/symbol_rate.py:53`
  - Code uses `|diff(samples)|²` (see comment at :21-25) but evidence claims `"|signal|^2"`.
  - Fix: evidence → `"Spectral peak of |diff(signal)|^2 (cyclostationary symbol-clock feature)"`.
  - Verify: no behavior change; `pytest tests/test_demod_and_classification.py`.

- [x] **4. `detect_bursts` crashes on empty input** — `detection/burst.py:46-48`
  - `active[0]` / `active[-1]` raise `IndexError` when `samples` is empty.
  - Fix: early `return []` for empty input (and non-positive `sample_rate`).
  - Verify: `detect_bursts(np.array([], dtype=np.complex64), 1e6) == []`.

## Cleanup (no behavior change)

- [x] **5. Redundant condition** — `modulation/classifier.py:102`
  `if 2 <= n_tones <= 2:` → `if n_tones == 2:`.
- [x] **6. Misleading "Gray-coded" header + dead code** — `demodulation/demod.py:7-17`
  Header claims Gray coding but PSK/QAM use direct binary mapping (correctly noted
  inline at :63-67). Fix header, drop unused `k` in `_psk_constellation`,
  remove unreferenced `_gray_code` (verified: no other usage in repo).

## Follow-ups (all implemented 2026-09-12)

- [x] **A. M-th-power peakiness ceiling**: squash recalibrated to
  `1 - exp(-3.5 * ratio / N)` (`modulation/classifier.py`), so a pure tone
  scores ~0.9 and noise ~0.0; PSK scoring is now differential (lower-order
  peaks explain away higher-order ones — fixes the BPSK/QPSK tie); QAM-branch
  QPSK cross-check restricted to multi-ring inputs with threshold 0.5.
  Classifier test tightened to top-1 across bpsk/qpsk/8psk/2fsk/16qam/ook.
- [x] **B. QAM AGC vs generator normalization**: `demod_qam` now uses blind RMS
  gain matching (rotation-invariant, outlier-robust) instead of the
  95th-percentile; added 64-QAM demod test (SNR 35 dB, BER < 0.1).
- [x] **C. Silent truncation/zero-pad**: `block_*` and `diagonal_*` now emit
  `UserWarning` on size mismatch (`interleaving/block.py:_check_block_fit`).
- [x] **D. `diagonal_interleave` inverse**: added `diagonal_deinterleave`
  (exported). Round-trip testing exposed a latent forward bug — non-coprime
  `(offset, cols)` silently overwrites cells — now raises `ValueError` unless
  `gcd(offset, cols) == 1`.
- [x] **E. Dead pulse-shaping code**: removed `_rc_filter`/`_rrc_filter` and
  unused `rrc_beta`/`rrc_span` (verified unreferenced repo-wide).
- [x] **F. Reporting stage**: implemented `reporting/report.py`
  (`AnalysisReport`, `build_report`, numpy-safe JSON) + `tests/test_reporting.py`.
- [x] **G. Perf (numpy only, no new deps)**: FFT-based `autocorrelate_bits`
  (bit-exact vs loop) and vectorized `sliding_pattern_match`; vectorized
  Viterbi trellis step (~6x faster on 5k-bit frames, identical decoding on
  clean input, equal-or-better BER under noise). The rewrite also fixed a
  latent branch-metric quirk: summing two numpy bools saturates to bool, so a
  double-bit mismatch used to cost 1 instead of 2 (and the penalty depended on
  input dtype); the metric is now a true {0, 1, 2} Hamming distance as the
  docstring always claimed.

