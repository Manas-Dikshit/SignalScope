import numpy as np
import pytest

from signalscope_dsp.fec.reed_solomon import (
    reed_solomon_encode,
    reed_solomon_decode,
)

rng = np.random.default_rng(42)


def _message(m, k):
    return rng.integers(0, 2, size=k * m).astype(np.uint8)


def _inject_symbol_errors(bits, m, n_syms, position_map):
    out = bits.copy()
    for sym_idx in position_map:
        for b in range(m):
            out[sym_idx * m + b] ^= 1
    return out


def _position(rng, n):
    return sorted(rng.choice(n, size=n, replace=False))


def test_rs_round_trip_noise_free():
    for m, k in ((4, 11), (4, 7), (8, 223), (8, 239), (5, 21)):
        n = (1 << m) - 1
        if n - k < 2 or (n - k) % 2 != 0:
            continue
        msg = _message(m, k)
        coded = reed_solomon_encode(msg, m, n, k)
        result = reed_solomon_decode(coded, m, n, k)
        assert result.syndrome_zero
        assert result.corrected_symbols == 0
        assert np.array_equal(msg, result.decoded_bits)


def test_rs_corrects_errors_within_capacity():
    m, k = 4, 11  # n=15, t=(15-11)/2=2 -> 2 symbol errors correctable
    n = (1 << m) - 1
    msg = _message(m, k)
    coded = reed_solomon_encode(msg, m, n, k)
    bad = _inject_symbol_errors(coded, m, n, _position(rng, 2))
    result = reed_solomon_decode(bad, m, n, k)
    assert result.syndrome_zero
    assert result.corrected_symbols == 2
    assert result.confidence > 0
    assert np.array_equal(msg, result.decoded_bits)


def test_rs_corrects_erasures_only():
    m, k = 4, 11  # up to 4 erasures correctable
    n = (1 << m) - 1
    msg = _message(m, k)
    coded = reed_solomon_encode(msg, m, n, k)
    erasures = _position(rng, 4)
    bad = _inject_symbol_errors(coded, m, n, erasures)
    result = reed_solomon_decode(bad, m, n, k, erasures=erasures)
    assert result.syndrome_zero
    assert result.corrected_symbols == 4
    assert result.corrected_erasures == 4
    assert np.array_equal(msg, result.decoded_bits)


def test_rs_corrects_errors_and_erasures_mixed():
    m, k = 4, 11  # 2e + f <= 4
    n = (1 << m) - 1
    msg = _message(m, k)
    coded = reed_solomon_encode(msg, m, n, k)
    erasures = _position(rng, 2)
    bad = _inject_symbol_errors(coded, m, n, erasures)
    errs = [i for i in range(n) if i not in erasures][:0]  # tack error onto one non-erased symbol
    err_idx = rng.choice([i for i in range(n) if i not in erasures], size=1, replace=False)
    bad = _inject_symbol_errors(coded, m, n, err_idx)
    result = reed_solomon_decode(bad, m, n, k, erasures=erasures)
    assert result.syndrome_zero
    assert result.corrected_symbols == 3
    assert result.corrected_erasures == 2
    assert np.array_equal(msg, result.decoded_bits)


def test_rs_over_capacity_reports_failure_not_silent_success():
    m, k = 4, 11  # t=2
    n = (1 << m) - 1
    msg = _message(m, k)
    coded = reed_solomon_encode(msg, m, n, k)
    bad = _inject_symbol_errors(coded, m, n, _position(rng, 5))  # 5 > t
    result = reed_solomon_decode(bad, m, n, k)
    # either genuinely fails syndrome, or (barely possible) lands on a wrong
    # codeword at distance > t — never report high confidence silently
    assert result.confidence == 0.0 or result.syndrome_zero is False


def test_rs_false_success_check_on_garbage():
    """Random garbage must not decode to anything a downstream stage would trust."""
    m, k = 4, 11
    n = (1 << m) - 1
    garbage = rng.integers(0, 2, size=n * m).astype(np.uint8)
    result = reed_solomon_decode(garbage, m, n, k)
    # a random n-symbol frame is almost certainly nowhere near a codeword, so
    # the decoder must spend its full erasure budget (=> confidence 0) rather
    # than report a confident success
    assert result.confidence < 0.5
    assert result.corrected_symbols <= (n - k)


def test_rs_invalid_parameters():
    with pytest.raises(ValueError, match="invalid RS block"):
        reed_solomon_encode(rng.integers(0, 2, size=16).astype(np.uint8), 4, 15, 14)
    with pytest.raises(ValueError, match="n < 2"):
        reed_solomon_encode(rng.integers(0, 2, size=16).astype(np.uint8), 4, 20, 14)
    with pytest.raises(ValueError, match="GF"):
        reed_solomon_encode(rng.integers(0, 2, size=16).astype(np.uint8), 12, 15, 7)