from __future__ import annotations

import json
import sys
import os
import uuid
from datetime import datetime, timezone

import numpy as np
from celery import Celery

from .config import settings

# Make DSP modules importable
_dsp_root = os.path.join(os.path.dirname(__file__), "..", "..", "..", "dsp-worker")
if _dsp_root not in sys.path:
    sys.path.insert(0, os.path.abspath(_dsp_root))

celery_app = Celery(
    "signalscope",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.update(
    task_always_eager=os.environ.get("CELERY_TASK_ALWAYS_EAGER", "").lower() in ("1", "true", "yes"),
    result_backend=settings.REDIS_URL,
    broker_connection_retry_on_startup=True,
)


def _update_progress(task, stage: str, percent: float):
    task.update_state(
        state="STARTED",
        meta={"current_stage": stage, "progress_percent": percent},
    )


@celery_app.task(name="estimate_parameters", bind=True)
def estimate_parameters_task(self, project_id_str: str):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    from signalscope_dsp.io import load_wav, load_raw_iq, RawIQFormat, load_sigmf
    from signalscope_dsp.preprocessing import ConditioningConfig, condition_signal
    from signalscope_dsp.features import compute_psd, compute_waterfall, extract_spectral_features
    from signalscope_dsp.modulation import classify_modulation_estimate, estimate_symbol_rate_candidates
    from signalscope_dsp.detection import detect_bursts, burst_stats

    from .models import Base, AnalysisProject, Recording, RecordingMetadata, ParameterEstimate
    from .database import engine as _unused  # noqa: F811

    # Sync engine for Celery worker
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    sync_engine = create_engine(sync_url)
    SessionLocal = sessionmaker(bind=sync_engine)

    project_id = uuid.UUID(project_id_str)

    with SessionLocal() as db:
        project = db.get(AnalysisProject, project_id)
        if not project:
            return {"error": "Project not found"}

        rec = db.get(Recording, project.recording_id)
        if not rec:
            return {"error": "Recording not found"}

        meta = db.query(RecordingMetadata).filter(RecordingMetadata.recording_id == rec.id).first()

        _update_progress(self, "loading_recording", 5)

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
            return {"error": f"Unknown format: {loader}"}

        samples = loaded.samples
        sr = loaded.metadata.sample_rate.value
        if not sr:
            return {"error": "Sample rate unknown"}

        # Apply ROI
        start_s = project.selected_start_sample or 0
        end_s = project.selected_end_sample or len(samples)
        samples = samples[start_s:end_s]
        total_samples_roi = len(samples)

        _update_progress(self, "conditioning", 15)
        cfg = ConditioningConfig(remove_dc_offset=True, normalize=True)
        result = condition_signal(samples, sr, cfg)
        conditioned = result.samples

        _update_progress(self, "psd", 25)
        freqs, psd_db = compute_psd(conditioned, sr)

        _update_progress(self, "waterfall", 35)
        wf_freqs, wf_times, wf_db = compute_waterfall(conditioned, sr)

        _update_progress(self, "spectral_features", 50)
        features = extract_spectral_features(conditioned, sr)

        _update_progress(self, "modulation_classification", 65)
        mod_est = classify_modulation_estimate(conditioned, sr)

        _update_progress(self, "symbol_rate", 75)
        sym_rates = estimate_symbol_rate_candidates(conditioned, sr)

        _update_progress(self, "burst_detection", 85)
        bursts = detect_bursts(conditioned, sr)
        b_stats = burst_stats(bursts)

        _update_progress(self, "persisting_results", 90)

        # Delete old estimates
        db.query(ParameterEstimate).filter(ParameterEstimate.project_id == project_id).delete()

        # Store each Estimate as a row
        estimates_to_store = [
            features.occupied_bandwidth_hz,
            features.peak_frequency_hz,
            features.spectral_centroid_hz,
            features.spectral_flatness,
            features.crest_factor,
            features.zero_crossing_rate,
            features.snr_db,
            mod_est,
            *sym_rates,
        ]
        for est in estimates_to_store:
            value = est.to_dict()
            row = ParameterEstimate(
                project_id=project_id,
                parameter_name=est.name,
                value_json=value,
                value_type=type(est.value).__name__ if est.value is not None else "None",
                confidence=est.confidence,
                evidence_json={"evidence": est.evidence, "warnings": est.warnings, "alternatives": [a.to_dict() for a in est.alternatives]},
                source=est.source.value,
            )
            db.add(row)

        # Store burst stats
        for key, est in b_stats.items():
            row = ParameterEstimate(
                project_id=project_id,
                parameter_name=key,
                value_json=est.to_dict(),
                value_type=type(est.value).__name__ if est.value is not None else "None",
                confidence=est.confidence,
                evidence_json={"evidence": est.evidence, "warnings": est.warnings},
                source=est.source.value,
            )
            db.add(row)

        project.status = "completed"
        db.commit()

    _update_progress(self, "done", 100)
    return {"project_id": project_id_str, "status": "completed"}
