from __future__ import annotations

"""Render small PNG "second opinion" images for the Gemma 4 analyst.

The model never receives raw IQ. This module turns a bounded signal window into
a handful of low-resolution plots (PSD, waterfall, constellation, M-th power),
encodes them as data URIs, and returns an audit record with the hash and size of
every image that was actually sent.

Pillow is used directly instead of matplotlib: no hidden caches, no GUI backend,
predictable memory use, and no extra system dependencies.
"""

import hashlib
import io
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

WIDTH = 512
HEIGHT = 320
TITLE_HEIGHT = 24

_MODULATION_ORDERS = {
    "BPSK": ("psk", 2, 2),
    "QPSK": ("psk", 4, 4),
    "8-PSK": ("psk", 8, 8),
    "16-QAM": ("qam", 16, 4),
    "64-QAM": ("qam", 64, 4),
    "2-FSK": ("fsk", 2, 2),
    "4-FSK": ("fsk", 4, 2),
}

_BACKGROUND = (250, 250, 252)
_AXIS = (180, 184, 190)
_TRACE = (37, 99, 235)
_MUTED = (90, 96, 105)


@dataclass
class EvidenceImageBundle:
    images: dict[str, str] = field(default_factory=dict)
    audit: dict[str, dict[str, Any]] = field(default_factory=dict)
    total_bytes: int = 0


def _new_canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), _BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, WIDTH, TITLE_HEIGHT], fill=(238, 240, 245))
    draw.text((8, 6), title, fill=(30, 34, 40))
    return image, draw


def _to_uint8(values: np.ndarray, low: float | None = None, high: float | None = None) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    lo = float(np.min(values)) if low is None else float(low)
    hi = float(np.max(values)) if high is None else float(high)
    if not np.isfinite(lo):
        lo = 0.0
    if not np.isfinite(hi) or hi <= lo:
        hi = lo + 1.0
    scaled = np.clip((values - lo) / (hi - lo), 0.0, 1.0)
    return (scaled * 255.0).astype(np.uint8)


def _plot(
    draw: ImageDraw.ImageDraw,
    x: np.ndarray,
    y: np.ndarray,
    color: tuple[int, int, int] = _TRACE,
) -> None:
    left, right = 12, WIDTH - 12
    top, bottom = TITLE_HEIGHT + 12, HEIGHT - 12
    draw.rectangle([left, top, right, bottom], outline=_AXIS)
    if len(x) < 2:
        return
    px = left + (np.asarray(x) - np.min(x)) / max(np.ptp(x), 1e-12) * (right - left)
    py = bottom - (np.asarray(y) - np.min(y)) / max(np.ptp(y), 1e-12) * (bottom - top)
    points = [(float(a), float(b)) for a, b in zip(px, py)]
    draw.line(points, fill=color, width=1)


