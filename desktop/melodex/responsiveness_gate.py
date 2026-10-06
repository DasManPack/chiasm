from __future__ import annotations

from typing import Any


INTERACTION_P95_LIMIT_MS = 100.0
INTERACTION_P95_PREFERRED_MS = 50.0
EVENT_LOOP_P99_LIMIT_MS = 100.0
FOREGROUND_STALL_LIMIT_MS = 250.0
SERIOUS_STALL_MS = 500.0
RELEASE_BLOCKER_MS = 1000.0


def release_budget() -> dict[str, float]:
    return {
        "interaction_p95_limit_ms": INTERACTION_P95_LIMIT_MS,
        "interaction_p95_preferred_ms": INTERACTION_P95_PREFERRED_MS,
        "event_loop_p99_limit_ms": EVENT_LOOP_P99_LIMIT_MS,
        "foreground_stall_limit_ms": FOREGROUND_STALL_LIMIT_MS,
        "serious_stall_ms": SERIOUS_STALL_MS,
        "release_blocker_ms": RELEASE_BLOCKER_MS,
    }


def evaluate_responsiveness_summary(
    summary: dict[str, Any] | None,
    *,
    require_interactions: bool = False,
    require_event_loop_samples: bool = False,
    require_interaction_prefixes: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Evaluate a controlled responsiveness summary against the release budget.

    This function is deliberately deterministic. CI feeds it measurements from
    controlled regression scenarios; it does not benchmark arbitrary shared
    runner speed.
    """
    data = dict(summary or {})
    errors: list[str] = []
    warnings: list[str] = []

    interaction_count = max(0, int(data.get("interaction_count") or 0))
    interaction_p95 = max(0.0, float(data.get("interaction_p95_ms") or 0.0))
    gap_count = max(0, int(data.get("event_loop_sample_count") or 0))
    p99_gap = max(0.0, float(data.get("p99_event_loop_gap_ms") or 0.0))
    ci_violations = max(0, int(data.get("ci_violations") or 0))
    serious_stalls = max(0, int(data.get("serious_stalls") or 0))
    release_blockers = max(0, int(data.get("release_blockers") or 0))

    if require_interactions and interaction_count == 0:
        errors.append("No interaction acknowledgement samples were recorded.")

    raw_interactions = data.get("recent_interactions") or ()
    interaction_labels = [
        str(row.get("label") or "")
        for row in raw_interactions
        if isinstance(row, dict)
    ]
    for prefix in require_interaction_prefixes:
        if not prefix.strip():
            errors.append("Required interaction label prefixes cannot be empty.")
            continue
        if not any(label.startswith(prefix) for label in interaction_labels):
            errors.append(
                f"No recent interaction label starts with {prefix!r}."
            )

    if interaction_count:
        if interaction_p95 > INTERACTION_P95_LIMIT_MS:
            errors.append(
                f"Interaction acknowledgement p95 is {interaction_p95:.1f} ms; "
                f"limit is {INTERACTION_P95_LIMIT_MS:.0f} ms."
            )
        elif interaction_p95 > INTERACTION_P95_PREFERRED_MS:
            warnings.append(
                f"Interaction acknowledgement p95 is {interaction_p95:.1f} ms; "
                f"preferred target is {INTERACTION_P95_PREFERRED_MS:.0f} ms."
            )

    if require_event_loop_samples and gap_count == 0:
        errors.append("No event-loop samples were recorded.")
    if gap_count and p99_gap > EVENT_LOOP_P99_LIMIT_MS:
        errors.append(
            f"Event-loop p99 gap is {p99_gap:.1f} ms; "
            f"limit is {EVENT_LOOP_P99_LIMIT_MS:.0f} ms."
        )

    if ci_violations:
        errors.append(
            f"{ci_violations} foreground stall(s) exceeded the "
            f"{FOREGROUND_STALL_LIMIT_MS:.0f} ms CI budget."
        )
    if serious_stalls:
        errors.append(
            f"{serious_stalls} serious foreground stall(s) exceeded "
            f"{SERIOUS_STALL_MS:.0f} ms."
        )
    if release_blockers:
        errors.append(
            f"{release_blockers} release-blocking foreground stall(s) exceeded "
            f"{RELEASE_BLOCKER_MS:.0f} ms."
        )

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "budget": release_budget(),
        "observed": {
            "interaction_count": interaction_count,
            "interaction_p95_ms": interaction_p95,
            "event_loop_sample_count": gap_count,
            "p99_event_loop_gap_ms": p99_gap,
            "ci_violations": ci_violations,
            "serious_stalls": serious_stalls,
            "release_blockers": release_blockers,
        },
    }


def extract_responsiveness_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Accept either a raw summary or a full Melodex diagnostics export."""
    data = dict(payload or {})
    performance = data.get("performance")
    if isinstance(performance, dict):
        candidate = performance.get("ui_responsiveness")
        if isinstance(candidate, dict):
            return dict(candidate)
    return data
