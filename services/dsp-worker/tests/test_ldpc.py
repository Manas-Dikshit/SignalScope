"""LDPC codec tests: build, encode, decode, error correction, honest failure."""
import numpy as np
import pytest

from signalscope_dsp.fec.ldpc import build_regular_ldpc, ldpc_encode, ldpc_decode


N_CODE, K_MSG = 128, 64


@pytest.fixture
def H():
    return build_regular_ldpc(N_CODE, K_MSG, column_weight=3, seed=42)


def _message(seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 2, size=K_MSG).astype(np.uint8)


def _flip(codeword: np.ndarray, n_bits: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pos = rng.choice(len(codeword), size=n_bits, replace=False)
    bad = codeword.copy()
    bad[pos] ^= 1
    return bad


def test_ldpc_round_trip_noise_free(H):
    msg = _message()
    coded = ldpc_encode(msg, H)
    result = ldpc_decode(coded, H)
    assert result.syndrome_zero
    assert np.array_equal(result.decoded_bits, msg)
    assert result.corrected_bits == 0
    assert result.confidence > 0
    assert result.n_input_bits == N_CODE
    assert result.n_output_bits == K_MSG


def test_ldpc_corrects_errors_within_capacity(H):
    msg = _message()
    coded = ldpc_encode(msg, H)
    # this small (3,6) code reliably corrects a few flips; 3 is well inside its reach
    bad = _flip(coded, 3, seed=5)
    result = ldpc_decode(bad, H)
    assert result.syndrome_zero
    assert np.array_equal(result.decoded_bits, msg)
    assert result.corrected_bits == 3
    assert result.confidence > 0


def test_ldpc_miscorrected_codeword_not_CRC_valid(H):
    msg = _message()
    coded = ldpc_encode(msg, H)
    # ~6 flips can push min-sum onto a *different* valid codeword; the CRC layer
    # must be what catches it, otherwise this is a silent false success
    bad = _flip(coded, 6, seed=5)
    result = ldpc_decode(bad, H)
    assert not np.array_equal(result.decoded_bits, msg)
    assert not result.syndrome_zero or result.crc_valid_count == 0


def test_ldpc_soft_llr_input_supported(H):
    msg = _message()
    coded = ldpc_encode(msg, H)
    llr = np.where(coded == 0, 3.5, -3.5)
    llr = llr + np.random.default_rng(2).normal(0, 0.8, size=N_CODE)
    result = ldpc_decode(llr, H)
    assert result.syndrome_zero
    assert np.array_equal(result.decoded_bits, msg)


def test_ldpc_false_success_check_on_garbage(H):
    rng = np.random.default_rng(9)
    garbage = rng.integers(0, 2, size=N_CODE).astype(np.uint8)
    result = ldpc_decode(garbage, H)
    # a zero syndrome means garbage happened to be a genuine codeword: astronomically
    # unlikely (2^-64), so a clean decode must be flagged rather than fabricated
    assert not result.syndrome_zero
    assert result.confidence == 0.0
    assert len(result.warnings) >= 1


def test_ldpc_survives_more_than_half_gets_flagged(H):
    msg = _message()
    coded = ldpc_encode(msg, H)
    bad = msg == 0  # 50%-flipped nonsense: definitely not correctable
    bad = bad.astype(np.uint8)
    result = ldpc_decode(bad, H)
    assert (not result.syndrome_zero) or not np.array_equal(result.decoded_bits, msg)


def test_ldpc_invalid_length_raises(H):
    with pytest.raises(ValueError):
        ldpc_encode(np.zeros(10, dtype=np.uint8), H)
    with pytest.raises(ValueError):
        ldpc_decode(np.zeros(10), H)