from __future__ import annotations

import numpy as np

from .block import score_deinterleave_candidate


def pseudo_random_interleave(bits: np.ndarray, seed: int) -> np.ndarray:
    """Full-block pseudo-random (seeded) interleaver: reorders the whole block
    by a deterministic permutation driven by `seed`. Length-preserving; a peer
    with the same seed reproduces exactly the inverse order."""
    perm = np.random.default_rng(seed).permutation(len(bits))
    out = np.empty_like(bits)
    out[perm] = bits
    return out


def pseudo_random_deinterleave(bits: np.ndarray, seed: int) -> np.ndarray:
    """Inverse of pseudo_random_interleave for the same seed."""
    perm = np.random.default_rng(seed).permutation(len(bits))
    out = np.empty_like(bits)
    out[np.argsort(perm)] = bits  # reverse the placement applied by the interleaver
    return out


def rank_pseudo_random_candidates(bits: np.ndarray, seeds: list[int]) -> list[dict]:
    """Hypothesis search over possible interleaver seeds: de-interleave with each
    seed and rank the results by the shared transition-rate heuristic. Returns
    [{seed, score, recovered_bits}] sorted best-first. The heuristic ranks, it
    does not prove — the winning seed is a candidate, not a fact."""
    scored = []
    for s in seeds:
        recovered = pseudo_random_deinterleave(bits, s)
        scored.append({
            "seed": s,
            "score": score_deinterleave_candidate(recovered),
            "recovered_bits": recovered.tolist(),
        })
    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored