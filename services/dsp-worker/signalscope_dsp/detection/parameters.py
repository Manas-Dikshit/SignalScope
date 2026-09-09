from __future__ import annotations

from typing import Any

import numpy as np

from ..common import Estimate, Source
from ..fec.convolutional import viterbi_decode
from ..fec.reed_solomon import _poly_eval, _EXP
from ..interleaving import (
    block_deinterleave,
    convolutional_deinterleave,
    diagonal_deinterleave,
    pseudo_random_deinterleave,
    score_deinterleave_candidate,
)


def identify_fec(bits: np.ndarray) -> Estimate:
    """Rank recognizable FEC families without claiming certainty."""
    bits = np.asarray(bits, dtype=np.uint8) & 1
    candidates: list[Estimate] = []
    if len(bits) >= 32 and len(bits) % 2 == 0:
        result = viterbi_decode(bits)
        normalized = result.path_metric / max(len(bits) // 2, 1)
        candidates.append(Estimate(
            "fec", "convolutional", source=Source.HYPOTHESIS,
            confidence=float(np.clip(1.0 - normalized, 0.0, 0.95)),
            evidence=[f"Rate-1/2 K=7 Viterbi path metric={result.path_metric:.0f}."],
        ))
    if len(bits) >= 8 and len(bits) % 8 == 0:
        data = np.packbits(bits).tobytes()
        rs_score = 0
        for parity in (8, 16, 32):
            for start in range(0, len(data) - parity + 1, parity):
                block = list(data[start:start + parity])
                if len(block) > parity and all(_poly_eval(block, int(_EXP[i])) == 0 for i in range(parity)):
                    rs_score += 1
        if rs_score:
            candidates.append(Estimate(
                "fec", "reed-solomon", source=Source.HYPOTHESIS,
                confidence=float(min(0.9, 0.45 + rs_score * 0.1)),
                evidence=[f"{rs_score} byte-aligned RS syndrome checks passed."],
            ))
    if not candidates:
        return Estimate("fec", None, Source.UNKNOWN, warnings=["No supported FEC family had sufficient evidence."])
    candidates.sort(key=lambda item: item.confidence or 0, reverse=True)
    best = candidates[0]
    best.alternatives = candidates[1:]
    return best


def identify_interleaving(bits: np.ndarray) -> dict[str, Any]:
    """Rank common de-interleaving hypotheses using the existing validation score."""
    bits = np.asarray(bits, dtype=np.uint8) & 1
    candidates: list[tuple[str, np.ndarray]] = [("none", bits)]
    if len(bits) >= 64:
        candidates.extend([
            ("block", block_deinterleave(bits, 8, 8)),
            ("diagonal", diagonal_deinterleave(bits, 8, 8)),
            ("convolutional", convolutional_deinterleave(bits, 4, 3)),
        ])
    if len(bits) >= 32:
        candidates.append(("pseudo_random", pseudo_random_deinterleave(bits, seed=0)))
    ranked = sorted(
        ((name, score_deinterleave_candidate(candidate), candidate) for name, candidate in candidates),
        key=lambda item: item[1],
        reverse=True,
    )
    name, score, recovered = ranked[0]
    return {
        "best_attempt": name,
        "validation_score": round(float(score), 3),
        "recovered_preview": "".join(str(int(bit)) for bit in recovered[:64]),
        "candidates": [{"name": n, "score": round(float(s), 3)} for n, s, _ in ranked],
    }
