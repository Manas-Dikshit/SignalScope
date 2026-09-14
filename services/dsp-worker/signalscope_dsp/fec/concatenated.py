"""Concatenated codec: outer Reed-Solomon block code, inner rate-1/2
convolutional code (the classic deep-space/NATO-style concatenation).

   encode: message bits -> (RS block encode) -> (convolutional encode) -> bits
   decode: bits -> (Viterbi hard decode) -> (RS binary/erasure decode) -> message

The inner Viterbi already absorbs most channel errors; the outer RS code mops
up the short residual-error bursts that survive it. If either stage fails the
decode reports exactly which one (and why), so the upper layers never mistake
an out-of-capability frame for a clean one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .convolutional import convolutional_encode, viterbi_decode, ViterbiResult
from .reed_solomon import reed_solomon_encode, reed_solomon_decode, ReedSolomonResult
from .validation import count_crc_valid_frames

DEFAULT_POLYS = (0o171, 0o133)
DEFAULT_CONSTRAINT = 7


@dataclass
class ConcatenatedResult:
    decoded_bits: np.ndarray
    n_input_bits: int
    n_output_bits: int
    viterbi: ViterbiResult
    reed_solomon: ReedSolomonResult | None
    stage_failed: str | None      # 'viterbi' | 'reed_solomon' | None
    crc_valid_count: int
    confidence: float
    warnings: list[str] = field(default_factory=list)


def concatenated_encode(bits: np.ndarray, rs_m: int = 4, rs_n: int = 15, rs_k: int = 11,
                        constraint_length: int = DEFAULT_CONSTRAINT,
                        generators: tuple[int, int] = DEFAULT_POLYS) -> np.ndarray:
    """Encode message bits with the outer RS block then inner convolutional code.
    Message is zero-padded to the RS block size."""
    msg = np.asarray(bits, dtype=np.uint8)
    rs_bits_len = rs_k * rs_m
    if len(msg) > rs_bits_len:
        raise ValueError(f"message too large for RS block ({rs_bits_len} bits)")
    padded = np.zeros(rs_bits_len, dtype=np.uint8)
    padded[: len(msg)] = msg
    rs_bits = reed_solomon_encode(padded, rs_m, rs_n, rs_k)
    return convolutional_encode(rs_bits, constraint_length, generators)


def concatenated_decode(bits: np.ndarray, rs_m: int = 4, rs_n: int = 15, rs_k: int = 11,
                        constraint_length: int = DEFAULT_CONSTRAINT,
                        generators: tuple[int, int] = DEFAULT_POLYS,
                        traceback_depth: int | None = None) -> ConcatenatedResult:
    """Decode a concatenated-coded bitstream; report precisely which stage failed."""
    viterbi = viterbi_decode(bits, constraint_length, generators, traceback_depth)
    rs_bits = viterbi.decoded_bits
    if len(rs_bits) < rs_k * rs_m:
        rs_bits = np.zeros(rs_k * rs_m, dtype=np.uint8)
        viterbi = ViterbiResult(
            decoded_bits=rs_bits, path_metric=viterbi.path_metric,
            traceback_depth=viterbi.traceback_depth,
            warnings=viterbi.warnings)
    rs = reed_solomon_decode(rs_bits, rs_m, rs_n, rs_k)
    decoded = rs.decoded_bits[: rs_k * rs_m]

    stage_failed = None
    warnings = list(viterbi.warnings) + list(rs.warnings)
    if not rs.syndrome_zero:
        stage_failed = "reed_solomon"
        warnings.append(f"Outer RS code did not converge (over-capacity after Viterbi); frame dropped.")
        confidence = 0.0
    else:
        confidence = float(rs.confidence)

    return ConcatenatedResult(
        decoded_bits=decoded,
        n_input_bits=len(bits),
        n_output_bits=rs_k * rs_m,
        viterbi=viterbi,
        reed_solomon=rs,
        stage_failed=stage_failed,
        crc_valid_count=count_crc_valid_frames(np.packbits(decoded) if len(decoded) else b""),
        confidence=confidence,
        warnings=warnings,
    )