def _downsample(array: np.ndarray, limit: int) -> np.ndarray:
    if len(array) <= limit:
        return array
    step = max(1, len(array) // limit)
    return array[::step][:limit]


def _psd_image(samples: np.ndarray, sample_rate: float) -> Image.Image:
    from signalscope_dsp.features import compute_psd

    freqs, psd_db = compute_psd(samples, sample_rate)
    freqs = _downsample(freqs, 320)
    psd_db = _downsample(psd_db, 320)
    image, draw = _new_canvas("PSD (dB, Welch)")
    _plot(draw, freqs / 1000.0, psd_db)
    draw.text((12, HEIGHT - 11), "frequency (kHz)", fill=_MUTED)
    return image


def _waterfall_image(samples: np.ndarray, sample_rate: float) -> Image.Image:
    from signalscope_dsp.features import compute_waterfall

    _, _, spectrogram_db = compute_waterfall(samples, sample_rate, fft_size=256, overlap=0.5)
    if spectrogram_db.ndim != 2 or spectrogram_db.size == 0:
        raise ValueError("waterfall is empty")
    n_freq, n_time = spectrogram_db.shape
    freq_step = max(1, n_freq // 160)
    time_step = max(1, n_time // 240)
    trimmed = spectrogram_db[::freq_step, ::time_step]
    grey = Image.fromarray(_to_uint8(trimmed)).resize(
        (WIDTH - 24, HEIGHT - TITLE_HEIGHT - 24)
    )
    image, draw = _new_canvas("Waterfall (dB)")
    image.paste(grey.convert("RGB"), (12, TITLE_HEIGHT + 12))
    draw.rectangle(
        [12, TITLE_HEIGHT + 12, WIDTH - 12, HEIGHT - 12],
        outline=_AXIS,
    )
    draw.text((12, HEIGHT - 11), "time \u2192", fill=_MUTED)
    return image


def _symbols_for(
    samples: np.ndarray,
    sample_rate: float,
    modulation: str | None,
    symbol_rate: float | None,
) -> np.ndarray:
    from signalscope_dsp.demodulation import demod_fsk, demod_psk, demod_qam

    mode, order, _ = _MODULATION_ORDERS.get(
        (modulation or "").upper(), ("psk", 4, 4)
    )
    if symbol_rate and symbol_rate > 0:
        sps = max(2, min(64, int(round(sample_rate / float(symbol_rate)))))
    else:
        sps = 8

    if mode == "qam":
        result = demod_qam(samples, order, sps)
    elif mode == "fsk":
        result = demod_fsk(samples, sample_rate, order, sps)
    else:
        result = demod_psk(samples, order, sps)

    symbols = np.asarray(result.symbols)
    if symbols.size == 0:
        raise ValueError("no decided symbols")
    return _downsample(symbols, 2000)


def _constellation_image(
    samples: np.ndarray,
    sample_rate: float,
    modulation: str | None,
    symbol_rate: float | None,
) -> Image.Image:
    symbols = _symbols_for(samples, sample_rate, modulation, symbol_rate)
    real = symbols.real
    imag = symbols.imag
    span = float(max(np.max(np.abs(real)), np.max(np.abs(imag)), 1e-9))
    left, right = 24, WIDTH - 24
    top, bottom = TITLE_HEIGHT + 16, HEIGHT - 16
    cx, cy = (left + right) / 2, (top + bottom) / 2
    half = min(right - cx, bottom - cy)

    image, draw = _new_canvas(f"Constellation ({modulation or 'auto'})")
    draw.line([(left, cy), (right, cy)], fill=_AXIS)
    draw.line([(cx, top), (cx, bottom)], fill=_AXIS)
    for value, other in zip(real, imag):
        x = cx + float(value) / span * half
        y = cy - float(other) / span * half
        draw.ellipse([x - 1.4, y - 1.4, x + 1.4, y + 1.4], fill=_TRACE)
    return image


def _mth_power_image(samples: np.ndarray, modulation: str | None) -> Image.Image:
    from signalscope_dsp.modulation.classifier import mth_power_spectrum

    order = _MODULATION_ORDERS.get((modulation or "").upper(), ("psk", 4, 4))[2]
    spectrum = mth_power_spectrum(samples, order)
    freqs = _downsample(np.asarray(spectrum.get("freqs", [])), 320)
    power = _downsample(np.asarray(spectrum.get("power", [])), 320)
    if freqs.size < 2 or power.size < 2:
        raise ValueError("empty M-th power spectrum")
    image, draw = _new_canvas(f"M-th power spectrum (M={order})")
    _plot(draw, freqs, power, color=(190, 24, 93))
    return image


def _encode(
    image: Image.Image,
    *,
    kind: str,
    max_bytes: int,
) -> tuple[str, dict[str, Any]] | None:
    """Encode a PNG, shrinking it if needed. Returns None if it cannot fit."""

    last: bytes | None = None
    width, height = image.size
    for scale in (1.0, 0.75, 0.5, 0.35):
        candidate = image
        if scale != 1.0:
            candidate = image.resize(
                (max(64, int(width * scale)), max(48, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        candidate.save(buffer, format="PNG", optimize=True)
        last = buffer.getvalue()
        if len(last) <= max_bytes:
            break
    if not last or len(last) > max_bytes:
        return None

    audit = {
        "kind": kind,
        "mime": "image/png",
        "bytes": len(last),
        "sha256": hashlib.sha256(last).hexdigest(),
        "width": candidate.size[0],
        "height": candidate.size[1],
    }
    import base64

    data_uri = "data:image/png;base64," + base64.b64encode(last).decode("ascii")
    return data_uri, audit


def render_evidence_images(
    samples: np.ndarray,
    sample_rate: float,
    *,
    modulation: str | None = None,
    symbol_rate: float | None = None,
    max_samples: int = 200_000,
    max_image_bytes: int = 300_000,
    max_total_bytes: int = 1_000_000,
) -> EvidenceImageBundle:
    """Render the multimodal evidence bundle.

    Individual renderers are isolated: one failed plot never blocks the others,
    and the audit records why an image was skipped. No raw samples are returned.
    """

    window = np.asarray(samples)[:max_samples]
    if window.size < 32:
        raise ValueError("signal window is too short to render evidence images")

    from signalscope_dsp.preprocessing import ConditioningConfig, condition_signal

    try:
        conditioned = condition_signal(
            window,
            sample_rate,
            ConditioningConfig(remove_dc_offset=True, normalize=True),
        )
        work = conditioned.samples
    except Exception:
        work = window

    renderers = {
        "psd.png": lambda: _psd_image(work, sample_rate),
        "waterfall.png": lambda: _waterfall_image(work, sample_rate),
        "constellation.png": lambda: _constellation_image(
            work, sample_rate, modulation, symbol_rate
        ),
        "mth_power.png": lambda: _mth_power_image(work, modulation),
    }

    bundle = EvidenceImageBundle()
    for name, renderer in renderers.items():
        try:
            encoded = _encode(
                renderer(),
                kind=name.split(".")[0],
                max_bytes=max_image_bytes,
            )
        except Exception as exc:  # one bad plot must not sink the brief
            bundle.audit[name] = {"kind": name.split(".")[0], "skipped": str(exc)}
            continue

        if encoded is None:
            bundle.audit[name] = {
                "kind": name.split(".")[0],
                "skipped": f"exceeds {max_image_bytes} byte cap",
            }
            continue

        data_uri, audit = encoded
        if bundle.total_bytes + audit["bytes"] > max_total_bytes:
            bundle.audit[name] = {
                **audit,
                "skipped": f"exceeds {max_total_bytes} byte bundle cap",
            }
            continue

        bundle.images[name] = data_uri
        bundle.audit[name] = audit
        bundle.total_bytes += audit["bytes"]

    return bundle
