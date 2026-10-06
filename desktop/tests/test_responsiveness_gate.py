from __future__ import annotations

from melodex.responsiveness_gate import (
    EVENT_LOOP_P99_LIMIT_MS,
    INTERACTION_P95_LIMIT_MS,
    INTERACTION_P95_PREFERRED_MS,
    evaluate_responsiveness_summary,
    extract_responsiveness_summary,
)


def _passing_summary() -> dict:
    return {
        "interaction_count": 20,
        "interaction_p95_ms": 42.0,
        "event_loop_sample_count": 500,
        "p99_event_loop_gap_ms": 82.0,
        "ci_violations": 0,
        "serious_stalls": 0,
        "release_blockers": 0,
    }


def test_release_gate_passes_clean_summary():
    result = evaluate_responsiveness_summary(
        _passing_summary(),
        require_interactions=True,
        require_event_loop_samples=True,
    )

    assert result["passed"] is True
    assert result["errors"] == []
    assert result["warnings"] == []


def test_release_gate_warns_between_preferred_and_hard_interaction_target():
    summary = _passing_summary()
    summary["interaction_p95_ms"] = INTERACTION_P95_PREFERRED_MS + 20

    result = evaluate_responsiveness_summary(summary)

    assert result["passed"] is True
    assert result["errors"] == []
    assert result["warnings"]


def test_release_gate_fails_interaction_p95_over_100_ms():
    summary = _passing_summary()
    summary["interaction_p95_ms"] = INTERACTION_P95_LIMIT_MS + 0.1

    result = evaluate_responsiveness_summary(summary)

    assert result["passed"] is False
    assert any("Interaction acknowledgement p95" in row for row in result["errors"])


def test_release_gate_fails_event_loop_p99_over_100_ms():
    summary = _passing_summary()
    summary["p99_event_loop_gap_ms"] = EVENT_LOOP_P99_LIMIT_MS + 0.1

    result = evaluate_responsiveness_summary(summary)

    assert result["passed"] is False
    assert any("Event-loop p99 gap" in row for row in result["errors"])


def test_release_gate_fails_foreground_stall_tiers():
    for key in ("ci_violations", "serious_stalls", "release_blockers"):
        summary = _passing_summary()
        summary[key] = 1

        result = evaluate_responsiveness_summary(summary)

        assert result["passed"] is False
        assert result["errors"]


def test_release_gate_can_require_real_samples():
    result = evaluate_responsiveness_summary(
        {},
        require_interactions=True,
        require_event_loop_samples=True,
    )

    assert result["passed"] is False
    assert len(result["errors"]) == 2


def test_release_gate_can_require_feature_specific_interaction_evidence():
    summary = _passing_summary()
    summary["recent_interactions"] = [
        {"label": "library:selection", "duration_ms": 12.0},
        {"label": "chiasm:key", "duration_ms": 18.0},
    ]

    result = evaluate_responsiveness_summary(
        summary,
        require_interaction_prefixes=("chiasm:",),
    )

    assert result["passed"] is True
    assert result["errors"] == []

    summary["recent_interactions"] = [
        {"label": "library:selection", "duration_ms": 12.0}
    ]
    result = evaluate_responsiveness_summary(
        summary,
        require_interaction_prefixes=("chiasm:",),
    )
    assert result["passed"] is False
    assert any("chiasm:" in row for row in result["errors"])

    result = evaluate_responsiveness_summary(
        summary,
        require_interaction_prefixes=("",),
    )
    assert result["passed"] is False
    assert any("prefixes cannot be empty" in row for row in result["errors"])


def test_extracts_summary_from_full_diagnostics_payload():
    summary = _passing_summary()
    payload = {
        "performance": {
            "ui_responsiveness": dict(summary),
        }
    }

    assert extract_responsiveness_summary(payload) == summary
