"""Reed-Solomon block codec over GF(2^m).

Implements a configurable-symbol-size RS(n, k) codec with both error correction
(Berlekamp–Massey + Chien search + Forney) and erasure correction (the same
pipeline seeded by a known erasure locator). Encoding is systematic: the
transmitted stream is `k` message symbols followed by `(n - k)` parity symbols.

The result object mirrors the `ViterbiResult` contract used elsewhere in this
package (decoded bits + honest counts + confidence + warnings) and adds the
symbol-level counts the block-code spec requires: corrected symbols, corrected
erasures, and a post-decode CRC-16 validity count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .validation import bits_to_bytes, crc16_ccitt


# Known primitive polynomials for GF(2^m), expressed as the packed coefficient
# bitmask (e.g. 0x11d == x^8 + x^4 + x^3 + x^2 + 1). Used to build the field's
# log/antilog tables. m > 10 is rejected simply because no table is defined —
# the codec is otherwise arithmetic-generic.
_PRIMITIVE_POLYS = {
    2: 0b111,        # x^2 + x + 1
    3: 0b1011,       # x^3 + x + 1
    4: 0b10011,      # x^4 + x + 1
    5: 0b100101,     # x^5 + x^2 + 1
    6: 0b1000011,    # x^6 + x + 1
    7: 0b10001001,   # x^7 + x^3 + 1
    8: 0b100011101,  # x^8 + x^4 + x^3 + x^2 + 1
    9: 0b1000010001, # x^9 + x^4 + 1
    10: 0b10000001001,  # x^10 + x^3 + 1
}


class _GF:
    """GF(2^m) arithmetic via log/antilog tables built from a primitive polynomial."""

    def __init__(self, m: int):
        if m < 2 or m > 10:
            raise ValueError(f"GF(2^{m}) not supported; select m in [2, 10]")
        self.m = m
        self.q = 1 << m
        self.poly = _PRIMITIVE_POLYS[m]
        self._build_tables()

    def _build_tables(self) -> None:
        q, poly = self.q, self.poly

        def mul(a: int, b: int) -> int:
            res = 0
            while b:
                if b & 1:
                    res ^= a
                a <<= 1
                if a & q:
                    a ^= poly
                b >>= 1
            return res

        exp = [0] * (q - 1)
        log = [-1] * q
        x = 1
        for i in range(q - 1):
            exp[i] = x
            log[x] = i
            x = mul(x, 2)  # 2 (== alpha) is a primitive element by construction
        self.exp = exp
        self.log = log
        self._mul = mul

    def mul(self, a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        return self.exp[(self.log[a] + self.log[b]) % (self.q - 1)]

    def inv(self, a: int) -> int:
        if a == 0:
            raise ValueError("0 has no inverse in GF(2^m)")
        return self.exp[(self.q - 1 - self.log[a]) % (self.q - 1)]

    def pow(self, a: int, n: int) -> int:
        if a == 0:
            return 0
        # negative exponents are fine: exponent modulo (q-1) with 0 kept as 0
        if n < 0:
            n = (self.q - 1) + (n % (self.q - 1) or 0)
        return self.exp[(self.log[a] * n) % (self.q - 1)]

    def sub(self, a: int, b: int) -> int:
        return a ^ b  # characteristic 2: addition == subtraction == XOR


def _bits_to_symbols(bits: np.ndarray, m: int) -> np.ndarray:
    n = len(bits) // m
    b = np.asarray(bits, dtype=np.uint8)[: n * m].reshape(n, m)
    sym = np.zeros(n, dtype=np.int64)
    for i in range(m):
        sym |= b[:, i].astype(np.int64) << (m - 1 - i)
    return sym


def _symbols_to_bits(symbols, m: int) -> np.ndarray:
    out = np.zeros(len(symbols) * m, dtype=np.uint8)
    for si, s in enumerate(symbols):
        for b in range(m):
            out[si * m + b] = (int(s) >> (m - 1 - b)) & 1
    return out


def _poly_mul(gf: _GF, a: list[int], b: list[int]) -> list[int]:
    res = [0] * (len(a) + len(b) - 1)
    for i, ai in enumerate(a):
        if ai == 0:
            continue
        for j, bj in enumerate(b):
            if bj:
                res[i + j] ^= gf.mul(ai, bj)
    return res


def _poly_mod(gf: _GF, a: list[int], b: list[int]) -> list[int]:
    a = list(a)
    deg_b = len(b) - 1
    while len(a) - 1 >= deg_b:
        lead = a[-1]
        if lead == 0:
            a.pop()
            continue
        shift = (len(a) - 1) - deg_b
        for i, bi in enumerate(b):
            if bi:
                a[shift + i] ^= gf.mul(lead, bi)
        a.pop()
    while a and a[-1] == 0:
        a.pop()
    return a


def _poly_eval(gf: _GF, coefs: list[int], x: int) -> int:
    res = 0
    for c in reversed(coefs):
        res = gf.mul(res, x) ^ c
    return res


def _derivative(gf: _GF, coefs: list[int]) -> list[int]:
    # formal derivative over GF(2^m): k*c_k, and k is even => 0 in characteristic 2
    return [(k % 2) * c for k, c in enumerate(coefs)][1:] or [0]


def _berlekamp_massey(gf: _GF, syndromes: list[int]) -> list[int]:
    """Return the error-locator connection polynomial Lambda(x).

    Standard iterative BM for symbol fields; the result degree equals the
    number of (non-erasure) errors when the frame is correctable.
    """
    n = len(syndromes)
    C = [1] + [0] * n
    B = [1] + [0] * n
    L, m_shift, b = 0, 1, 1
    for N in range(n):
        d = syndromes[N]
        for i in range(1, L + 1):
            if C[i]:
                d ^= gf.mul(C[i], syndromes[N - i])
        if d == 0:
            m_shift += 1
            continue
        T = list(C)
        coef = gf.mul(d, gf.inv(b))
        for i, bi in enumerate(B):
            if bi and i + m_shift <= n:
                C[i + m_shift] ^= gf.mul(coef, bi)
        if 2 * L <= N:
            L = N + 1 - L
            B, b, m_shift = T, d, 1
        else:
            m_shift += 1
    return C[: L + 1]


def _erasure_locator(gf: _GF, positions: list[int], n: int) -> list[int]:
    """Lambda_E(x) = prod (1 - X_f x) with X_f = alpha^(n-1-pos).

    Over GF(2^m) addition and subtraction coincide, so `1 - X_f x` == `1 + X_f x`
    and the coefficient list is simply [1, X_f].
    """
    lam = [1]
    for pos in positions:
        X = gf.pow(2, n - 1 - pos)
        lam = _poly_mul(gf, lam, [1, X])
    return lam


def _forney_values(gf: _GF, locator: list[int], syndromes: list[int], n: int,
                   positions: list[int]) -> list[int] | None:
    """Error/erasure magnitudes at `positions` via Forney's formula (b = 0):

    e_i = X_i * Omega(X_i^-1) / Lambda'(X_i^-1)   (subtraction == addition here)
    with Omega(x) = (Lambda * S)(x) mod x^(2t).
    """
    omega = _poly_mod_xn(_poly_mul(gf, locator, syndromes), len(syndromes))
    lp = _derivative(gf, locator)
    values = []
    for pos in positions:
        X = gf.pow(2, n - 1 - pos)
        root = gf.inv(X)  # root of Lambda
        denom = _poly_eval(gf, lp, root)
        if denom == 0:
            return None
        num = _poly_eval(gf, omega, root)
        values.append(gf.mul(gf.mul(X, num), gf.inv(denom)))
    return values


def _syndromes(gf: _GF, symbols: list[int], n_parity: int) -> list[int]:
    return [_poly_eval(gf, list(reversed(symbols)), gf.pow(2, i)) for i in range(n_parity)]


def _count_crc_valid(decoded_bytes: bytes) -> int:
    """How many of the trailing-2-byte CRC16 fields in the decoded message validate.

    The pipeline's framing convention (shared with the convolutional path) is
    payload || crc16(payload big-endian). Every cleanly decoded RS message whose
    tail matches an earlier-2-bytes CRC counts as one valid frame.
    """
    count = 0
    buf = decoded_bytes
    # guard against pathological loops (max 8 CRC frames per decode)
    for _ in range(8):
        if len(buf) < 2:
            break
        payload, received = buf[:-2], int.from_bytes(buf[-2:], "big")
        if crc16_ccitt(payload) == received:
            count += 1
            break
        buf = buf[1:]
    return count


@dataclass
class ReedSolomonResult:
    decoded_bits: np.ndarray
    n_input_bits: int
    n_output_bits: int
    corrected_symbols: int     # symbol-level corrections applied (errors + erasures)
    corrected_erasures: int    # fraction of the above that were known erasures
    crc_valid_count: int       # CRC-16 checks that passed on the decoded message
    confidence: float          # 0..1; 0 when uncorrectable / at capacity
    warnings: list[str] = field(default_factory=list)
    syndrome_zero: bool = True


def reed_solomon_encode(bits: np.ndarray, m: int, n: int, k: int) -> np.ndarray:
    """Encode `bits` (k*m bits) into a systematic RS codeword of n symbols over GF(2^m).

    The parity symbol count 2t = n - k must be even and positive.
    """
    if n - k < 2 or (n - k) % 2 != 0:
        raise ValueError(f"invalid RS block: parity {n - k} must be positive and even")
    if k >= n or n >= (1 << m):
        raise ValueError(f"RS block must satisfy k < n < 2^m (got n={n}, k={k}, m={m})")
    gf = _GF(m)
    t = (n - k) // 2

    msg = _bits_to_symbols(np.asarray(bits)[: k * m], m)
    if len(msg) != k:
        raise ValueError(f"expected {k} message symbols ({k * m} bits), got {len(msg)}")

    # generator polynomial g(x) = prod_{i=0}^{2t-1} (x - alpha^i)
    gen = [1]
    for i in range(2 * t):
        gen = _poly_mul(gf, gen, [gf.pow(2, i), 1])
    # systematic: c(x) = x^(2t) * m(x) + (x^(2t)*m(x) mod g(x))
    msg_poly = list(reversed(msg))
    shifted = [0] * (2 * t) + msg_poly
    remainder = _poly_mod(gf, shifted, gen)
    # The transmitted sequence is `msg || parity`, and the decoder parses a
    # codeword as the polynomial with coefficient of x^j = t[n-1-j]. So the
    # parity symbols must be emitted high-power-first (i.e. reversed remainder).
    parity = [0] * (2 * t - len(remainder)) + list(reversed(remainder))
    codeword = list(msg) + parity
    return _symbols_to_bits(codeword, m)


def reed_solomon_decode(bits: np.ndarray, m: int, n: int, k: int,
                        erasures: list[int] | None = None) -> ReedSolomonResult:
    """Decode a (possibly corrupted) RS codeword of n symbols into its message.

    Corrects up to 2t symbol errors when erasures are known cheaply: the code
    corrects any e errors and f erasures with 2e + f <= 2t (t = (n-k)/2).
    `erasures` lists symbol indices known to be bad (0-based, from the start of
    the codeword). If the received frame is beyond correcting capacity the
    result is returned untouched with syndrome_zero=False and confidence 0 —
    the decoder never fabricates a success the way a naive lookup could.
    """
    if n - k < 2 or (n - k) % 2 != 0:
        raise ValueError(f"invalid RS block: parity {n - k} must be positive and even")
    if k >= n or n >= (1 << m):
        raise ValueError(f"RS block must satisfy k < n < 2^m")
    gf = _GF(m)
    t = (n - k) // 2
    warnings: list[str] = []

    rx = _bits_to_symbols(np.asarray(bits)[: n * m], m)
    if len(rx) != n:
        warnings.append(f"Expected {n} symbols ({n * m} bits); got {len(rx)}. Padding/truncation applied.")
        pad = np.zeros(n * m, dtype=np.uint8)
        pad[: len(rx) * m] = _symbols_to_bits(rx, m)
        rx = _bits_to_symbols(pad, m)

    erasures = [int(e) for e in (erasures or []) if 0 <= int(e) < n]
    if len(set(erasures)) != len(erasures):
        raise ValueError("erasure positions must be unique")

    syndromes = _syndromes(gf, rx.tolist(), 2 * t)
    syndrome_zero = all(s == 0 for s in syndromes)

    decoded = list(rx)
    corrected_errors = 0
    corrected_erasures = 0
    confidence = 1.0

    if not syndrome_zero:
        if len(erasures) > 2 * t:
            warnings.append(f"{len(erasures)} erasures exceeds codeword capacity 2t={2 * t}")
            syndrome_zero = False
            return ReedSolomonResult(
                _symbols_to_bits(decoded, m), n * m, k * m, 0, 0,
                _count_crc_valid(bits_to_bytes(_symbols_to_bits(decoded, m))),
                0.0, warnings, syndrome_zero,
            )

        lam_E = _erasure_locator(gf, erasures, n)
        f = len(erasures)
        if f == 0:
            lam_0 = _berlekamp_massey(gf, syndromes)
        else:
            # Forney (modified) syndromes: T_j = sum_i lam_i * S_{j+f-i}, j=0..2t-f-1
            # Erasure terms vanish (lambda_E vanishes at their locator roots), so
            # BM(T) recovers the locator of the genuine non-erasure errors only.
            T = []
            for j in range(2 * t - f):
                acc = 0
                for i, li in enumerate(lam_E):
                    idx = j + f - i
                    if 0 <= idx < 2 * t:
                        acc ^= gf.mul(li, syndromes[idx])
                T.append(acc)
            lam_0 = _berlekamp_massey(gf, T)
        locator = _poly_mul(gf, lam_0, lam_E) if f else lam_0

        # Chien search over every transmitted index
        error_positions: list[int] = []
        for pos in range(n):
            root = gf.pow(2, pos - (n - 1))  # X^-1 for X = alpha^(n-1-pos) == alpha^(pos-n+1)
            if _poly_eval(gf, locator, root) == 0:
                error_positions.append(pos)

        weight = len(locator) - 1
        expected_roots = len(error_positions)
        if expected_roots != weight:
            warnings.append(
                f"Chien search found {expected_roots} roots for a degree-{weight} locator; "
                f"frame exceeds correcting capacity (2e+f <= {2 * t})."
            )
            syndrome_zero = False
            confidence = 0.0
        else:
            values = _forney_values(gf, locator, syndromes, n, error_positions)
            if values is None:
                warnings.append("Forney evaluation hit a zero denominator; frame uncorrectable.")
                syndrome_zero = False
                confidence = 0.0
            else:
                for pos, val in zip(error_positions, values):
                    if pos in erasures:
                        corrected_erasures += 1
                    else:
                        corrected_errors += 1
                    decoded[pos] ^= val  # add error value (notice: subtract == add in GF(2^m))
                # re-check the corrected codeword's syndrome
                syndrome_zero = all(s == 0 for s in _syndromes(gf, decoded, 2 * t))
                if not syndrome_zero:
                    warnings.append("Corrected codeword still has non-zero syndrome; treating as decode failure.")
                    confidence = 0.0
                else:
                    used = corrected_errors * 2 + corrected_erasures
                    # margin remaining against the 2t budget; floor stays > 0 for a
                    # genuinely corrected frame even at full capacity
                    confidence = float(np.clip(1.0 - (used + 1) / (2 * t + 2), 0.0, 1.0))
    else:
        warnings.append("Syndrome already zero; no corrections required.")
        confidence = float(np.clip(1.0 - 1.0 / (2 * t + 2), 0.0, 1.0))

    decoded_bits = _symbols_to_bits(decoded, m)[: k * m]
    decoded_bytes = bits_to_bytes(decoded_bits)
    crc_count = _count_crc_valid(decoded_bytes)

    return ReedSolomonResult(
        decoded_bits=decoded_bits,
        n_input_bits=n * m,
        n_output_bits=k * m,
        corrected_symbols=corrected_errors + corrected_erasures,
        corrected_erasures=corrected_erasures,
        crc_valid_count=crc_count,
        confidence=float(np.clip(confidence, 0.0, 1.0)),
        warnings=warnings,
        syndrome_zero=syndrome_zero,
    )