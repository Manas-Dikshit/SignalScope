"""SignalScope AI — Sample Signal Generator
Generates sample .wav (stereo I/Q and mono) and .iq files for testing.
"""

import os
from pathlib import Path
import numpy as np
from scipy.io import wavfile

try:
    from signalscope_dsp.synth import SynthConfig, generate_signal
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "dsp-worker"))
    from signalscope_dsp.synth import SynthConfig, generate_signal


def main():
    out_dir = Path(__file__).resolve().parent.parent / "samples"
    out_dir.mkdir(exist_ok=True)

    print(f"Generating sample signals in {out_dir} ...")

    # 1. QPSK Stereo I/Q WAV (48 kHz sample rate)
    cfg_qpsk = SynthConfig(
        modulation="qpsk",
        sample_rate_hz=48_000.0,
        symbol_rate_hz=2_400.0,
        carrier_offset_hz=0.0,
        snr_db=25.0,
        n_symbols=4000,
    )
    sig_qpsk = generate_signal(cfg_qpsk).samples
    norm_i = np.clip(np.real(sig_qpsk) * 16000, -32767, 32767).astype(np.int16)
    norm_q = np.clip(np.imag(sig_qpsk) * 16000, -32767, 32767).astype(np.int16)
    stereo_qpsk = np.stack([norm_i, norm_q], axis=1)
    qpsk_path = out_dir / "sample_qpsk_48k.wav"
    wavfile.write(str(qpsk_path), 48_000, stereo_qpsk)
    print(f"  [+] Created {qpsk_path.name}")

    # 2. 2FSK Stereo I/Q WAV (48 kHz sample rate)
    cfg_fsk = SynthConfig(
        modulation="2fsk",
        sample_rate_hz=48_000.0,
        symbol_rate_hz=1_200.0,
        fsk_deviation_hz=1_200.0,
        carrier_offset_hz=0.0,
        snr_db=20.0,
        n_symbols=2000,
    )
    sig_fsk = generate_signal(cfg_fsk).samples
    fsk_i = np.clip(np.real(sig_fsk) * 16000, -32767, 32767).astype(np.int16)
    fsk_q = np.clip(np.imag(sig_fsk) * 16000, -32767, 32767).astype(np.int16)
    stereo_fsk = np.stack([fsk_i, fsk_q], axis=1)
    fsk_path = out_dir / "sample_2fsk_48k.wav"
    wavfile.write(str(fsk_path), 48_000, stereo_fsk)
    print(f"  [+] Created {fsk_path.name}")

    # 3. Raw interleaved int16 I/Q
    raw_iq = np.empty(2 * len(sig_qpsk), dtype=np.int16)
    raw_iq[0::2] = norm_i
    raw_iq[1::2] = norm_q
    iq_path = out_dir / "sample_qpsk_interleaved_int16.iq"
    raw_iq.tofile(str(iq_path))
    print(f"  [+] Created {iq_path.name}")

    print("\nDone! You can upload any of these files in SignalScope at http://localhost:3000")


if __name__ == "__main__":
    main()
