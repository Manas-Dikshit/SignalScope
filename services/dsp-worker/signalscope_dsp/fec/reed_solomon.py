from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


_EXP = np.zeros(512, dtype=np.int16)
_LOG = np.full(256, -1, dtype=np.int16)
value = 1
for index in range(255):
    _EXP[index] = value
    _LOG[value] = index
    value <<= 1
    if value & 0x100:
        value ^= 0x11D
_EXP[255:] = _EXP[:257]


def _mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else int(_EXP[int(_LOG[a]) + int(_LOG[b])])


def _poly_mul(left: list[int], right: list[int]) -> list[int]:
    out = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            out[i + j] ^= _mul(a, b)
    return out


def _generator(nsym: int) -> list[int]:
    result = [1]
    for i in range(nsym):
        result = _poly_mul(result, [1, int(_EXP[i])])
    return result


def reed_solomon_encode(data: bytes, parity_symbols: int = 32) -> bytes:
    """Encode a byte payload using a shortened RS code over GF(2^8)."""
    if not 1 <= parity_symbols <= 254:
        raise ValueError("parity_symbols must be between 1 and 254")
    if len(data) + parity_symbols > 255:
        raise ValueError("data plus parity must fit in a 255-symbol RS codeword")
    generator = _generator(parity_symbols)
    parity = [0] * parity_symbols
    for symbol in data:
        feedback = symbol ^ parity[0]
        parity = parity[1:] + [0]
        if feedback:
            for index in range(parity_symbols):
                parity[index] ^= _mul(generator[index + 1], feedback)
    return data + bytes(parity)


@dataclass
class ReedSolomonResult:
    decoded_bytes: bytes
    corrected_symbols: int
    valid: bool
    warnings: list[str] = field(default_factory=list)


def reed_solomon_decode(codeword: bytes, parity_symbols: int = 32) -> ReedSolomonResult:
    """Decode and correct errors using Berlekamp-Massey and Forney's algorithm."""
    if not 1 <= parity_symbols <= 254:
        raise ValueError("parity_symbols must be between 1 and 254")
    if len(codeword) > 255 or len(codeword) <= parity_symbols:
        raise ValueError("codeword length must be between parity_symbols + 1 and 255")
    values = list(codeword)
    syndromes = [
        _poly_eval(values, int(_EXP[i]))
        for i in range(parity_symbols)
    ]
    if max(syndromes, default=0) == 0:
        return ReedSolomonResult(codeword[:-parity_symbols], 0, True)

    locator = _berlekamp_massey(syndromes)
    error_positions = []
    for position in range(len(values)):
        root = int(_EXP[(len(values) - 1 - position) % 255])
        if _poly_eval(locator, root) == 0:
            error_positions.append(position)
    if not error_positions or len(error_positions) != len(locator) - 1:
        return ReedSolomonResult(codeword[:-parity_symbols], 0, False,
                                 ["Too many errors to correct or invalid RS locator polynomial."])

    roots = [int(_EXP[(len(values) - 1 - position) % 255]) for position in error_positions]
    magnitudes = _solve_error_magnitudes(syndromes, roots)
    for position, magnitude in zip(error_positions, magnitudes):
        values[position] ^= magnitude
    corrected = len(error_positions)

    valid = all(_poly_eval(values, int(_EXP[i])) == 0 for i in range(parity_symbols))
    warnings = [] if valid else ["RS correction did not produce a valid codeword."]
    return ReedSolomonResult(bytes(values[:-parity_symbols]), corrected, valid, warnings)


def _poly_eval(poly: list[int], x: int) -> int:
    result = 0
    for coefficient in poly:
        result = _mul(result, x) ^ coefficient
    return result


def _inverse(value: int) -> int:
    if value == 0:
        raise ValueError("zero has no multiplicative inverse")
    return int(_EXP[255 - int(_LOG[value])])


def _berlekamp_massey(syndromes: list[int]) -> list[int]:
    locator = [1]
    previous = [1]
    degree = 0
    shift = 1
    discrepancy_scale = 1
    for index in range(len(syndromes)):
        discrepancy = syndromes[index]
        for j in range(1, len(locator)):
            if index - j >= 0:
                discrepancy ^= _mul(locator[j], syndromes[index - j])
        if discrepancy == 0:
            shift += 1
            continue
        factor = _mul(discrepancy, _inverse(discrepancy_scale))
        correction = [0] * shift + [_mul(factor, item) for item in previous]
        old = locator[:]
        if len(locator) < len(correction):
            locator.extend([0] * (len(correction) - len(locator)))
        for j, item in enumerate(correction):
            locator[j] ^= item
        if 2 * degree <= index:
            previous = old
            degree = index + 1 - degree
            discrepancy_scale = discrepancy
            shift = 1
        else:
            shift += 1
    return locator


def _solve_error_magnitudes(syndromes: list[int], roots: list[int]) -> list[int]:
    """Solve S_i = sum(error_j * root_j**i) over GF(256)."""
    count = len(roots)
    matrix = [
        [_exp_power(root, row) for root in roots] + [syndromes[row]]
        for row in range(count)
    ]
    for column in range(count):
        pivot = next((row for row in range(column, count) if matrix[row][column]), None)
        if pivot is None:
            raise ValueError("singular RS error-magnitude system")
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        inverse = _inverse(matrix[column][column])
        matrix[column] = [_mul(item, inverse) for item in matrix[column]]
        for row in range(count):
            if row == column or not matrix[row][column]:
                continue
            factor = matrix[row][column]
            matrix[row] = [left ^ _mul(factor, right) for left, right in zip(matrix[row], matrix[column])]
    return [matrix[row][-1] for row in range(count)]


def _exp_power(value: int, power: int) -> int:
    if power == 0:
        return 1
    if value == 0:
        return 0
    return int(_EXP[(int(_LOG[value]) * power) % 255])
