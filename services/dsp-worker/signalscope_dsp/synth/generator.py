from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..fec.convolutional import convolutional_encode


def _rc_filter(beta: float, span: int, sps: int) -> np.ndarray:
    """Full raised-cosine pulse. Used (instead of root-raised-cosine) as the sole
    transmit-side pulse shape because this MVP's demodulators sample symbol centers
    directly without a matched receive filter — RC gives zero inter-symbol
    interference at symbol-spaced sample instants on its own, whereas RRC only does
    when paired with an identical matched filter at the receiver."""
    n = span * sps
    t = (np.arange(-n / 2, n / 2 + 1)) / sps
    h = np.zeros_like(t)
    for i, ti in enumerate(t):
        if abs(1 - (2 * beta * ti) ** 2) < 1e-8:
            h[i] = (np.pi / 4) * np.sinc(1 / (2 * beta))
        else:
            h[i] = np.sinc(ti) * np.cos(np.pi * beta * ti) / (1 - (2 * beta * ti) ** 2)
    return h / np.sum(h)


def _rrc_filter(beta: float, span: int, sps: int) -> np.ndarray:
    n = span * sps
    t = (np.arange(-n / 2, n / 2 + 1)) / sps
    h = np.zeros_like(t)
    for i, ti in enumerate(t):
        if abs(ti) < 1e-8:
            h[i] = 1.0 - beta + 4 * beta / np.pi
        elif beta != 0 and abs(abs(ti) - 1 / (4 * beta)) < 1e-8:
            h[i] = (beta / np.sqrt(2)) * (
                (1 + 2 / np.pi) * np.sin(np.pi / (4 * beta)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta))
            )
        else:
            num = np.sin(np.pi * ti * (1 - beta)) + 4 * beta * ti * np.cos(np.pi * ti * (1 + beta))
            den = np.pi * ti * (1 - (4 * beta * ti) ** 2)
            h[i] = num / den
    return h / np.sqrt(np.sum(h ** 2))


@dataclass
class SynthConfig:
    modulation: str = "qpsk"  # ook, 2fsk, 4fsk, bpsk, qpsk, 8psk, 16qam, 64qam
    sample_rate_hz: float = 200_000.0
    symbol_rate_hz: float = 10_000.0
    carrier_offset_hz: float = 5_000.0
    snr_db: float = 15.0
    n_symbols: int = 2000
    fsk_deviation_hz: float = 5_000.0
    rrc_beta: float = 0.35
    rrc_span: int = 8
    apply_conv_code: bool = False
    burst: bool = False
    burst_on_symbols: int = 500
    burst_off_symbols: int = 300
    seed: Optional[int] = 42


@dataclass
class SynthResult:
    samples: np.ndarray
    bits: np.ndarray             # ground-truth payload bits (pre-FEC if apply_conv_code)
    coded_bits: Optional[np.ndarray]
    sps: int
    config: SynthConfig


_MOD_ORDERS = {
    "ook": 2, "2fsk": 2, "4fsk": 4, "bpsk": 2, "qpsk": 4, "8psk": 8, "16qam": 16, "64qam": 64,
}


def generate_signal(cfg: SynthConfig) -> SynthResult:
    rng = np.random.default_rng(cfg.seed)
    sps = max(2, int(round(cfg.sample_rate_hz / cfg.symbol_rate_hz)))
    order = _MOD_ORDERS[cfg.modulation]
    bits_per_symbol = int(np.log2(order))

    payload_bits = rng.integers(0, 2, size=cfg.n_symbols * bits_per_symbol).astype(np.uint8)
    coded_bits = None
    tx_bits = payload_bits
    if cfg.apply_conv_code:
        coded_bits = convolutional_encode(payload_bits)
        tx_bits = coded_bits
        # re-derive n_symbols from coded stream length for the chosen modulation
        n_sym = len(tx_bits) // bits_per_symbol
        tx_bits = tx_bits[: n_sym * bits_per_symbol]

    n_sym = len(tx_bits) // bits_per_symbol
    sym_ints = np.zeros(n_sym, dtype=int)
    for i in range(n_sym):
        chunk = tx_bits[i * bits_per_symbol:(i + 1) * bits_per_symbol]
        val = 0
        for b in chunk:
            val = (val << 1) | int(b)
        sym_ints[i] = val

    if cfg.modulation in ("bpsk", "qpsk", "8psk"):
        angles = 2 * np.pi * sym_ints / order
        symbols = np.exp(1j * angles)
    elif cfg.modulation == "ook":
        symbols = sym_ints.astype(np.complex128)  # 0 or 1
    elif cfg.modulation in ("2fsk", "4fsk"):
        symbols = None  # handled via direct FM synthesis below
    elif cfg.modulation in ("16qam", "64qam"):
        side = int(np.sqrt(order))
        levels = np.arange(-(side - 1), side, 2)
        i_idx = sym_ints // side
        q_idx = sym_ints % side
        symbols = (levels[i_idx] + 1j * levels[q_idx]).astype(np.complex128)
        symbols = symbols / np.max(np.abs(symbols))
    else:
        raise ValueError(f"Unknown modulation: {cfg.modulation}")

    if cfg.modulation in ("2fsk", "4fsk"):
        tone_count = order
        tones = np.linspace(-cfg.fsk_deviation_hz, cfg.fsk_deviation_hz, tone_count)
        freq_per_symbol = tones[sym_ints]
        freq_samples = np.repeat(freq_per_symbol, sps)
        phase = 2 * np.pi * np.cumsum(freq_samples) / cfg.sample_rate_hz
        baseband = np.exp(1j * phase)
    else:
        # Rectangular (NRZ) pulse shaping: each symbol held constant for `sps` samples.
        # This MVP's demodulators sample symbol centers directly with no receive-side
        # matched filter, so a band-limited RRC/RC pulse (which requires matched
        # filtering to be ISI-free) is deliberately not used here — rectangular
        # pulses are exactly ISI-free for a naive center-sample receiver, at the
        # cost of a wider occupied bandwidth than a real band-limited transmitter
        # would use. A pulse-shaped + matched-filter receive chain is a natural
        # follow-up once timing/carrier recovery loops are added.
        baseband = np.repeat(symbols, sps)

    if cfg.burst:
        on = cfg.burst_on_symbols * sps
        off = cfg.burst_off_symbols * sps
        mask = np.zeros(len(baseband))
        pos = 0
        state_on = True
        while pos < len(mask):
            length = on if state_on else off
            mask[pos: pos + length] = 1.0 if state_on else 0.0
            pos += length
            state_on = not state_on
        baseband = baseband * mask

    t = np.arange(len(baseband)) / cfg.sample_rate_hz
    carrier = np.exp(1j * 2 * np.pi * cfg.carrier_offset_hz * t)
    passband = baseband * carrier

    sig_power = np.mean(np.abs(passband) ** 2) + 1e-20
    snr_linear = 10 ** (cfg.snr_db / 10)
    noise_power = sig_power / snr_linear
    noise = np.sqrt(noise_power / 2) * (rng.standard_normal(len(passband)) + 1j * rng.standard_normal(len(passband)))
    samples = (passband + noise).astype(np.complex64)

    return SynthResult(samples=samples, bits=payload_bits, coded_bits=coded_bits, sps=sps, config=cfg)
