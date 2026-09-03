"""SignalScope AI — lean MVP.

Offline, explainable RF signal-analysis workbench for authorized .IQ / .wav /
SigMF recordings. No live capture, no decryption of protected communications —
this tool only analyzes files you already have.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from signalscope_dsp import __version__
from signalscope_dsp.common import Estimate, Source, Recording, RecordingMetadata
from signalscope_dsp.io import load_wav, load_raw_iq, load_sigmf, RawIQFormat
from signalscope_dsp.preprocessing import ConditioningConfig, condition_signal, shift_frequency
from signalscope_dsp.features import compute_psd, compute_waterfall, extract_spectral_features
from signalscope_dsp.detection import detect_bursts, burst_stats
from signalscope_dsp.modulation import classify_modulation, estimate_symbol_rate_candidates
from signalscope_dsp.demodulation import demod_psk, demod_qam, demod_fsk
from signalscope_dsp.interleaving.block import (
    block_deinterleave, convolutional_deinterleave, score_deinterleave_candidate,
)
from signalscope_dsp.fec.convolutional import viterbi_decode
from signalscope_dsp.fec.validation import bits_to_bytes, crc16_ccitt
from signalscope_dsp.correlation.correlate import sliding_pattern_match, find_repeated_sequences
from signalscope_dsp.synth import SynthConfig, generate_signal

st.set_page_config(page_title="SignalScope AI", layout="wide", page_icon="📡")

MOD_LABEL_TO_KEY = {
    "OOK/ASK": "ook", "2-FSK": "2fsk", "4-FSK": "4fsk", "BPSK": "bpsk",
    "QPSK": "qpsk", "8-PSK": "8psk", "16-QAM": "16qam", "64-QAM": "64qam",
}


def confidence_badge(conf: float | None) -> str:
    if conf is None:
        return ""
    if conf >= 0.7:
        return f"🟢 {conf:.2f}"
    if conf >= 0.4:
        return f"🟡 {conf:.2f}"
    return f"🔴 {conf:.2f}"


def source_badge(source: Source) -> str:
    icons = {
        Source.METADATA: "📄 metadata (exact)",
        Source.USER_SUPPLIED: "✍️ user supplied (exact)",
        Source.MEASURED: "📏 measured (exact)",
        Source.ESTIMATED: "🧮 estimated",
        Source.HYPOTHESIS: "🔎 hypothesis",
        Source.UNKNOWN: "❓ unknown",
    }
    return icons.get(source, str(source))


def render_estimate(label: str, est: Estimate | None, unit_suffix: str = ""):
    if est is None or est.value is None:
        st.metric(label, "unknown")
        if est and est.warnings:
            st.caption("⚠️ " + " ".join(est.warnings))
        return
    value_str = f"{est.value:,.2f}" if isinstance(est.value, float) else str(est.value)
    st.metric(label, f"{value_str}{unit_suffix}")
    line = source_badge(est.source)
    if est.confidence is not None:
        line += f"  ·  confidence {confidence_badge(est.confidence)}"
    st.caption(line)
    if est.evidence:
        with st.expander("Evidence", expanded=False):
            for e in est.evidence:
                st.write("• " + e)
    if est.alternatives:
        with st.expander("Alternative hypotheses", expanded=False):
            for a in est.alternatives:
                st.write(f"• **{a.value}** — confidence {confidence_badge(a.confidence)}")
                for e in a.evidence:
                    st.caption("   " + e)
    if est.warnings:
        for w in est.warnings:
            st.caption("⚠️ " + w)


def plot_time_waveform(samples, fs, max_points=20000):
    n = len(samples)
    step = max(1, n // max_points)
    idx = np.arange(0, n, step)
    t = idx / fs if fs else idx
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=t, y=samples.real[idx], name="I", line=dict(width=1)))
    fig.add_trace(go.Scattergl(x=t, y=samples.imag[idx], name="Q", line=dict(width=1)))
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10),
                       xaxis_title="Time (s)" if fs else "Sample index", yaxis_title="Amplitude",
                       title=f"Time waveform{' (downsampled for display)' if step > 1 else ''}")
    return fig


def plot_psd(freqs, psd_db, title="Power spectral density"):
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=freqs, y=psd_db, line=dict(width=1)))
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10),
                       xaxis_title="Frequency (Hz, relative to center)", yaxis_title="Power (dB)", title=title)
    return fig


def plot_waterfall(freqs, times, sxx_db):
    fig = go.Figure(data=go.Heatmap(z=sxx_db, x=freqs, y=times, colorscale="Viridis"))
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=30, b=10),
                       xaxis_title="Frequency (Hz)", yaxis_title="Time (s)", title="Waterfall / spectrogram")
    return fig


def plot_iq_scatter(samples, max_points=5000, title="I/Q scatter"):
    n = len(samples)
    step = max(1, n // max_points)
    idx = np.arange(0, n, step)
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=samples.real[idx], y=samples.imag[idx], mode="markers",
                                marker=dict(size=3, opacity=0.5)))
    fig.update_layout(height=400, width=400, margin=dict(l=10, r=10, t=30, b=10),
                       xaxis_title="I", yaxis_title="Q", title=title, yaxis=dict(scaleanchor="x"))
    return fig


def plot_bit_timeline(bits, max_points=2000, title="Bit timeline"):
    n = len(bits)
    step = max(1, n // max_points)
    idx = np.arange(0, n, step)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=idx, y=bits[idx], mode="lines", line_shape="hv", line=dict(width=1)))
    fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10), title=title,
                       yaxis=dict(tickvals=[0, 1]), xaxis_title="Bit index")
    return fig


# ---------------------------------------------------------------------------
# Sidebar: data source
# ---------------------------------------------------------------------------

st.sidebar.title("📡 SignalScope AI")
st.sidebar.caption(f"v{__version__} · offline, explainable RF analysis")
st.sidebar.info(
    "For **authorized, offline** .IQ / .WAV / SigMF recordings only. No live "
    "capture, geolocation, or decryption of protected communications.",
    icon="🔒",
)

source_choice = st.sidebar.radio(
    "Load a recording",
    ["Generate synthetic demo signal", "Upload WAV", "Upload raw IQ", "Upload SigMF"],
)

if "recording" not in st.session_state:
    st.session_state.recording = None
    st.session_state.ground_truth = None

if source_choice == "Generate synthetic demo signal":
    st.sidebar.subheader("Synthetic signal generator")
    mod = st.sidebar.selectbox("Modulation", list(MOD_LABEL_TO_KEY.keys()), index=4)
    sample_rate = st.sidebar.number_input("Sample rate (Hz)", value=200_000, step=10_000)
    symbol_rate = st.sidebar.number_input("Symbol rate (Hz)", value=10_000, step=1_000)
    carrier_offset = st.sidebar.number_input("Carrier offset (Hz)", value=5_000, step=500)
    snr_db = st.sidebar.slider("SNR (dB)", -5, 40, 20)
    n_symbols = st.sidebar.number_input("Number of symbols", value=2000, step=100)
    apply_fec = st.sidebar.checkbox("Apply rate-1/2 convolutional coding (K=7)", value=False)
    burst_mode = st.sidebar.checkbox("Bursty (on/off) signal", value=False)
    if st.sidebar.button("Generate", type="primary"):
        cfg = SynthConfig(
            modulation=MOD_LABEL_TO_KEY[mod], sample_rate_hz=float(sample_rate),
            symbol_rate_hz=float(symbol_rate), carrier_offset_hz=float(carrier_offset),
            snr_db=float(snr_db), n_symbols=int(n_symbols), apply_conv_code=apply_fec, burst=burst_mode,
        )
        result = generate_signal(cfg)
        metadata = RecordingMetadata(
            sample_rate=Estimate("sample_rate", cfg.sample_rate_hz, "Hz", Source.USER_SUPPLIED,
                                  evidence=["Synthetic generator configuration"]),
            center_frequency=Estimate("center_frequency", 0.0, "Hz", Source.USER_SUPPLIED,
                                       evidence=["Synthetic baseband recording"]),
            is_complex=True, channel_count=1, sample_dtype="complex64",
            duration_seconds=len(result.samples) / cfg.sample_rate_hz, total_samples=len(result.samples),
            extra={"synthetic": True, "warnings": []},
        )
        rec = Recording(samples=result.samples, metadata=metadata, source_path="<synthetic>")
        st.session_state.recording = rec
        st.session_state.ground_truth = {"bits": result.bits, "sps": result.sps, "cfg": cfg}
        st.sidebar.success(f"Generated {len(result.samples):,} samples of {mod}.")

elif source_choice == "Upload WAV":
    up = st.sidebar.file_uploader("WAV file", type=["wav"])
    stereo_mode = st.sidebar.selectbox(
        "Stereo interpretation", ["left_is_i_right_is_q", "left_only", "right_only", "mono_mix"])
    if up is not None and st.sidebar.button("Load WAV", type="primary"):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(up.getvalue())
            tmp_path = tmp.name
        rec = load_wav(tmp_path, stereo_mode=stereo_mode)
        st.session_state.recording = rec
        st.session_state.ground_truth = None
        st.sidebar.success(f"Loaded {len(rec.samples):,} samples.")

elif source_choice == "Upload raw IQ":
    up = st.sidebar.file_uploader("Raw IQ file", type=["iq", "bin", "dat", "raw"])
    st.sidebar.caption("Raw IQ files aren't self-describing — set the format explicitly:")
    dtype = st.sidebar.selectbox("Sample dtype", ["int8", "uint8", "int16", "uint16", "int32", "float32", "float64"])
    layout = st.sidebar.selectbox("Layout", ["interleaved", "separate_iq", "real_only"])
    endian = st.sidebar.selectbox("Endianness", ["little", "big"])
    has_sr = st.sidebar.checkbox("I know the sample rate", value=True)
    sample_rate_hz = st.sidebar.number_input("Sample rate (Hz)", value=1_000_000, step=10_000) if has_sr else None
    has_cf = st.sidebar.checkbox("I know the center frequency", value=False)
    center_freq_hz = st.sidebar.number_input("Center frequency (Hz)", value=915_000_000, step=1000) if has_cf else None
    if up is not None and st.sidebar.button("Load raw IQ", type="primary"):
        with tempfile.NamedTemporaryFile(suffix=".iq", delete=False) as tmp:
            tmp.write(up.getvalue())
            tmp_path = tmp.name
        fmt = RawIQFormat(dtype=dtype, layout=layout, endian=endian,
                           sample_rate_hz=float(sample_rate_hz) if sample_rate_hz else None,
                           center_frequency_hz=float(center_freq_hz) if center_freq_hz else None)
        rec = load_raw_iq(tmp_path, fmt)
        st.session_state.recording = rec
        st.session_state.ground_truth = None
        st.sidebar.success(f"Loaded {len(rec.samples):,} samples.")

elif source_choice == "Upload SigMF":
    meta_up = st.sidebar.file_uploader("SigMF metadata (.sigmf-meta)", type=["sigmf-meta", "json"])
    data_up = st.sidebar.file_uploader("SigMF data (.sigmf-data)", type=["sigmf-data", "bin", "dat"])
    if meta_up is not None and data_up is not None and st.sidebar.button("Load SigMF", type="primary"):
        tmpdir = Path(tempfile.mkdtemp())
        meta_path = tmpdir / "rec.sigmf-meta"
        data_path = tmpdir / "rec.sigmf-data"
        meta_path.write_bytes(meta_up.getvalue())
        data_path.write_bytes(data_up.getvalue())
        rec = load_sigmf(meta_path)
        st.session_state.recording = rec
        st.session_state.ground_truth = None
        st.sidebar.success(f"Loaded {len(rec.samples):,} samples.")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

rec = st.session_state.recording

if rec is None:
    st.title("📡 SignalScope AI")
    st.write(
        "An offline, explainable workbench for analyzing authorized .IQ, .WAV, and "
        "SigMF recordings. Load a recording from the sidebar, or generate a "
        "synthetic demo signal to try the pipeline immediately — no external "
        "dataset required."
    )
    st.write(
        "Every number this tool reports is tagged with where it came from: "
        "**metadata** and **measured** values are exact; **estimated** values and "
        "**hypotheses** carry a confidence score and evidence, and are never "
        "presented as certainties."
    )
    st.stop()

fs = rec.metadata.sample_rate.value
n_total = len(rec.samples)
duration = rec.duration_s()

st.title("📡 SignalScope AI — Analysis Workspace")

st.subheader("Region of interest")
if fs and not np.isnan(duration):
    t0, t1 = st.slider("Select time range (s)", 0.0, float(duration),
                        (0.0, float(duration)), key="time_range")
    start_sample = int(t0 * fs)
    end_sample = int(t1 * fs)
else:
    st.caption("Sample rate unknown — selecting by raw sample index instead of time.")
    start_sample, end_sample = st.slider("Sample range", 0, n_total, (0, n_total), key="sample_range")
end_sample = max(end_sample, start_sample + 16)
segment = rec.samples[start_sample:end_sample]
st.caption(f"Analyzing {len(segment):,} of {n_total:,} samples ({start_sample:,}–{end_sample:,}).")

tabs = st.tabs([
    "Overview", "Waveform & Spectrum", "Waterfall", "I/Q & Constellation",
    "Detection & Features", "Modulation & Symbol Rate", "Demodulation",
    "De-interleave & FEC", "Correlation", "Export",
])

with tabs[0]:
    st.subheader("File & metadata")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_estimate("Sample rate", rec.metadata.sample_rate, " Hz")
    with c2:
        render_estimate("Center frequency", rec.metadata.center_frequency, " Hz")
    with c3:
        st.metric("Total samples", f"{n_total:,}")
        st.caption("📏 measured (exact)")
    with c4:
        st.metric("Duration", f"{duration:.4f} s" if not np.isnan(duration) else "unknown")
        st.caption("📏 measured (exact)" if fs else "❓ unknown (needs sample rate)")

    st.write(f"**Source:** `{rec.source_path}`  ·  **Complex I/Q:** {rec.metadata.is_complex}  ·  "
             f"**Channels:** {rec.metadata.channel_count}  ·  **Dtype:** {rec.metadata.sample_dtype}")

    warnings = rec.metadata.extra.get("warnings", [])
    if warnings:
        st.warning("\n\n".join(f"⚠️ {w}" for w in warnings))

    if rec.metadata.extra.get("synthetic"):
        gt = st.session_state.ground_truth
        st.info(
            f"This is a **synthetic** recording. Ground truth: modulation="
            f"`{gt['cfg'].modulation}`, symbol_rate={gt['cfg'].symbol_rate_hz:.0f} Hz, "
            f"carrier_offset={gt['cfg'].carrier_offset_hz:.0f} Hz, SNR={gt['cfg'].snr_db} dB. "
            "Ground truth is shown here for validation — a real recording would not "
            "provide this."
        )

with tabs[1]:
    st.subheader("Time-domain waveform")
    st.plotly_chart(plot_time_waveform(segment, fs or 1.0), use_container_width=True)

    st.subheader("Power spectral density")
    fft_size = st.select_slider("FFT size", options=[256, 512, 1024, 2048, 4096, 8192], value=2048, key="psd_fft")
    if fs:
        freqs, psd_db = compute_psd(segment, fs, fft_size)
        st.plotly_chart(plot_psd(freqs, psd_db), use_container_width=True)
    else:
        st.warning("Sample rate unknown — cannot label a frequency axis. Supply one via the raw-IQ import dialog.")

with tabs[2]:
    st.subheader("Waterfall / spectrogram")
    if fs:
        wf_fft = st.select_slider("FFT size", options=[128, 256, 512, 1024, 2048], value=512, key="wf_fft")
        overlap = st.slider("Overlap fraction", 0.0, 0.9, 0.5, key="wf_overlap")
        freqs, times, sxx_db = compute_waterfall(segment, fs, wf_fft, overlap)
        st.plotly_chart(plot_waterfall(freqs, times, sxx_db), use_container_width=True)
    else:
        st.warning("Sample rate unknown — waterfall time/frequency axes cannot be labeled.")

with tabs[3]:
    st.subheader("I/Q scatter")
    st.plotly_chart(plot_iq_scatter(segment), use_container_width=False)
    st.caption(
        "Raw I/Q scatter before carrier/timing recovery — a decided constellation "
        "is available on the Demodulation tab after running a demodulator."
    )

with tabs[4]:
    st.subheader("Burst detection")
    if fs:
        thresh = st.slider("Threshold above noise floor (dB)", 1.0, 20.0, 6.0)
        bursts = detect_bursts(segment, fs, threshold_db_above_floor=thresh)
        st.write(f"Detected **{len(bursts)}** burst(s).")
        if bursts:
            df = pd.DataFrame([{
                "start_s": b.start_time_s, "end_s": b.end_time_s,
                "duration_s": b.end_time_s - b.start_time_s,
                "peak_dB": b.peak_power_db, "confidence": b.confidence,
            } for b in bursts])
            st.dataframe(df, use_container_width=True)
            stats = burst_stats(bursts)
            c1, c2, c3 = st.columns(3)
            with c1:
                render_estimate("Mean burst duration", stats["burst_duration_s"], " s")
            with c2:
                render_estimate("Repetition interval", stats["repetition_interval_s"], " s")
            with c3:
                render_estimate("Duty cycle", stats["duty_cycle"])
    else:
        st.warning("Sample rate unknown — burst timing cannot be computed.")

    st.subheader("Spectral & statistical features")
    if fs:
        feats = extract_spectral_features(segment, fs)
        c1, c2, c3 = st.columns(3)
        with c1:
            render_estimate("Occupied bandwidth", feats.occupied_bandwidth_hz, " Hz")
            render_estimate("Peak frequency", feats.peak_frequency_hz, " Hz")
        with c2:
            render_estimate("Spectral centroid", feats.spectral_centroid_hz, " Hz")
            render_estimate("SNR", feats.snr_db, " dB")
        with c3:
            render_estimate("Crest factor", feats.crest_factor)
            render_estimate("Spectral flatness", feats.spectral_flatness)

with tabs[5]:
    st.subheader("Modulation classification")
    hyps = classify_modulation(segment, fs or 1.0)
    for i, h in enumerate(hyps):
        marker = "🥇" if i == 0 else ("🥈" if i == 1 else "🥉")
        st.write(f"{marker} **{h.label}** — confidence {confidence_badge(h.confidence)}")
        for e in h.evidence:
            st.caption("   " + e)
    st.caption(
        "This is a hypothesis from handcrafted, explainable features (envelope "
        "variance, M-th-power spectral peakiness, tone/ring clustering) — never a "
        "certainty."
    )

    st.subheader("Symbol-rate candidates")
    if fs:
        candidates = estimate_symbol_rate_candidates(segment, fs)
        for c in candidates:
            render_estimate(f"Candidate: {c.value} Hz" if c.value else "Symbol rate", c)
    else:
        st.warning("Sample rate unknown — symbol rate cannot be estimated in Hz.")

with tabs[6]:
    st.subheader("Configure & run demodulation")
    mod_choice = st.selectbox("Modulation", list(MOD_LABEL_TO_KEY.keys()), key="demod_mod")
    mod_key = MOD_LABEL_TO_KEY[mod_choice]

    default_sr = 10_000.0
    gt = st.session_state.ground_truth
    if gt and gt["cfg"].modulation == mod_key:
        default_sr = gt["cfg"].symbol_rate_hz
    symbol_rate_hz = st.number_input("Symbol rate (Hz)", value=float(default_sr), step=100.0)
    sps = max(2, int(round((fs or 1.0) / symbol_rate_hz))) if fs else 1
    st.caption(f"→ {sps} samples/symbol at the current sample rate.")

    carrier_offset_default = float(gt["cfg"].carrier_offset_hz) if (gt and gt["cfg"].modulation == mod_key) else 0.0
    remove_carrier = st.checkbox("Remove a known carrier offset before demodulating", value=bool(carrier_offset_default))
    carrier_offset_hz = st.number_input("Carrier offset (Hz)", value=carrier_offset_default) if remove_carrier else 0.0

    if st.button("Run demodulation", type="primary"):
        work = segment
        if remove_carrier and fs:
            work = shift_frequency(work, fs, carrier_offset_hz)
        cond = condition_signal(work, fs or 1.0, ConditioningConfig(coarse_freq_correction=False))

        if mod_key in ("bpsk", "qpsk", "8psk"):
            order = {"bpsk": 2, "qpsk": 4, "8psk": 8}[mod_key]
            result = demod_psk(cond.samples, order, sps)
        elif mod_key in ("16qam", "64qam"):
            order = {"16qam": 16, "64qam": 64}[mod_key]
            result = demod_qam(cond.samples, order, sps)
        elif mod_key in ("2fsk", "4fsk"):
            order = {"2fsk": 2, "4fsk": 4}[mod_key]
            result = demod_fsk(cond.samples, fs or 1.0, order, sps)
        else:
            result = demod_psk(cond.samples, 2, sps)  # OOK fallback: on/off treated as BPSK-like slicing
        st.session_state.demod_result = result

        st.success(f"Decoded {len(result.hard_bits):,} bits from {len(result.symbols):,} symbols.")
        for w in result.warnings:
            st.caption("⚠️ " + w)

        st.plotly_chart(plot_iq_scatter(result.symbols, title="Decided constellation"), use_container_width=False)
        st.plotly_chart(plot_bit_timeline(result.hard_bits), use_container_width=True)

        if gt and gt["cfg"].modulation == mod_key:
            n = min(len(gt["bits"]), len(result.hard_bits))
            ber = float(np.mean(gt["bits"][:n] != result.hard_bits[:n]))
            st.metric("Bit error rate vs. synthetic ground truth", f"{ber:.3%}")

        st.download_button("Download hard bits (0/1 text)", "".join(str(b) for b in result.hard_bits),
                            file_name="hard_bits.txt")

with tabs[7]:
    st.subheader("De-interleaving")
    if "demod_result" not in st.session_state:
        st.info("Run demodulation first to get a bit stream to de-interleave.")
    else:
        bits = st.session_state.demod_result.hard_bits
        interleaver_type = st.selectbox("Interleaver type", ["none", "block", "convolutional"])
        if interleaver_type == "block":
            rows = st.number_input("Rows", value=8, min_value=1)
            cols = st.number_input("Cols", value=8, min_value=1)
            if st.button("Apply block de-interleaver"):
                out = block_deinterleave(bits, rows, cols)
                score = score_deinterleave_candidate(out)
                st.session_state.deinterleaved_bits = out
                st.metric("Validation score (heuristic, not proof)", f"{score:.2f}")
                st.plotly_chart(plot_bit_timeline(out, title="De-interleaved bits"), use_container_width=True)
        elif interleaver_type == "convolutional":
            n_branches = st.number_input("Branches", value=4, min_value=2)
            delay_step = st.number_input("Delay step", value=3, min_value=1)
            if st.button("Apply convolutional de-interleaver"):
                out = convolutional_deinterleave(bits, n_branches, delay_step)
                score = score_deinterleave_candidate(out)
                st.session_state.deinterleaved_bits = out
                st.metric("Validation score (heuristic, not proof)", f"{score:.2f}")
                st.plotly_chart(plot_bit_timeline(out, title="De-interleaved bits"), use_container_width=True)
        else:
            st.session_state.deinterleaved_bits = bits
            st.caption("No de-interleaving applied — passing demodulated bits through.")

    st.subheader("FEC decoding (rate-1/2 convolutional, Viterbi)")
    bits_for_fec = None
    if "deinterleaved_bits" in st.session_state:
        bits_for_fec = st.session_state.deinterleaved_bits
    elif "demod_result" in st.session_state:
        bits_for_fec = st.session_state.demod_result.hard_bits

    if bits_for_fec is None:
        st.info("Run demodulation (and optionally de-interleaving) first.")
    else:
        constraint_length = st.number_input("Constraint length K", value=7, min_value=3, max_value=9)
        if st.button("Run Viterbi decode"):
            result = viterbi_decode(bits_for_fec, constraint_length=constraint_length)
            st.session_state.fec_result = result
            st.write(f"Decoded {len(result.decoded_bits):,} bits. Best path metric: {result.path_metric:.1f} "
                     f"(lower is better — 0 means a perfect match to some codeword).")
            for w in result.warnings:
                st.caption("⚠️ " + w)
            st.plotly_chart(plot_bit_timeline(result.decoded_bits, title="FEC-decoded bits"), use_container_width=True)

            payload = bits_to_bytes(result.decoded_bits)
            st.write(f"As bytes (first 64): `{payload[:64].hex()}`")
            if len(payload) > 2:
                crc = crc16_ccitt(payload[:-2])
                received_crc = int.from_bytes(payload[-2:], "big")
                valid = crc == received_crc
                st.write(f"CRC-16 check (last 2 bytes as CRC): {'✅ valid' if valid else '❌ does not match'}")
                st.caption(
                    "Matching CRC or readable bytes are evidence of correct decoding, not proof by "
                    "themselves — corroborate with sync words, header validity, or repeated-frame consistency."
                )
            st.download_button("Download decoded bytes", payload, file_name="decoded.bin")

with tabs[8]:
    st.subheader("Bit-stream correlation")
    bits_source = None
    if "fec_result" in st.session_state:
        bits_source = st.session_state.fec_result.decoded_bits
    elif "deinterleaved_bits" in st.session_state:
        bits_source = st.session_state.deinterleaved_bits
    elif "demod_result" in st.session_state:
        bits_source = st.session_state.demod_result.hard_bits

    if bits_source is None:
        st.info("Run demodulation first to get a bit stream to correlate.")
    else:
        st.write("**Sync-word / known-pattern search**")
        pattern_hex = st.text_input("Pattern (hex, e.g. AB CD or ABCD)", value="")
        tolerance = st.number_input("Tolerance (bit errors allowed)", value=0, min_value=0, max_value=8)
        if pattern_hex.strip() and st.button("Search for pattern"):
            try:
                clean = pattern_hex.replace(" ", "")
                pattern_bytes = bytes.fromhex(clean)
                pattern_bits = np.unpackbits(np.frombuffer(pattern_bytes, dtype=np.uint8))
                matches = sliding_pattern_match(bits_source, pattern_bits, tolerance_bits=tolerance)
                st.write(f"Found **{len(matches)}** match(es).")
                for m in matches[:20]:
                    st.write(f"• offset {m.offset}, Hamming distance {m.hamming_distance}, score {m.score:.2f}")
            except ValueError:
                st.error("Could not parse hex pattern.")

        st.write("**Repeated-sequence / header detection**")
        seq_len = st.number_input("Sequence length (bits)", value=32, min_value=4, max_value=256)
        min_repeats = st.number_input("Minimum repeats", value=2, min_value=2)
        if st.button("Find repeated sequences"):
            results = find_repeated_sequences(bits_source, seq_len, min_repeats)
            if not results:
                st.write("No repeated sequences found at this length/threshold.")
            for r in results[:10]:
                st.write(f"• pattern `{r['pattern_hex']}` repeats {r['repeat_count']}× at offsets {r['offsets'][:10]}")

with tabs[9]:
    st.subheader("Export analysis report")
    report = {
        "software_version": __version__,
        "source_path": rec.source_path,
        "metadata": {
            "sample_rate": rec.metadata.sample_rate.to_dict(),
            "center_frequency": rec.metadata.center_frequency.to_dict() if rec.metadata.center_frequency else None,
            "is_complex": rec.metadata.is_complex,
            "channel_count": rec.metadata.channel_count,
            "sample_dtype": rec.metadata.sample_dtype,
            "duration_seconds": rec.metadata.duration_seconds,
            "total_samples": rec.metadata.total_samples,
        },
        "selected_region": {"start_sample": start_sample, "end_sample": end_sample},
        "modulation_hypotheses": [
            {"label": h.label, "confidence": h.confidence, "evidence": h.evidence} for h in hyps
        ],
    }
    if "demod_result" in st.session_state:
        dr = st.session_state.demod_result
        report["demodulation"] = {
            "hard_bits_count": len(dr.hard_bits), "bits_per_symbol": dr.bits_per_symbol,
            "samples_per_symbol": dr.samples_per_symbol, "warnings": dr.warnings,
        }
    if "fec_result" in st.session_state:
        fr = st.session_state.fec_result
        report["fec"] = {"decoded_bits_count": len(fr.decoded_bits), "path_metric": fr.path_metric,
                          "warnings": fr.warnings}

    report_json = json.dumps(report, indent=2, default=str)
    st.download_button("Download JSON report", report_json, file_name="signalscope_report.json",
                        mime="application/json")
    st.json(report)
