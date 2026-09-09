from __future__ import annotations

import numpy as np


def block_interleave(bits: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Write bits row-wise into a rows x cols matrix, read out column-wise."""
    n = rows * cols
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = padded.reshape(rows, cols)
    return matrix.T.flatten()


def block_deinterleave(bits: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Inverse of block_interleave: write column-wise, read row-wise."""
    n = rows * cols
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


def diagonal_interleave(bits: np.ndarray, rows: int, cols: int, offset: int = 1) -> np.ndarray:
    n = rows * cols
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
    """Inverse of :func:`diagonal_interleave` for one fixed-size block."""
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be positive")
    if offset % cols == 0:
        raise ValueError("offset must be relatively non-zero modulo cols")
    n = rows * cols
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = padded.reshape(cols, rows).T
    recovered = np.zeros(n, dtype=bits.dtype)
    for i in range(n):
        r = i % rows
        c = (i // rows * offset + r) % cols
        recovered[i] = matrix[r, c]
    return recovered


def pseudo_random_interleave(bits: np.ndarray, seed: int = 0, block_size: int | None = None) -> np.ndarray:
    """Permute each block with a reproducible pseudo-random permutation."""
    if seed < 0:
        raise ValueError("seed must be non-negative")
    size = block_size or len(bits)
    if size < 1:
        raise ValueError("block_size must be positive")
    out = np.zeros_like(bits)
    rng = np.random.default_rng(seed)
    for start in range(0, len(bits), size):
        end = min(start + size, len(bits))
        permutation = rng.permutation(end - start)
        out[start:end] = bits[start:end][permutation]
    return out


def pseudo_random_deinterleave(bits: np.ndarray, seed: int = 0, block_size: int | None = None) -> np.ndarray:
    """Inverse of :func:`pseudo_random_interleave`."""
    if seed < 0:
        raise ValueError("seed must be non-negative")
    size = block_size or len(bits)
    if size < 1:
        raise ValueError("block_size must be positive")
    out = np.zeros_like(bits)
    rng = np.random.default_rng(seed)
    for start in range(0, len(bits), size):
        end = min(start + size, len(bits))
        permutation = rng.permutation(end - start)
        recovered = np.zeros(end - start, dtype=bits.dtype)
        recovered[permutation] = bits[start:end]
        out[start:end] = recovered
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
