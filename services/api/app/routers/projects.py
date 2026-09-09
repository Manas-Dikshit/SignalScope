from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import AnalysisProject, ParameterEstimate, Recording, RecordingMetadata, User
from ..schemas import (
    AnalysisCorrelation,
    AnalysisDemod,
    AnalysisFEC,
    AnalysisModulation,
    AnalysisPSD,
    AnalysisWaterfall,
    BurstDetectionResponse,
    BurstResponse,
    DeepAnalysisResponse,
    JobResponse,
    PaginatedResponse,
    ParameterEstimateResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    SegmentInfo,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_or_403(project: AnalysisProject | None, user_id: uuid.UUID) -> AnalysisProject:
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.created_by != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec_result = await db.execute(select(Recording).where(Recording.id == body.recording_id))
    rec = rec_result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied to recording")

    project = AnalysisProject(
        name=body.name,
        description=body.description,
        recording_id=body.recording_id,
        created_by=user.id,
        selected_start_sample=body.selected_start_sample,
        selected_end_sample=body.selected_end_sample,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    offset: int = 0,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count_q = select(func.count()).select_from(AnalysisProject).where(
        AnalysisProject.created_by == user.id, AnalysisProject.status != "deleted"
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(AnalysisProject)
        .where(AnalysisProject.created_by == user.id, AnalysisProject.status != "deleted")
        .order_by(AnalysisProject.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    items = result.scalars().all()
    return PaginatedResponse(items=items, total=total)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id, AnalysisProject.status != "deleted"
        )
    )
    project = result.scalar_one_or_none()
    return _project_or_403(project, user.id)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id, AnalysisProject.status != "deleted"
        )
    )
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field_name, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisProject).where(AnalysisProject.id == project_id))
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)
    project.status = "deleted"
    await db.commit()


@router.post("/{project_id}/estimate-parameters", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def estimate_parameters(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id, AnalysisProject.status != "deleted"
        )
    )
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    from ..tasks import estimate_parameters_task

    task = estimate_parameters_task.delay(str(project_id))
    return JobResponse(
        id=task.id,
        status="queued",
        progress_percent=0.0,
        current_stage=None,
        error_message=None,
    )


@router.get("/{project_id}/parameters", response_model=list[ParameterEstimateResponse])
async def list_parameters(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id, AnalysisProject.status != "deleted"
        )
    )
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    q = (
        select(ParameterEstimate)
        .where(ParameterEstimate.project_id == project_id)
        .order_by(ParameterEstimate.created_at)
    )
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/{project_id}/detect-bursts", response_model=BurstDetectionResponse)
async def detect_bursts(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id, AnalysisProject.status != "deleted"
        )
    )
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    rec_result = await db.execute(select(Recording).where(Recording.id == project.recording_id))
    rec = rec_result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    from signalscope_dsp.io import load_wav, load_raw_iq, RawIQFormat, load_sigmf
    from signalscope_dsp.detection import detect_bursts as dsp_detect_bursts, burst_stats

    from ..models import RecordingMetadata

    meta_result = await db.execute(select(RecordingMetadata).where(RecordingMetadata.recording_id == rec.id))
    meta = meta_result.scalar_one_or_none()

    loader = rec.file_format
    params: dict = {}
    if meta and meta.raw_metadata_json:
        if loader == "raw_iq":
            params = {
                "dtype": meta.data_type or "int16",
                "layout": meta.iq_layout or "interleaved",
                "endian": meta.endian or "little",
                "sample_rate_hz": meta.sample_rate,
                "center_frequency_hz": meta.center_frequency,
            }
        elif loader == "wav":
            params = {"stereo_mode": meta.raw_metadata_json.get("stereo_mode", "left_is_i_right_is_q")}

    if loader == "wav":
        loaded = load_wav(rec.storage_path, **params)
    elif loader == "raw_iq":
        loaded = load_raw_iq(rec.storage_path, RawIQFormat(**params))
    elif loader == "sigmf":
        loaded = load_sigmf(rec.storage_path)
    else:
        raise HTTPException(status_code=422, detail=f"Unknown format: {loader}")

    samples = loaded.samples
    sr = loaded.metadata.sample_rate.value
    if not sr:
        raise HTTPException(status_code=422, detail="Sample rate unknown; cannot detect bursts")

    if project.selected_start_sample is not None and project.selected_end_sample is not None:
        s = project.selected_start_sample
        e = project.selected_end_sample
        samples = samples[s:e]
        sr_for_detection = sr
    else:
        sr_for_detection = sr

    bursts = dsp_detect_bursts(samples, sr_for_detection)
    stats = burst_stats(bursts)

    burst_responses = [BurstResponse(**b.__dict__) for b in bursts]
    stats_ser = {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in stats.items()}
    return BurstDetectionResponse(bursts=burst_responses, stats=stats_ser)


