from __future__ import annotations

import math
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Qt


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil((float(percentile) / 100.0) * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


class ResponsivenessTracker:
    """Measure event-loop delay and interaction acknowledgement without user content."""

    def __init__(
        self,
        *,
        interval_ms: int = 50,
        long_task_threshold_ms: int = 50,
        ci_threshold_ms: int = 250,
        serious_threshold_ms: int = 500,
        blocker_threshold_ms: int = 1000,
        action_ttl_seconds: float = 5.0,
        max_events: int = 50,
        max_gap_samples: int = 6000,
        max_interactions: int = 200,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.interval_ms = max(1, int(interval_ms))
        self.long_task_threshold_ms = max(1, int(long_task_threshold_ms))
        self.ci_threshold_ms = max(
            self.long_task_threshold_ms, int(ci_threshold_ms)
        )
        self.serious_threshold_ms = max(
            self.ci_threshold_ms, int(serious_threshold_ms)
        )
        self.blocker_threshold_ms = max(
            self.serious_threshold_ms, int(blocker_threshold_ms)
        )
        self.action_ttl_seconds = max(0.0, float(action_ttl_seconds))
        self._clock = clock
        self._last_tick: float | None = None
        self._last_action = ""
        self._last_action_at = 0.0
        self._events: deque[dict[str, Any]] = deque(maxlen=max(1, int(max_events)))
        self._gap_samples: deque[float] = deque(
            maxlen=max(10, int(max_gap_samples))
        )
        self._interactions: deque[dict[str, Any]] = deque(
            maxlen=max(10, int(max_interactions))
        )
        self._long_tasks = 0
        self._ci_violations = 0
        self._serious_stalls = 0
        self._release_blockers = 0
        self._max_delay_ms = 0.0
        self._max_gap_ms = 0.0

    def reset_clock(self, now: float | None = None) -> None:
        self._last_tick = self._clock() if now is None else float(now)

    def mark_action(self, label: str, now: float | None = None) -> None:
        self._last_action = str(label or "").strip()[:80]
        self._last_action_at = self._clock() if now is None else float(now)

    def record_interaction(
        self,
        label: str,
        duration_ms: float,
    ) -> dict[str, Any]:
        event = {
            "label": str(label or "").strip()[:80],
            "duration_ms": round(max(0.0, float(duration_ms)), 1),
        }
        self._interactions.append(event)
        return dict(event)

    def observe(self, now: float | None = None) -> dict[str, Any] | None:
        current = self._clock() if now is None else float(now)
        if self._last_tick is None:
            self._last_tick = current
            return None

        gap_ms = max(0.0, (current - self._last_tick) * 1000.0)
        self._last_tick = current
        self._gap_samples.append(gap_ms)
        self._max_gap_ms = max(self._max_gap_ms, gap_ms)

        delay_ms = max(0.0, gap_ms - float(self.interval_ms))
        if delay_ms < self.long_task_threshold_ms:
            return None

        if delay_ms >= self.blocker_threshold_ms:
            severity = "release_blocker"
            self._release_blockers += 1
        elif delay_ms >= self.serious_threshold_ms:
            severity = "serious"
            self._serious_stalls += 1
        elif delay_ms >= self.ci_threshold_ms:
            severity = "ci_violation"
            self._ci_violations += 1
        else:
            severity = "long_task"
            self._long_tasks += 1

        action = ""
        if (
            self._last_action
            and current - self._last_action_at <= self.action_ttl_seconds
        ):
            action = self._last_action

        event = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "severity": severity,
            "delay_ms": round(delay_ms, 1),
            "gap_ms": round(gap_ms, 1),
            "action": action,
        }
        self._events.append(event)
        self._max_delay_ms = max(self._max_delay_ms, delay_ms)
        return dict(event)

    def summary(self) -> dict[str, Any]:
        gaps = list(self._gap_samples)
        interactions = list(self._interactions)
        durations = [float(row["duration_ms"]) for row in interactions]
        interaction_over_50 = sum(value > 50.0 for value in durations)
        interaction_over_100 = sum(value > 100.0 for value in durations)

        return {
            "interval_ms": self.interval_ms,
            "long_task_threshold_ms": self.long_task_threshold_ms,
            "ci_threshold_ms": self.ci_threshold_ms,
            "serious_threshold_ms": self.serious_threshold_ms,
            "blocker_threshold_ms": self.blocker_threshold_ms,
            "total_stalls": (
                self._long_tasks
                + self._ci_violations
                + self._serious_stalls
                + self._release_blockers
            ),
            "long_tasks": self._long_tasks,
            "ci_violations": self._ci_violations,
            "serious_stalls": self._serious_stalls,
            "release_blockers": self._release_blockers,
            "event_loop_sample_count": len(gaps),
            "p99_event_loop_gap_ms": round(
                _nearest_rank_percentile(gaps, 99.0), 1
            ),
            "max_gap_ms": round(self._max_gap_ms, 1),
            "max_delay_ms": round(self._max_delay_ms, 1),
            "interaction_count": len(durations),
            "interaction_p95_ms": round(
                _nearest_rank_percentile(durations, 95.0), 1
            ),
            "interaction_max_ms": round(max(durations, default=0.0), 1),
            "interactions_over_50_ms": interaction_over_50,
            "interactions_over_100_ms": interaction_over_100,
            "recent_stalls": [dict(event) for event in self._events],
            "recent_interactions": [dict(event) for event in interactions[-50:]],
        }


class UiResponsivenessMonitor(QObject):
    """Qt wrapper around ResponsivenessTracker."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        interval_ms: int = 50,
        long_task_threshold_ms: int = 50,
        ci_threshold_ms: int = 250,
        serious_threshold_ms: int = 500,
        blocker_threshold_ms: int = 1000,
    ) -> None:
        super().__init__(parent)
        self.tracker = ResponsivenessTracker(
            interval_ms=interval_ms,
            long_task_threshold_ms=long_task_threshold_ms,
            ci_threshold_ms=ci_threshold_ms,
            serious_threshold_ms=serious_threshold_ms,
            blocker_threshold_ms=blocker_threshold_ms,
        )
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(self.tracker.interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.tracker.reset_clock()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def mark_action(self, label: str) -> None:
        self.tracker.mark_action(label)

    def begin_interaction(self, label: str) -> tuple[str, float]:
        clean = str(label or "").strip()[:80]
        self.tracker.mark_action(clean)
        return clean, time.monotonic()

    def end_interaction(
        self,
        token: tuple[str, float] | None,
    ) -> dict[str, Any] | None:
        if token is None:
            return None
        label, started_at = token
        return self.tracker.record_interaction(
            label,
            (time.monotonic() - float(started_at)) * 1000.0,
        )

    def record_interaction(self, label: str, duration_ms: float) -> dict[str, Any]:
        """Record a completed interaction measured by an owned UI component."""
        self.tracker.mark_action(label)
        return self.tracker.record_interaction(label, duration_ms)

    def summary(self) -> dict[str, Any]:
        return self.tracker.summary()

    def _tick(self) -> None:
        self.tracker.observe()
