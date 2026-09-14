"""Band-range coverage: the DSP chain must behave identically whether the signal
sits at a kHz-scale offset or a GHz-scale center frequency. These tests synthesize
short signals in both regimes and confirm classification + symbol-clock + FEC path
stay functional (relative-scale behavior, not absolute hold times)."""
import numpy as np

from signalscope_dsp.synth.generator import SynthConfig, generate_signal
from signalscope_dsp.modulation.classifier import classify_modulation_estimate
from signalscope_dsp.modulation.symbol_rate import symbol_clock_spectrum
from signalscope_dsp.fec.reed_solomon import reed_solomon_encode, reed_solomon_decode

# two regimes: a 40 kHz carrier ("kHz band") and a 1.25 GHz carrier ("GHz band");
# both keep samples small (<1 MB) by scaling the symbol period up in lockstep
BANDS = [
    dict(name="kHz", sample_rate_hz=200_000.0, symbol_rate_hz=10_000.0,
         carrier_offset_hz=40_000.0, n_symbols=256),
    dict(name="GHz", sample_rate_hz=5_000_000_000.0, symbol_rate_hz=10_000_000.0,
         carrier_offset_hz=1_250_000_000.0, n_symbols=256),
]


def test_classification_works_across_khz_to_ghz():
    for band in BANDS:
        cfg = SynthConfig(modulation="qpsk", snr_db=25, **{k: v for k, v in band.items() if k != "name"})
        sig = generate_signal(cfg).samples
        est = classify_modulation_estimate(sig, cfg.sample_rate_hz)
        assert est.value == "QPSK", f"{band['name']} band: classified {est.value}"


def test_symbol_clock_scale_invariant_peak():
    for band in BANDS:
        cfg = SynthConfig(modulation="qpsk", snr_db=25, **{k: v for k, v in band.items() if k != "name"})
        sig = generate_signal(cfg).samples
        info = symbol_clock_spectrum(sig, cfg.sample_rate_hz)
        # the symbol-clock line must be the dominant spectral feature in both regimes
        assert info["peak_freq"] > 0
        power = np.asarray(info["power"])
        assert np.max(power) > 5 * np.mean(power), f"{band['name']} band: no dominant clock line"


def test_fec_path_independent_of_band():
    # FEC math is scale-free; confirm it round-trips identically on both bands' payloads
    for band in BANDS:
        cfg = SynthConfig(modulation="qpsk", snr_db=25, **{k: v for k, v in band.items() if k != "name"})
        res = generate_signal(cfg)
        payload = res.bits[:44]
        coded = reed_solomon_encode(payload, 4, 15, 11)
        out = reed_solomon_decode(coded, 4, 15, 11)
        assert np.array_equal(out.decoded_bits, payload), f"{band['name']} band: RS round-trip failed"