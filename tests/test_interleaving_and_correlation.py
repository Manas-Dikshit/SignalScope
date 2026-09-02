import numpy as np

from signalscope_dsp.interleaving.block import (
    block_interleave, block_deinterleave, convolutional_interleave, convolutional_deinterleave,
)
from signalscope_dsp.correlation.correlate import sliding_pattern_match, find_repeated_sequences


def test_block_interleave_round_trip():
    rng = np.random.default_rng(0)
    bits = rng.integers(0, 2, size=64).astype(np.uint8)
    interleaved = block_interleave(bits, rows=8, cols=8)
    recovered = block_deinterleave(interleaved, rows=8, cols=8)
    assert np.array_equal(bits, recovered)


def test_convolutional_interleave_round_trip():
    rng = np.random.default_rng(1)
    bits = rng.integers(0, 2, size=200).astype(np.uint8)
    interleaved = convolutional_interleave(bits, n_branches=4, delay_step=3)
    recovered = convolutional_deinterleave(interleaved, n_branches=4, delay_step=3)
    # End-to-end pipeline delay: each branch only sees every n_branches-th sample,
    # so a branch-local delay of (n_branches-1)*delay_step becomes that many times
    # n_branches in absolute stream position.
    delay = (4 - 1) * 3 * 4
    n = len(bits) - delay
    assert np.array_equal(bits[:n], recovered[delay:delay + n])


def test_sliding_pattern_match_finds_known_offset():
    rng = np.random.default_rng(2)
    bits = rng.integers(0, 2, size=100).astype(np.uint8)
    pattern = np.array([1, 0, 1, 1, 0, 0, 1, 0], dtype=np.uint8)
    bits[40:48] = pattern
    matches = sliding_pattern_match(bits, pattern, tolerance_bits=0)
    offsets = [m.offset for m in matches]
    assert 40 in offsets


def test_find_repeated_sequences_detects_header():
    header = np.array([1, 1, 0, 1, 0, 0, 1, 0], dtype=np.uint8)
    rng = np.random.default_rng(3)
    payload = rng.integers(0, 2, size=20).astype(np.uint8)
    bits = np.concatenate([header, payload, header, payload, header])
    results = find_repeated_sequences(bits, seq_length=8, min_repeats=3)
    assert results, "expected at least one repeated pattern"
    assert results[0]["repeat_count"] >= 3
