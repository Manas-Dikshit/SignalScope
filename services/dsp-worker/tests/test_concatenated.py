"""Concatenated codec tests: nested encode, residual-error correction, honesty."""
import numpy as np

from signalscope_dsp.fec.concatenated import concatenated_encode, concatenated_decode


RS_M, RS_K = 4, 11  # RS block (15,11) at n=15; message 44 bits -> 60 RS bits -> 120 coded bits
MSG_BITS = 44


def _message(seed: int = 3) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 2, size=MSG_BITS).astype(np.uint8)


def _flip(bits: np.ndarray, n_flips: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pos = rng.choice(len(bits), size=n_flips, replace=False)
    bad = bits.copy()
    bad[pos] ^= 1
    return bad


def test_concatenated_round_trip_noise_free():
    msg = _message()
    coded = concatenated_encode(msg)
    result = concatenated_decode(coded)
    assert result.stage_failed is None
    assert np.array_equal(result.decoded_bits[:MSG_BITS], msg)
    assert result.reed_solomon is not None and result.reed_solomon.syndrome_zero
    assert result.confidence > 0


def test_concatenated_absorbs_burst_with_outer_rs():
    # residual errors that survive the inner Viterbi must be cleaned by outer RS
    msg = _message()
    coded = concatenated_encode(msg)
    for flips in (2, 4, 8):
        bad = _flip(coded, flips, seed=8)
        result = concatenated_decode(bad)
        assert result.stage_failed is None, result.warnings
        assert np.array_equal(result.decoded_bits[:MSG_BITS], msg)
        assert result.confidence > 0


def test_concatenated_reports_stage_failure_honestly():
    # well past the combined capability: must fail loudly, never fake success
    msg = _message()
    coded = concatenated_encode(msg)
    bad = _flip(coded, 70, seed=11)
    result = concatenated_decode(bad)
    assert result.stage_failed is not None
    assert not result.reed_solomon.syndrome_zero
    assert result.confidence == 0.0
    assert result.stage_failed == "reed_solomon"


def test_concatenated_crc_valid_counts_are_checked_but_zero_for_raw_messages():
    msg = _message()
    coded = concatenated_encode(msg)
    result = concatenated_decode(coded)
    # random messages are not CRC-framed, so the recovered frame must NOT claim
    # a tampered-but-passing frame as CRC-valid
    assert result.crc_valid_count == 0