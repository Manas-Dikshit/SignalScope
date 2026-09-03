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

    This is a straightforward reference implementation (O(2^K * N)) suitable for
    the MVP's frame sizes; a production build would use GNU Radio's optimized FEC
    blocks for large recordings.
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

    # precompute transition outputs for every (state, input_bit)
    trans_out = {}
    trans_next = {}
    for state in range(n_states):
        state_bits = [(state >> i) & 1 for i in range(constraint_length - 2, -1, -1)]
        for bit in (0, 1):
            reg = [bit] + state_bits
            o0 = sum(x * y for x, y in zip(reg, g0)) % 2
            o1 = sum(x * y for x, y in zip(reg, g1)) % 2
            next_state = 0
            for v in reg[:-1]:
                next_state = (next_state << 1) | v
            trans_out[(state, bit)] = (o0, o1)
            trans_next[(state, bit)] = next_state

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
        new_metrics = np.full(n_states, INF)
        new_survivors = np.full(n_states, -1, dtype=np.int64)
        for state in range(n_states):
            if path_metrics[state] == INF:
                continue
            for bit in (0, 1):
                o0, o1 = trans_out[(state, bit)]
                branch_metric = (o0 != r0) + (o1 != r1)  # Hamming distance
                metric = path_metrics[state] + branch_metric
                nxt = trans_next[(state, bit)]
                if metric < new_metrics[nxt]:
                    new_metrics[nxt] = metric
                    new_survivors[nxt] = state
        path_metrics = new_metrics
        survivors[t] = new_survivors
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
