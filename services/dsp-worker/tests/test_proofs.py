"""Evidence/proof-layer helpers: M-th power spectrum, symbol-clock spectrum,
run-length histogram. These are the bundles the API attaches to estimates so the
UI can render a 'View proof' panel from real DSP internals, not duplicated math."""
import numpy as np

from signalscope_dsp.modulation.classifier import mth_power_spectrum
from signalscope_dsp.modulation.symbol_rate import symbol_clock_spectrum
from signalscope_dsp.synth.generator import SynthConfig, generate_signal
from signalscope_dsp.interleaving.block import block_interleave, run_length_histogram


def test_mth_power_spectrum_qpsk_peaks_at_order_4():
    sig = generate_signal(SynthConfig(modulation="qpsk", n_symbols=512, snr_db=30)).samples
    p2 = mth_power_spectrum(sig, 2)["peakiness"]
    p4 = mth_power_spectrum(sig, 4)["peakiness"]
    # QPSK squares to a 4th-power-distinct tone -> the 4th-power score should
    # clearly dominate the 2nd-power score (which is near-random for QPSK).
    assert p4 > 0.5
    assert p4 > p2 + 0.2
    spec = mth_power_spectrum(sig, 4)
    assert len(spec["freqs"]) == len(spec["power"])
    assert 0.0 <= max(spec["power"]) <= 1.0 + 1e-9


def test_symbol_clock_spectrum_peak_near_symbol_rate():
    cfg = SynthConfig(modulation="qpsk", sample_rate_hz=400_000.0,
                      symbol_rate_hz=25_000.0, carrier_offset_hz=0.0,
                      n_symbols=1024, snr_db=25)
    sig = generate_signal(cfg).samples
    info = symbol_clock_spectrum(sig, cfg.sample_rate_hz)
    freqs = np.asarray(info["freqs"])
    power = np.asarray(info["power"])
    assert len(power) and np.max(power) > 0
    peak = info["peak_freq"]
    assert abs(peak - 25_000.0) / 25_000.0 < 0.15, f"symbol-clock line at {peak} Hz"
    # peak power must sit well above the spectral mean for a clean signal
    assert np.max(power) > 5 * np.mean(power)


def test_run_length_histogram_structural():
    rng = np.random.default_rng(4)
    bits = rng.integers(0, 2, size=2400).astype(np.uint8)
    h = run_length_histogram(bits)
    assert len(h["run_lengths"]) == len(h["counts"])
    total_runs = int(np.sum(h["counts"]))
    # every run in `bits` is counted exactly once
    assert total_runs == int(np.sum(np.diff(bits) != 0)) + 1
    assert h["max_run"] >= 1


def test_run_length_histogram_reacts_to_interleaving():
    rng = np.random.default_rng(4)
    bits = rng.integers(0, 2, size=4800).astype(np.uint8)
    inter = block_interleave(bits, rows=40, cols=120)
    h0, h1 = run_length_histogram(bits), run_length_histogram(inter)
    # block interleaving (40-deep) must diffuse the longest natural runs
    assert h1["max_run"] < h0["max_run"], "interleave should break up long runs"