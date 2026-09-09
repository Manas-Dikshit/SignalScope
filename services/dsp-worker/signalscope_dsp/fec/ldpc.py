from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class LDPCResult:
    decoded_bits: np.ndarray
    iterations: int
    parity_satisfied: bool
    warnings: list[str] = field(default_factory=list)


def ldpc_encode(message_bits: np.ndarray, generator_matrix: np.ndarray) -> np.ndarray:
    """Systematic binary LDPC encoding from a generator matrix."""
    message = np.asarray(message_bits, dtype=np.uint8) & 1
    generator = np.asarray(generator_matrix, dtype=np.uint8) & 1
    if generator.ndim != 2 or message.size != generator.shape[0]:
        raise ValueError("message length must match generator matrix rows")
    return (message @ generator % 2).astype(np.uint8)


def ldpc_decode(llr: np.ndarray, parity_check: np.ndarray, max_iterations: int = 50) -> LDPCResult:
    """Min-sum belief-propagation decoder for a binary parity-check matrix."""
    if max_iterations < 1:
        raise ValueError("max_iterations must be positive")
    checks = np.asarray(parity_check, dtype=np.uint8) & 1
    soft = np.asarray(llr, dtype=float)
    if checks.ndim != 2 or checks.shape[1] != soft.size:
        raise ValueError("LLR length must match parity-check columns")
    edges = np.argwhere(checks)
    check_to_edges = [[] for _ in range(checks.shape[0])]
    variable_to_edges = [[] for _ in range(checks.shape[1])]
    for edge, (check, variable) in enumerate(edges):
        check_to_edges[check].append(edge)
        variable_to_edges[variable].append(edge)
    variable_messages = soft[edges[:, 1]].copy()
    check_messages = np.zeros(len(edges), dtype=float)
    for iteration in range(1, max_iterations + 1):
        for check, edge_ids in enumerate(check_to_edges):
            if not edge_ids:
                continue
            values = variable_messages[edge_ids]
            signs = np.sign(values)
            magnitudes = np.abs(values)
            for local, edge in enumerate(edge_ids):
                others = np.delete(magnitudes, local)
                sign = np.prod(np.delete(signs, local))
                check_messages[edge] = sign * (np.min(others) if len(others) else 0.0)
        posterior = soft.copy()
        for variable, edge_ids in enumerate(variable_to_edges):
            posterior[variable] += np.sum(check_messages[edge_ids])
            for edge in edge_ids:
                variable_messages[edge] = posterior[variable] - check_messages[edge]
        decoded = (posterior < 0).astype(np.uint8)
        if np.all((checks @ decoded) % 2 == 0):
            return LDPCResult(decoded, iteration, True)
    return LDPCResult(decoded, max_iterations, False, ["Maximum LDPC iterations reached without satisfying all parity checks."])
