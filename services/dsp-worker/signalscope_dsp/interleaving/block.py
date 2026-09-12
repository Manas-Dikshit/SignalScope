from __future__ import annotations

import math
import warnings

import numpy as np


def _check_block_fit(n_bits: int, rows: int, cols: int, op: str) -> None:
    n = rows * cols
    if n_bits > n:
        warnings.warn(
            f"{op}: input has {n_bits} bits but the {rows}x{cols} block holds "
            f"{n}; {n_bits - n} trailing bit(s) will be dropped.",
            UserWarning, stacklevel=3,
        )
    elif n_bits < n:
        warnings.warn(
            f"{op}: input has {n_bits} bits but the {rows}x{cols} block holds "
            f"{n}; output is zero-padded to {n} bits.",
            UserWarning, stacklevel=3,
        )


def block_interleave(bits: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Write bits row-wise into a rows x cols matrix, read out column-wise."""
    n = rows * cols
    _check_block_fit(len(bits), rows, cols, "block_interleave")
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = padded.reshape(rows, cols)
    return matrix.T.flatten()


def block_deinterleave(bits: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Inverse of block_interleave: write column-wise, read row-wise."""
    n = rows * cols
    _check_block_fit(len(bits), rows, cols, "block_deinterleave")
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = padded.reshape(cols, rows).T
    return matrix.flatten()


def convolutional_interleave(bits: np.ndarray, n_branches: int, delay_step: int) -> np.ndarray:
    """Classic Forney/Ramsey-style convolutional interleaver: branch i delays symbols
    by i * delay_step (in branch-local sample counts), symbols are commutated
    cyclically across branches. Paired with convolutional_deinterleave using the same
    (n_branches, delay_step), the end-to-end pipeline delay before the output matches
    the original input is (n_branches - 1) * delay_step * n_branches absolute samples
    (each branch only sees every n_branches-th sample of the stream, so a
    branch-local delay of d samples is a d * n_branches delay in absolute stream
    position)."""
    buffers = [np.zeros(i * delay_step, dtype=bits.dtype).tolist() for i in range(n_branches)]
    out = []
    for idx, b in enumerate(bits):
        branch = idx % n_branches
        buffers[branch].append(b)
        out.append(buffers[branch].pop(0))
    return np.array(out, dtype=bits.dtype)


def convolutional_deinterleave(bits: np.ndarray, n_branches: int, delay_step: int) -> np.ndarray:
    """Inverse of convolutional_interleave: branch i delays by (n_branches-1-i)*delay_step."""
    max_delay = (n_branches - 1) * delay_step
    buffers = [np.zeros((max_delay - i * delay_step), dtype=bits.dtype).tolist() for i in range(n_branches)]
    out = []
    for idx, b in enumerate(bits):
        branch = idx % n_branches
        buffers[branch].append(b)
        out.append(buffers[branch].pop(0))
    return np.array(out, dtype=bits.dtype)


def _check_diagonal_invertible(cols: int, offset: int) -> None:
    # The placement c = (t*offset + r) % cols is a permutation (hence the
    # interleave is lossless/invertible) iff gcd(offset, cols) == 1.
    if math.gcd(offset, cols) != 1:
        raise ValueError(
            f"diagonal interleave requires gcd(offset, cols) == 1, got "
            f"gcd({offset}, {cols}) = {math.gcd(offset, cols)}: placements would "
            f"collide and silently overwrite bits."
        )


def diagonal_interleave(bits: np.ndarray, rows: int, cols: int, offset: int = 1) -> np.ndarray:
    n = rows * cols
    _check_diagonal_invertible(cols, offset)
    _check_block_fit(len(bits), rows, cols, "diagonal_interleave")
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = np.zeros((rows, cols), dtype=bits.dtype)
    for i, val in enumerate(padded):
        r = i % rows
        c = (i // rows * offset + r) % cols
        matrix[r, c] = val
    out = np.zeros(n, dtype=bits.dtype)
    k = 0
    for c in range(cols):
        for r in range(rows):
            out[k] = matrix[r, c]
            k += 1
    return out


def diagonal_deinterleave(bits: np.ndarray, rows: int, cols: int, offset: int = 1) -> np.ndarray:
    """Inverse of diagonal_interleave: the input is the column-major readout of
    the permuted matrix, so rebuild the matrix first, then invert the
    (row, col) placement permutation."""
    n = rows * cols
    _check_diagonal_invertible(cols, offset)
    _check_block_fit(len(bits), rows, cols, "diagonal_deinterleave")
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    # column-major flatten of M == row-major flatten of M.T
    matrix = padded.reshape(cols, rows).T
    out = np.zeros(n, dtype=bits.dtype)
    for i in range(n):
        r = i % rows
        c = (i // rows * offset + r) % cols
        out[i] = matrix[r, c]
    return out


def score_deinterleave_candidate(recovered_bits: np.ndarray) -> float:
    """Heuristic validation score in [0,1] for a candidate de-interleaving parameter
    set: penalizes very high or very low bit-transition rates, which are typical
    signatures of a still-scrambled (interleaved) bitstream rather than real data/FEC
    frames. This is NOT proof of correctness — it's a coarse hypothesis-ranking score."""
    if len(recovered_bits) < 2:
        return 0.0
    transitions = np.mean(np.abs(np.diff(recovered_bits.astype(int))))
    # real coded/data bitstreams are rarely perfectly random (0.5) or near-constant
    return float(1.0 - 2.0 * abs(transitions - 0.5))
