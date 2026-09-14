"""Pseudo-random interleaver tests: invertibility, seed sensitivity, candidate search."""
import numpy as np

from signalscope_dsp.interleaving.pseudo_random import (
    pseudo_random_interleave, pseudo_random_deinterleave, rank_pseudo_random_candidates,
)


def _bits(n: int, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 2, size=n).astype(np.uint8)


def test_pseudo_random_round_trip_invertible():
    for n in (16, 32, 100, 255):
        bits = _bits(n)
        inter = pseudo_random_interleave(bits, seed=7)
        back = pseudo_random_deinterleave(inter, seed=7)
        assert np.array_equal(bits, back)


def test_pseudo_random_permutes_always():
    # deterministic mapping must never be the identity for a non-trivial length
    bits = _bits(64)
    inter = pseudo_random_interleave(bits, seed=7)
    assert not np.array_equal(bits, inter)


def test_pseudo_random_seed_sensitive():
    bits = _bits(64)
    a = pseudo_random_interleave(bits, seed=1)
    b = pseudo_random_interleave(bits, seed=2)
    assert not np.array_equal(a, b)


def test_rank_candidates_finds_true_seed():
    bits = _bits(128, seed=3)
    true_seed = 5
    inter = pseudo_random_interleave(bits, seed=true_seed)
    seeds = [2, 3, 4, 5, 6, 7]
    ranked = rank_pseudo_random_candidates(inter, seeds)
    best = ranked[0]
    recovered = np.asarray(best["recovered_bits"])
    assert best["seed"] == true_seed
    assert np.array_equal(recovered, bits)
    assert best["score"] >= max(d["score"] for d in ranked) - 1e-9