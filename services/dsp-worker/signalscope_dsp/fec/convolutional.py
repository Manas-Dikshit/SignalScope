from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def _poly_bits(poly: int, constraint_length: int) -> list[int]:
    return [(poly >> i) & 1 for i in range(constraint_length - 1, -1, -1)]


def convolutional_encode(bits: np.ndarray, constraint_length: int = 7,
                          generators: tuple[int, int] = (0o171, 0o133)) -> np.ndarray:
    """Rate-1/2 convolutional encoder. Defaults are the common (K=7, g=[171,133]_8)
    industry-standard code (used by e.g. CCSDS/DVB legacy links)."""
    g0 = _poly_bits(generators[0], constraint_length)
    g1 = _poly_bits(generators[1], constraint_length)
    state = [0] * (constraint_length - 1)
    out = []
    for b in bits:
        reg = [int(b)] + state
        o0 = sum(x * y for x, y in zip(reg, g0)) % 2
        o1 = sum(x * y for x, y in zip(reg, g1)) % 2
        out.extend([o0, o1])
        state = reg[:-1]
    return np.array(out, dtype=np.uint8)


@dataclass
class ViterbiResult:
    decoded_bits: np.ndarray
    path_metric: float
    traceback_depth: int
    warnings: list[str] = field(default_factory=list)


def viterbi_decode(coded_bits: np.ndarray, constraint_length: int = 7,
                    generators: tuple[int, int] = (0o171, 0o133),
                    traceback_depth: int | None = None) -> ViterbiResult:
    """Hard-decision Viterbi decoder for the rate-1/2 code above.

    The trellis step is vectorized with numpy (one small-array op per symbol
    instead of a Python loop over all 2^K states), so MVP frame sizes decode
    fast without extra dependencies; a production build would use GNU Radio's
    optimized FEC blocks for large recordings.
    """
    g0 = _poly_bits(generators[0], constraint_length)
    g1 = _poly_bits(generators[1], constraint_length)
    n_states = 2 ** (constraint_length - 1)
    traceback_depth = traceback_depth or min(64, max(16, 5 * constraint_length))

    if len(coded_bits) % 2 != 0:
        coded_bits = coded_bits[:-1]
    n_symbols = len(coded_bits) // 2
    warnings = []
    if n_symbols == 0:
        return ViterbiResult(np.array([], dtype=np.uint8), 0.0, traceback_depth, ["No input bits."])

    # Transition tables: next_state[s, b], out0[s, b], out1[s, b].
    next_state = np.zeros((n_states, 2), dtype=np.int64)
    out0 = np.zeros((n_states, 2), dtype=np.uint8)
    out1 = np.zeros((n_states, 2), dtype=np.uint8)
    for state in range(n_states):
        state_bits = [(state >> i) & 1 for i in range(constraint_length - 2, -1, -1)]
        for bit in (0, 1):
            reg = [bit] + state_bits
            o0 = sum(x * y for x, y in zip(reg, g0)) % 2
            o1 = sum(x * y for x, y in zip(reg, g1)) % 2
            nxt = 0
            for v in reg[:-1]:
                nxt = (nxt << 1) | v
            next_state[state, bit] = nxt
            out0[state, bit] = o0
            out1[state, bit] = o1

    # Predecessor tables: every state has exactly two incoming edges.
    # Built iterating states ascending, bit 0 then 1, so pred[:, 0] is the
    # predecessor the old strict-`<` loop preferred on ties (same decoding).
    pred = np.full((n_states, 2), -1, dtype=np.int64)
    pred_bit = np.zeros((n_states, 2), dtype=np.int64)
    fill = np.zeros(n_states, dtype=np.int64)
    for s in range(n_states):
        for b in (0, 1):
            nxt = next_state[s, b]
            pred[nxt, fill[nxt]] = s
            pred_bit[nxt, fill[nxt]] = b
            fill[nxt] += 1

    INF = float("inf")
    path_metrics = np.full(n_states, INF)
    path_metrics[0] = 0.0
    # survivors[t, s] = the PREDECESSOR state that the best path into state s at time t
    # came from. (Storing only the input bit is not enough to reconstruct the
    # predecessor, because — under the shift-register convention used above, where
    # the newest input becomes the state's top bit — two different predecessor
    # states can share the same top-bit/input-bit but differ in the bit that's about
    # to shift out, which the input bit alone doesn't disambiguate.)
    survivors = np.full((n_symbols, n_states), -1, dtype=np.int64)

    for t in range(n_symbols):
        r0, r1 = coded_bits[2 * t], coded_bits[2 * t + 1]
        # True Hamming branch metric in {0, 1, 2}. (Note: the previous loop
        # version summed two numpy bools, and numpy bool+bool saturates to bool,
        # so a double-bit mismatch cost 1 instead of 2 — and the penalty even
        # depended on the input's dtype. Casting before adding fixes both.)
        branch = (out0 != r0).astype(np.float64) + (out1 != r1).astype(np.float64)
        cand = path_metrics[:, None] + branch  # cand[s, b]: metric via (state s, input b)
        m0 = cand[pred[:, 0], pred_bit[:, 0]]
        m1 = cand[pred[:, 1], pred_bit[:, 1]]
        use1 = m1 < m0  # strict: ties keep pred[:, 0], matching the old loop
        path_metrics = np.where(use1, m1, m0)
        survivors[t] = np.where(use1, pred[:, 1], pred[:, 0])
        if np.all(path_metrics == INF):
            warnings.append(f"Path metrics diverged at symbol {t}; input may not match this code.")
            path_metrics[0] = 0.0

    # traceback from best final state
    best_state = int(np.argmin(path_metrics))
    decoded = np.zeros(n_symbols, dtype=np.uint8)
    state = best_state
    for t in range(n_symbols - 1, -1, -1):
        prev_state = int(survivors[t, state])
        if prev_state < 0:
            warnings.append(f"Unreachable state encountered during traceback at symbol {t}.")
            prev_state = 0
        # The input bit that caused prev_state -> state is exactly the top bit of
        # `state` under this convention (newest input occupies the MSB position).
        bit = (state >> (constraint_length - 2)) & 1 if constraint_length > 1 else 0
        decoded[t] = bit
        state = prev_state

    return ViterbiResult(decoded_bits=decoded, path_metric=float(np.min(path_metrics)),
                          traceback_depth=traceback_depth, warnings=warnings)
