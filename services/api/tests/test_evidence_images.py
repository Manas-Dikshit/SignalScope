from __future__ import annotations

import base64

import pytest

from app.evidence_images import render_evidence_images
from signalscope_dsp.synth import SynthConfig, generate_signal

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _qpsk_samples(n_symbols: int = 1200):
    result = generate_signal(
        SynthConfig(
            modulation="qpsk",
            sample_rate_hz=200_000.0,
            symbol_rate_hz=10_000.0,
            carrier_offset_hz=0.0,
            snr_db=20.0,
            n_symbols=n_symbols,
            seed=5,
        )
    )
    return result.samples, result.config.sample_rate_hz, result.config.symbol_rate_hz


def test_render_evidence_images_returns_audited_png_data_uris():
    samples, sample_rate, symbol_rate = _qpsk_samples()
    bundle = render_evidence_images(
        samples,
        sample_rate,
        modulation="QPSK",
        symbol_rate=symbol_rate,
    )

    assert bundle.images
    assert bundle.total_bytes <= 1_000_000
    for name, data_uri in bundle.images.items():
        assert data_uri.startswith("data:image/png;base64,"), name
        raw = base64.b64decode(data_uri.split(",", 1)[1])
        assert raw.startswith(PNG_MAGIC)
        audit = bundle.audit[name]
        assert audit["mime"] == "image/png"
        assert audit["bytes"] == len(raw)
        assert len(audit["sha256"]) == 64
        assert audit["width"] > 0 and audit["height"] > 0
        # Audit records metadata only, never signal samples.
        assert "samples" not in audit


def test_expected_plot_kinds_are_present():
    samples, sample_rate, symbol_rate = _qpsk_samples()
    bundle = render_evidence_images(
        samples, sample_rate, modulation="QPSK", symbol_rate=symbol_rate
    )
    assert {"psd.png", "waterfall.png", "constellation.png", "mth_power.png"} <= set(
        bundle.images
    )


def test_per_image_cap_skips_oversized_pngs():
    samples, sample_rate, _ = _qpsk_samples()
    bundle = render_evidence_images(
        samples, sample_rate, modulation="QPSK", max_image_bytes=16
    )
    assert bundle.images == {}
    assert bundle.total_bytes == 0
    assert all("skipped" in entry for entry in bundle.audit.values())


def test_total_bundle_cap_is_enforced():
    samples, sample_rate, _ = _qpsk_samples()
    bundle = render_evidence_images(
        samples,
        sample_rate,
        modulation="QPSK",
        max_image_bytes=300_000,
        max_total_bytes=1,
    )
    assert bundle.images == {}
    assert all("bundle cap" in entry.get("skipped", "") for entry in bundle.audit.values())


def test_short_window_is_rejected():
    with pytest.raises(ValueError):
        render_evidence_images([0j] * 4, 1000.0)
