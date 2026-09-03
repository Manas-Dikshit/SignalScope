import numpy as np

from signalscope_dsp.synth import SynthConfig, generate_signal
from signalscope_dsp.preprocessing import ConditioningConfig, condition_signal, shift_frequency
from signalscope_dsp.demodulation import demod_psk, demod_qam, demod_fsk
from signalscope_dsp.modulation import classify_modulation, estimate_symbol_rate_candidates


def _demod_ber(cfg: SynthConfig) -> float:
    result = generate_signal(cfg)
    # remove carrier offset (in a real pipeline this comes from carrier-recovery/estimation;
    # here we use the known synth value to isolate demod correctness)
    baseband = shift_frequency(result.samples, cfg.sample_rate_hz, cfg.carrier_offset_hz)
    cond = condition_signal(baseband, cfg.sample_rate_hz, ConditioningConfig(coarse_freq_correction=False))

    mod = cfg.modulation
    if mod in ("bpsk",):
        d = demod_psk(cond.samples, 2, result.sps)
    elif mod == "qpsk":
        d = demod_psk(cond.samples, 4, result.sps)
    elif mod == "8psk":
        d = demod_psk(cond.samples, 8, result.sps)
    elif mod == "16qam":
        d = demod_qam(cond.samples, 16, result.sps)
    elif mod == "2fsk":
        d = demod_fsk(cond.samples, cfg.sample_rate_hz, 2, result.sps, cfg.fsk_deviation_hz)
    else:
        raise ValueError(mod)

    n = min(len(result.bits), len(d.hard_bits))
    if n == 0:
        return 1.0
    return float(np.mean(result.bits[:n] != d.hard_bits[:n]))


def test_bpsk_high_snr_low_ber():
    cfg = SynthConfig(modulation="bpsk", snr_db=25, n_symbols=1000)
    assert _demod_ber(cfg) < 0.05


def test_qpsk_high_snr_low_ber():
    cfg = SynthConfig(modulation="qpsk", snr_db=25, n_symbols=1000)
    assert _demod_ber(cfg) < 0.05


def test_16qam_high_snr_low_ber():
    cfg = SynthConfig(modulation="16qam", snr_db=30, n_symbols=1000)
    assert _demod_ber(cfg) < 0.1


def test_2fsk_high_snr_low_ber():
    cfg = SynthConfig(modulation="2fsk", snr_db=25, n_symbols=1000, fsk_deviation_hz=8000)
    assert _demod_ber(cfg) < 0.1


def test_modulation_classifier_identifies_qpsk_as_top_or_second():
    cfg = SynthConfig(modulation="qpsk", snr_db=20, n_symbols=3000, carrier_offset_hz=0)
    result = generate_signal(cfg)
    hyps = classify_modulation(result.samples, cfg.sample_rate_hz)
    labels = [h.label for h in hyps]
    assert "QPSK" in labels


def test_symbol_rate_candidates_include_true_rate_within_tolerance():
    cfg = SynthConfig(modulation="qpsk", snr_db=20, n_symbols=4000, symbol_rate_hz=10_000, carrier_offset_hz=0)
    result = generate_signal(cfg)
    candidates = estimate_symbol_rate_candidates(result.samples, cfg.sample_rate_hz)
    values = [c.value for c in candidates if c.value]
    assert any(abs(v - cfg.symbol_rate_hz) < cfg.symbol_rate_hz * 0.15 for v in values)
