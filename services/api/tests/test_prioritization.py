"""Unit tests for the celestial candidate prioritization checklist."""

from app.prioritization import (  # noqa: E402
    UNKNOWN,
    WEIGHTS,
    CandidateFacts,
    prioritize,
    score_candidate,
)


def _facts(**overrides) -> CandidateFacts:
    base = dict(
        project_id="11111111-1111-1111-1111-111111111111",
        project_name="Candidate A",
        created_at="2026-11-10T00:00:00Z",
        features={
            "occupied_bandwidth_ratio": 0.05,
            "spectral_flatness": 0.2,
            "crest_factor_norm": 0.3,
            "zero_crossing_rate": 0.4,
            "snr_norm": 0.5,
            "drift_ratio": 0.1,
        },
        estimates={"modulation": {"value": "QPSK", "confidence": 0.8}},
        gallery_size=3,
        nearest_distance=0.6,
        repeat_count=2,
        duration_seconds=120.0,
        center_frequency_hz=1_420_405_751.0,
    )
    base.update(overrides)
    return CandidateFacts(**base)


def test_strong_celestial_candidate_scores_high():
    result = score_candidate(_facts())
    assert result["novelty"] == 1.0
    assert result["repeatability"] == 1.0
    assert result["plausibility"] == 1.0
    assert result["feasibility"] == 1.0
    assert result["composite"] == 100.0
    assert result["rare_signal"] is True
    assert any("rare-signal candidate" in r for r in result["reasons"])


def test_rfi_like_duplicate_ranks_below_unique_narrowband():
    unique = _facts(project_id="1" * 8, nearest_distance=0.6, repeat_count=0)
    duplicate = _facts(
        project_id="2" * 8,
        project_name="Terrestrial repeat",
        features={
            "occupied_bandwidth_ratio": 0.8,
            "spectral_flatness": 0.9,
            "crest_factor_norm": 0.9,
            "zero_crossing_rate": 0.5,
            "snr_norm": 0.1,
            "drift_ratio": 0.9,
        },
        nearest_distance=0.05,
        repeat_count=1,
    )
    ranked = prioritize([duplicate, unique])
    assert ranked[0]["project_name"] == "Candidate A"
    assert ranked[0]["composite"] > ranked[1]["composite"]
    assert ranked[0]["rare_signal"] is True
    assert ranked[1]["rare_signal"] is False


def test_empty_gallery_is_neutral_not_zero():
    result = score_candidate(_facts(gallery_size=0, nearest_distance=None, repeat_count=0))
    assert result["novelty"] == UNKNOWN
    assert result["repeatability"] == UNKNOWN
    assert result["rare_signal"] is None
    assert any("no comparable fingerprinted observation" in r for r in result["reasons"])


def test_unknown_features_score_neutral_and_are_listed():
    stripped = _facts(
        features={
            "occupied_bandwidth_ratio": None,
            "snr_norm": None,
            "drift_ratio": None,
            "spectral_flatness": None,
        },
        center_frequency_hz=None,
    )
    result = score_candidate(stripped)
    assert result["plausibility"] == UNKNOWN
    # Fully-known facts score higher: a missing centre frequency costs points.
    complete = score_candidate(_facts())
    assert result["feasibility"] < complete["feasibility"]
    assert any("Occupied bandwidth unknown" in r for r in result["reasons"])
    assert any("cannot be re-pointed" in r for r in result["reasons"])


def test_composite_is_weighted_average_in_range():
    facts = _facts(nearest_distance=0.2, repeat_count=1)
    result = score_candidate(facts)
    expected = 100.0 * (
        WEIGHTS["novelty"] * (0.2 / 0.35)
        + WEIGHTS["plausibility"] * 1.0
        + WEIGHTS["repeatability"] * 0.5
        + WEIGHTS["feasibility"] * 1.0
    )
    assert result["composite"] == round(expected, 1)
    assert 0.0 <= result["composite"] <= 100.0
