import numpy as np

from signalscope_dsp.fec.convolutional import convolutional_encode, viterbi_decode
from signalscope_dsp.fec.validation import crc16_ccitt, validate_crc16, bits_to_bytes, find_sync_word
from signalscope_dsp.fec.reed_solomon import reed_solomon_encode, reed_solomon_decode
from signalscope_dsp.fec.ldpc import ldpc_decode


def test_convolutional_round_trip_no_noise():
    rng = np.random.default_rng(0)
    bits = rng.integers(0, 2, size=200).astype(np.uint8)
    coded = convolutional_encode(bits)
    result = viterbi_decode(coded)
    # allow the decoder's own tail-handling slop but core payload must match
    n = min(len(bits), len(result.decoded_bits))
    assert np.array_equal(bits[:n], result.decoded_bits[:n])


def test_convolutional_corrects_some_errors():
    rng = np.random.default_rng(1)
    bits = rng.integers(0, 2, size=500).astype(np.uint8)
    coded = convolutional_encode(bits)
    noisy = coded.copy()
    # flip ~2% of coded bits (well within a rate-1/2 K=7 code's correction ability)
    n_flips = int(0.02 * len(noisy))
    flip_idx = rng.choice(len(noisy), size=n_flips, replace=False)
    noisy[flip_idx] ^= 1
    result = viterbi_decode(noisy)
    n = min(len(bits), len(result.decoded_bits))
    ber = np.mean(bits[:n] != result.decoded_bits[:n])
    assert ber < 0.05


def test_crc16_round_trip():
    payload = b"hello signalscope"
    crc = crc16_ccitt(payload)
    assert validate_crc16(payload, crc)
    assert not validate_crc16(payload + b"x", crc)


def test_bits_to_bytes():
    bits = np.array([0, 1, 1, 0, 0, 0, 0, 1], dtype=np.uint8)  # 0x61 = 'a'
    b = bits_to_bytes(bits)
    assert b == bytes([0x61])


def test_find_sync_word():
    bits = np.array([1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 0], dtype=np.uint8)
    sync = np.array([1, 0, 1, 0, 1, 1], dtype=np.uint8)
    matches = find_sync_word(bits, sync, max_hamming=0)
    offsets = [m["offset"] for m in matches]
    assert 0 in offsets
    assert 8 in offsets


def test_reed_solomon_corrects_symbol_errors():
    payload = b"signalscope RS payload"
    encoded = bytearray(reed_solomon_encode(payload, parity_symbols=16))
    encoded[2] ^= 0x55
    encoded[-3] ^= 0x11
    result = reed_solomon_decode(bytes(encoded), parity_symbols=16)
    assert result.valid
    assert result.decoded_bytes == payload
    assert result.corrected_symbols == 2


def test_ldpc_min_sum_satisfies_parity_checks():
    parity = np.array([[1, 1, 0, 1], [0, 1, 1, 1]], dtype=np.uint8)
    result = ldpc_decode(np.array([4.0, 4.0, 4.0, 4.0]), parity)
    assert result.parity_satisfied
    assert np.array_equal((parity @ result.decoded_bits) % 2, np.zeros(2, dtype=np.uint8))
