from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

from melodex.responsiveness_gate import (  # noqa: E402
    evaluate_responsiveness_summary,
    extract_responsiveness_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a Melodex responsiveness summary or diagnostics export "
            "against the Fluid Melodex release budget."
        )
    )
    parser.add_argument("json_file", type=Path)
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Do not fail when interaction/event-loop samples are absent.",
    )
    parser.add_argument(
        "--require-interaction-prefix",
        action="append",
        default=[],
        metavar="PREFIX",
        help="Require at least one recent interaction label to start with PREFIX; may be repeated.",
    )
    args = parser.parse_args()

    try:
        payload = json.loads(args.json_file.read_text("utf-8"))
    except Exception as exc:
        print(f"Could not read {args.json_file}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("Diagnostics JSON must contain an object.", file=sys.stderr)
        return 2

    summary = extract_responsiveness_summary(payload)
    result = evaluate_responsiveness_summary(
        summary,
        require_interactions=not args.allow_empty,
        require_event_loop_samples=not args.allow_empty,
        require_interaction_prefixes=tuple(args.require_interaction_prefix),
    )

    observed = result["observed"]
    print("Fluid Melodex responsiveness gate")
    recent_interactions = summary.get("recent_interactions") or []
    for prefix in args.require_interaction_prefix:
        matching_count = sum(
            1
            for row in recent_interactions
            if isinstance(row, dict)
            and str(row.get("label") or "").startswith(prefix)
        )
        print(f"  recent {prefix!r} interaction samples: {matching_count}")
    print(
        "  acknowledgement p95: "
        f"{observed['interaction_p95_ms']:.1f} ms "
        f"({observed['interaction_count']} samples)"
    )
    print(
        "  event-loop p99 gap: "
        f"{observed['p99_event_loop_gap_ms']:.1f} ms "
        f"({observed['event_loop_sample_count']} samples)"
    )
    print(f"  >250 ms CI violations: {observed['ci_violations']}")
    print(f"  >500 ms serious stalls: {observed['serious_stalls']}")
    print(f"  >1 s release blockers: {observed['release_blockers']}")

    for warning in result["warnings"]:
        print(f"WARNING: {warning}")
    for error in result["errors"]:
        print(f"FAIL: {error}")

    if result["passed"]:
        print("PASS: responsiveness summary is within the Fluid Melodex release budget.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