@router.get("/{project_id}/analysis", response_model=DeepAnalysisResponse)
async def deep_analysis(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Interactive deep-dive over the project ROI: PSD, waterfall, spectral features,
    modulation hypothesis, symbol-rate candidates, demodulated bits, de-interleaving,
    FEC decode with CRC, and bit-stream correlation. Runs synchronously over a capped
    window (first ~0.2 M samples of the ROI) so it stays responsive; the full file is
    covered by the Celery parameter-estimation job instead."""
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id, AnalysisProject.status != "deleted"
        )
    )
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    rec_result = await db.execute(select(Recording).where(Recording.id == project.recording_id))
    rec = rec_result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    meta_result = await db.execute(select(RecordingMetadata).where(RecordingMetadata.recording_id == rec.id))
    meta = meta_result.scalar_one_or_none()
    sr = meta.sample_rate if meta else None
    if not sr:
        raise HTTPException(status_code=422, detail="Sample rate unknown; cannot run deep analysis")

    from signalscope_dsp.io import load_wav, load_raw_iq, RawIQFormat, load_sigmf
    from signalscope_dsp.preprocessing import ConditioningConfig, condition_signal
    from signalscope_dsp.features import compute_psd, compute_waterfall, extract_spectral_features
    from signalscope_dsp.modulation import classify_modulation_estimate, estimate_symbol_rate_candidates
    from signalscope_dsp.demodulation import demod_psk, demod_qam, demod_fsk
    from signalscope_dsp.detection.parameters import identify_fec, identify_interleaving
    from signalscope_dsp.fec.convolutional import viterbi_decode
    from signalscope_dsp.fec.validation import bits_to_bytes, crc16_ccitt
    from signalscope_dsp.correlation.correlate import find_repeated_sequences

    loader = rec.file_format
    params: dict = {}
    if meta and meta.raw_metadata_json:
        if loader == "raw_iq":
            params = {
                "dtype": meta.data_type or "int16",
                "layout": meta.iq_layout or "interleaved",
                "endian": meta.endian or "little",
                "sample_rate_hz": meta.sample_rate,
                "center_frequency_hz": meta.center_frequency,
            }
        elif loader == "wav":
            params = {"stereo_mode": meta.raw_metadata_json.get("stereo_mode", "left_is_i_right_is_q")}

    if loader == "wav":
        loaded = load_wav(rec.storage_path, **params)
    elif loader == "raw_iq":
        loaded = load_raw_iq(rec.storage_path, RawIQFormat(**params))
    elif loader == "sigmf":
        loaded = load_sigmf(rec.storage_path)
    else:
        raise HTTPException(status_code=422, detail=f"Unknown format: {loader}")

    start = project.selected_start_sample or 0
    end = project.selected_end_sample or len(loaded.samples)
    samples = loaded.samples[start:end]
    window_end = min(len(samples), 200_000)
    samples = samples[:window_end]

    cond = condition_signal(samples, sr, ConditioningConfig(remove_dc_offset=True, normalize=True))
    work = cond.samples

    freqs, psd_db = compute_psd(work, sr)
    wf_freqs, wf_times, wf_db = compute_waterfall(work, sr, fft_size=256, overlap=0.5)
    n_freq, n_time = wf_db.shape
    freq_idx = list(range(0, n_freq, max(1, n_freq // 200)))
    time_idx = list(range(0, n_time, max(1, n_time // 200)))
    wf_db = wf_db[np.ix_(freq_idx, time_idx)]

    feats = extract_spectral_features(work, sr)
    features = {
        f.name: {"value": f.value, "unit": f.unit, "source": f.source.value, "confidence": f.confidence}
        for name, f in [
            ("occupied_bandwidth", feats.occupied_bandwidth_hz),
            ("peak_frequency", feats.peak_frequency_hz),
            ("spectral_centroid", feats.spectral_centroid_hz),
            ("spectral_flatness", feats.spectral_flatness),
            ("crest_factor", feats.crest_factor),
            ("zero_crossing_rate", feats.zero_crossing_rate),
            ("snr_db", feats.snr_db),
        ]
    }

    mod_est = classify_modulation_estimate(work, sr)
    sym_cands = estimate_symbol_rate_candidates(work, sr)
    sym_rate = next((c.value for c in sym_cands if c.value), None)
    sym_conf = next((c.confidence for c in sym_cands if c.value), None)

    mod_label = "" if mod_est.value is None else str(mod_est.value)
    sps = max(2, int(round(sr / sym_rate))) if sym_rate else 8
    demod_modes = {
        "BPSK": ("psk", 2), "QPSK": ("psk", 4), "8-PSK": ("psk", 8),
        "16-QAM": ("qam", 16), "64-QAM": ("qam", 64),
        "2-FSK": ("fsk", 2), "4-FSK": ("fsk", 4),
    }
    mode, order = demod_modes.get(mod_label, ("psk", 2))
    n_bits = n_symbols = 0
    constellation: list[list[float]] = []
    hard_bits: np.ndarray | None = None
    first_bytes_hex = ""
    demod_warnings: list[str] = []
    try:
        if mode == "qam":
            result = demod_qam(work, order, sps)
        elif mode == "fsk":
            result = demod_fsk(work, sr, order, sps)
        else:
            result = demod_psk(work, order, sps)
        hard_bits = result.hard_bits
        n_bits, n_symbols = int(len(result.hard_bits)), int(len(result.symbols))
        cap = min(len(result.symbols), 2000)
        constellation = [[float(s.real), float(s.imag)] for s in result.symbols[:cap]]
        first_bytes_hex = bits_to_bytes(result.hard_bits)[:32].hex()
        demod_warnings = list(result.warnings)
    except Exception as exc:
        demod_warnings = [f"Demodulation failed: {exc}"]

    deinterleave = {"best_attempt": "none", "validation_score": 0.0, "recovered_preview": ""}
    fec_warnings: list[str] = []
    decoded_bits: np.ndarray | None = None
    path_metric = 0.0
    crc_valid: bool | None = None
    crc_detail = "No decoded bytes to check"
    fec_bytes_hex = ""
    fec_est = None
    if hard_bits is not None and len(hard_bits) >= 8:
        deinterleave = identify_interleaving(hard_bits)
        best_bits = hard_bits
        if deinterleave["best_attempt"] != "none":
            from signalscope_dsp.interleaving import (
                block_deinterleave, convolutional_deinterleave,
                diagonal_deinterleave, pseudo_random_deinterleave,
            )
            best_bits = {
                "block": block_deinterleave(hard_bits, 8, 8),
                "convolutional": convolutional_deinterleave(hard_bits, 4, 3),
                "diagonal": diagonal_deinterleave(hard_bits, 8, 8),
                "pseudo_random": pseudo_random_deinterleave(hard_bits, seed=0),
            }[deinterleave["best_attempt"]]
        fec_est = identify_fec(best_bits)
        try:
            viterbi = viterbi_decode(best_bits, constraint_length=7)
            decoded_bits = viterbi.decoded_bits
            path_metric = float(viterbi.path_metric)
            fec_warnings = list(viterbi.warnings)
            payload = bits_to_bytes(decoded_bits)
            fec_bytes_hex = payload[:32].hex()
            if len(payload) >= 2:
                expected = crc16_ccitt(payload[:-2])
                received = int.from_bytes(payload[-2:], "big")
                crc_valid = expected == received
                crc_detail = f"CRC-16 {('OK' if crc_valid else 'mismatch')}: computed {expected:04x} vs trailing {received:04x}"
        except Exception as exc:
            fec_warnings.append(f"FEC decode failed: {exc}")

    sequences: list[dict] = []
    if decoded_bits is not None and len(decoded_bits) >= 24:
        sequences = [
            {"pattern_hex": s["pattern_hex"], "repeat_count": s["repeat_count"], "offsets": s["offsets"][:5]}
            for s in find_repeated_sequences(decoded_bits, 24, 2)[:10]
        ]

    return DeepAnalysisResponse(
        sample_rate=sr,
        window_start_sample=start,
        window_end_sample=start + window_end,
        psd=AnalysisPSD(freqs_hz=freqs.tolist(), psd_db=psd_db.tolist()),
        waterfall=AnalysisWaterfall(
            freqs_hz=np.asarray(wf_freqs)[freq_idx].tolist(),
            times_s=np.asarray(wf_times)[time_idx].tolist(),
            db=wf_db.tolist(),
        ),
        features=features,
        modulation=AnalysisModulation(
            label=mod_label or "unknown",
            confidence=mod_est.confidence,
            evidence=mod_est.evidence,
            alternatives=[{"label": alt.value, "confidence": alt.confidence} for alt in mod_est.alternatives],
        ),
        symbol_rate_hz=sym_rate,
        symbol_rate_confidence=sym_conf,
        deinterleave=deinterleave,
        demodulation=AnalysisDemod(
            modulation=mod_label or "unknown", samples_per_symbol=sps,
            bits_per_symbol=(int(np.log2(order)) if hard_bits is not None else 0),
            n_symbols=n_symbols, n_bits=n_bits,
            constellation=constellation,
            hard_bits_preview="".join(str(b) for b in hard_bits[:128]) if hard_bits is not None else "",
            first_bytes_hex=first_bytes_hex,
            warnings=demod_warnings,
        ),
        fec=AnalysisFEC(
            fec_type=str(fec_est.value) if fec_est and fec_est.value else None,
            fec_confidence=fec_est.confidence if fec_est else None,
            decoded_bits_count=int(len(decoded_bits)) if decoded_bits is not None else 0,
            path_metric=path_metric, crc_valid=crc_valid, crc_detail=crc_detail,
            first_bytes_hex=fec_bytes_hex, warnings=fec_warnings,
        ),
        correlation=AnalysisCorrelation(sequences=sequences),
    )


@router.get("/{project_id}/segments", response_model=list[SegmentInfo])
async def get_segments(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id, AnalysisProject.status != "deleted"
        )
    )
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    rec_result = await db.execute(select(Recording).where(Recording.id == project.recording_id))
    rec = rec_result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    meta_result = await db.execute(select(RecordingMetadata).where(RecordingMetadata.recording_id == rec.id))
    meta = meta_result.scalar_one_or_none()
    sr = meta.sample_rate if meta else None

    total = rec.total_samples or 0
    start = project.selected_start_sample or 0
    end = project.selected_end_sample or total
    dur = (end - start) / sr if sr else None
    return [SegmentInfo(start_sample=start, end_sample=end, duration_seconds=dur)]
