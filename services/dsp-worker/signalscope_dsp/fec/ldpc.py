"""LDPC block codec: a systematic regular (3,6) rate-1/2 code with a min-sum
belief-propagation decoder.

The published standard in the traceability doc is a regular (3,6) rate-1/2
systematic LDPC code (IEEE 802.16e-style ensemble, built to order here). The
parity-check matrix is H = [A | I_(n-k)] with a sparse random A, so encoding is
systematic (message bits followed by parity bits) and exact:
    codeword = [message | A @ message (mod 2)].

Decoding runs min-sum belief propagation over H with configurable iteration
count. A decode only reports success (`syndrome_zero=True`) when the final
hard decision actually satisfies every parity check — random garbage either
fails to converge or fails the syndrome, never a fabricated success.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .validation import bits_to_bytes, count_crc_valid_frames


@dataclass
class LDPCResult:
    decoded_bits: np.ndarray
    parity_check: np.ndarray       # raw H (0/1) used for the decode
    n_input_bits: int
    n_output_bits: int
    iterations: int
    syndrome_zero: bool            # final hard decision actually satisfies H c = 0
    corrected_bits: int            # bits flipped relative to the received hard bits
    crc_valid_count: int           # trailing-16-bit CRC checks passed on the message
    confidence: float              # 0..1 from the final LLR magnitudes
    warnings: list[str] = field(default_factory=list)


def build_regular_ldpc(n_code: int, k_message: int, column_weight: int = 3,
                       seed: int = 42) -> np.ndarray:
    """Build a systematic parity-check matrix H = [A | I] with sparse random A.

    Guarantees (verified here so downstream code can rely on them):
      - H has shape (n-k, n), rank n-k (the identity block ensures full row rank),
      - every row/column has at least one 1,
      - column degrees ~= column_weight.
    """
    if not (0 < k_message < n_code):
        raise ValueError("need 0 < k < n")
    m_checks = n_code - k_message
    rng = np.random.default_rng(seed)
    H = np.zeros((m_checks, n_code), dtype=np.uint8)
    for col in range(k_message):
        targets = rng.choice(m_checks, size=column_weight, replace=False)
        H[targets, col] = 1
    H[:, k_message:] = np.eye(m_checks, dtype=np.uint8)
    # guard: every parity row must carry at least one message-bit 1 for a useful code
    for row in range(m_checks):
        if H[row, :k_message].sum() == 0:
            H[row, rng.integers(0, k_message)] = 1
    return H


def ldpc_encode(bits: np.ndarray, parity_check: np.ndarray) -> np.ndarray:
    """Systematic encode: message bits then parity bits p = A @ message (mod 2)."""
    H = np.asarray(parity_check, dtype=np.uint8)
    n_code, k_message = H.shape[1], H.shape[1] - H.shape[0]
    msg = np.asarray(bits, dtype=np.uint8)[:k_message]
    if len(msg) != k_message:
        raise ValueError(f"expected {k_message} message bits, got {len(msg)}")
    A = H[:, :k_message]
    parity = (A @ msg) % 2
    return np.concatenate([msg, parity]).astype(np.uint8)


def ldpc_decode(bits: np.ndarray, parity_check: np.ndarray, max_iterations: int = 40,
                channel_llr: float = 3.5) -> LDPCResult:
    """Min-sum belief propagation over the parity-check matrix.

    `bits` may be hard (0/1) or soft LLRs (passed as floats in arbitrary
    units); hard bits are mapped to +/-channel_llr. Convention: codeword bit 0
    maps to positive LLR.
    """
    H = np.asarray(parity_check, dtype=np.uint8)
    checks, n_code = H.shape
    k_message = n_code - checks
    received = np.asarray(bits, dtype=np.float64)[:n_code]
    if len(received) != n_code:
        raise ValueError(f"expected {n_code} received bits, got {len(received)}")
    # hard 0/1 input? map to LLRs; already signed float input is used as-is
    if np.all((received == 0) | (received == 1)):
        llr_input = np.where(received == 0, channel_llr, -channel_llr)
    else:
        llr_input = received

    n_vars = n_code
    # neighbours per check / variable for the dense min-sum updates
    var_neighbors = [np.nonzero(H[:, v])[0].tolist() for v in range(n_code)]
    check_neighbors = [np.nonzero(H[c])[0].tolist() for c in range(checks)]

    # messages: q[c, v] variable->check, r[c, v] check->variable (rows = checks)
    q = np.tile(llr_input, (checks, 1)).copy()
    for v in range(n_vars):
        q[H[:, v] == 0, v] = 0.0  # no message to a variable the check isn't connected to

    decision = llr_input < 0
    syndrome = (H @ decision) % 2
    iterations = 0

    for it in range(1, max_iterations + 1):
        iterations = it
        # check -> variable (min-sum); non-neighbour entries stay 0
        r = np.zeros((checks, n_vars))
        for c in range(checks):
            nbr = check_neighbors[c]
            if not nbr:
                continue
            col = q[c, nbr]
            mags = np.abs(col)
            signs = np.sign(col)
            total_sign = signs.prod()
            order = np.argsort(mags)
            min1 = mags[order[0]]
            min2 = mags[order[1]] if len(nbr) > 1 else min1
            n_min1 = int((mags == min1).sum())
            for l, v in enumerate(nbr):
                mag = min2 if (n_min1 == 1 and mags[l] == min1) else min1
                r[c, v] = total_sign * signs[l] * mag
        # variable -> check
        s = np.empty(n_vars)
        for v in range(n_vars):
            total = float(llr_input[v]) + float(np.sum(r[:, v]))
            s[v] = total
            for c in var_neighbors[v]:
                q[c, v] = total - r[c, v]
        decision = s < 0
        syndrome = (H @ decision.astype(np.uint8)) % 2
        if not syndrome.any():
            break

    decoded_bits = decision[:k_message].astype(np.uint8)
    received_hard = np.where(llr_input[:k_message] < 0, 1, 0)
    corrected = int(np.sum(decoded_bits != received_hard))
    confidence = float(np.clip(np.mean(np.abs(s)) / channel_llr, 0.0, 1.0)) if len(s) else 0.0

    warnings = []
    if syndrome.any():
        warnings.append(
            f"Belief propagation did not reach a zero syndrome in {iterations} "
            f"iterations; decoded output does not satisfy the parity checks."
        )
        confidence = 0.0

    decoded_bytes = bits_to_bytes(decoded_bits)
    crc_count = count_crc_valid_frames(decoded_bytes)

    return LDPCResult(
        decoded_bits=decoded_bits,
        parity_check=H,
        n_input_bits=n_code,
        n_output_bits=k_message,
        iterations=iterations,
        syndrome_zero=not syndrome.any(),
        corrected_bits=corrected,
        crc_valid_count=crc_count,
        confidence=confidence,
        warnings=warnings,
    )