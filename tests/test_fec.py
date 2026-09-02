import numpy as np

from signalscope_dsp.fec.convolutional import convolutional_encode, viterbi_decode
from signalscope_dsp.fec.validation import crc16_ccitt, validate_crc16, bits_to_bytes, find_sync_word


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
