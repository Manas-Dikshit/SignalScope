from __future__ import annotations

import numpy as np


def bits_to_bytes(bits: np.ndarray) -> bytes:
    n = len(bits) - (len(bits) % 8)
    bits = bits[:n]
    packed = np.packbits(bits.astype(np.uint8))
    return bytes(packed)


def crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def validate_crc16(payload: bytes, received_crc: int, poly: int = 0x1021, init: int = 0xFFFF) -> bool:
    return crc16_ccitt(payload, poly, init) == received_crc


def find_sync_word(bits: np.ndarray, sync_pattern: np.ndarray, max_hamming: int = 0) -> list[dict]:
    """Sliding-window search for a known sync word / preamble in a bitstream.
    Returns a list of {offset, hamming_distance} matches within max_hamming."""
    matches = []
    p_len = len(sync_pattern)
    if p_len == 0 or len(bits) < p_len:
        return matches
    for offset in range(len(bits) - p_len + 1):
        window = bits[offset: offset + p_len]
        dist = int(np.sum(window != sync_pattern))
        if dist <= max_hamming:
            matches.append({"offset": offset, "hamming_distance": dist})
    return matches
