#!/usr/bin/env python3
"""Small structural ratchets for Campaign 12.

These are intentionally narrow. P12b prevents known hotspots from getting worse
without treating arbitrary line-count targets as architecture goals.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_MAIN_WINDOW_SNIPPETS = {
    "def _build_now_playing": "Now Playing construction belongs to PlaybackFeature",
    "self.current_track": "current-track state belongs to PlaybackFeature",
    "self.rich_now": "Now Playing widgets belong to PlaybackFeature",
    "self.living_canvas": "Now Playing visual state belongs to PlaybackFeature",
    "self.player_cover": "player-bar widgets belong to PlaybackFeature",
    "def _feedback": "taste playback actions belong to PlaybackFeature",
    "def _keep": "taste playback actions belong to PlaybackFeature",
    "def _refresh_queue": "queue presentation belongs to PlaybackFeature",
    "def _build_music_map": "Music Map construction belongs to JourneyWorkspace",
    "self.music_path_start_ref": "Journey route state belongs to JourneyWorkspace",
    "self.music_journey_stages_data": "Journey stage state belongs to JourneyWorkspace",
    "self.music_live_active": "Journey Live state belongs to JourneyWorkspace",
    "self.pending_journey_recipe": "Journey recipe state belongs to JourneyWorkspace",
    "from .music_pathfinder import": "Journey path planning belongs to JourneyWorkspace/domain modules",
    "from .music_journey_live import": "Journey Live replanning belongs to JourneyWorkspace/domain modules",
    "from .journey_recipe import": "Journey recipe workflow belongs to JourneyWorkspace",
    "from .journey_replay import": "Journey replay workflow belongs to JourneyWorkspace",
    "from .plugin_configuration_dialog import": "plugin configuration belongs to SourcesFeature",
    "from .plugin_directory import": "plugin directory belongs to SourcesFeature",
    "from .plugin_onboarding import": "plugin onboarding belongs to SourcesFeature",
    "def _build_sources": "Sources page construction belongs to SourcesFeature",
    "def _refresh_sources": "Sources rendering belongs to SourcesFeature",
    "self.sources_list": "Sources widgets belong to SourcesFeature",
    "self.source_primary_button": "Sources widgets belong to SourcesFeature",
    "self.source_power_panel": "Sources widgets belong to SourcesFeature",
    "def _build_chiasm": "Chiasm page construction belongs to ChiasmFeature",
    "self.chiasm_canvas": "Chiasm field state belongs to ChiasmFeature",
    "self.chiasm_arc_route_ids": "Chiasm Arc state belongs to ChiasmFeature",
}

# Journey must coordinate playback and application navigation semantically.
FORBIDDEN_JOURNEY_WORKSPACE_SNIPPETS = {
    "self.player": "JourneyWorkspace must request playback through semantic signals",
    "self.main_window": "JourneyWorkspace must not retain MainWindow",
    "from .main_window import": "JourneyWorkspace must not import MainWindow",
}

FORBIDDEN_PLAYBACK_FEATURE_SNIPPETS = {
    "self.player.": "PlaybackFeature must request playback through semantic signals",
    "self.player =": "PlaybackFeature must not own FlowPlayer",
    "self.main_window": "PlaybackFeature must not retain MainWindow",
    "from .main_window import": "PlaybackFeature must not import MainWindow",
    "from .player import FlowPlayer": "PlaybackFeature must not import FlowPlayer",
    "self._current_track =": "canonical playback state belongs to PlaybackSessionState",
    "self._queue =": "canonical queue state belongs to PlaybackSessionState",
    "self._visual_position_ms =": "canonical playback progress belongs to PlaybackSessionState",
}

FORBIDDEN_CHIASM_FEATURE_SNIPPETS = {
    "from .main_window import": "ChiasmFeature must not import MainWindow",
    "self.main_window": "ChiasmFeature must not retain MainWindow",
    "self.player.": "ChiasmFeature must request playback semantically",
    "self.player =": "ChiasmFeature must not own FlowPlayer",
}


# Baseline is the v0.7.11 main_window.py snapshot from P12a. Lower this number
# as P12c extracts responsibilities; never raise it to accommodate new work.
MAX_LINES = {
    "desktop/melodex/main_window.py": 3780,
}


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def main() -> int:
    failures: list[str] = []
    for relative, maximum in MAX_LINES.items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"{relative}: file is missing")
            continue

        current = line_count(path)
        direction = "OK" if current <= maximum else "FAIL"
        print(f"{direction}: {relative}: {current} lines (maximum {maximum})")
        if current > maximum:
            failures.append(
                f"{relative} grew to {current} lines; Campaign 12 baseline is {maximum}. "
                "Extract responsibility or reduce the file instead of raising the limit."
            )

    main_window = (ROOT / "desktop/melodex/main_window.py").read_text(
        encoding="utf-8"
    )
    for snippet, reason in FORBIDDEN_MAIN_WINDOW_SNIPPETS.items():
        if snippet in main_window:
            failures.append(
                f"desktop/melodex/main_window.py contains {snippet!r}; {reason}."
            )

    journey_workspace = (ROOT / "desktop/melodex/journey_workspace.py").read_text(
        encoding="utf-8"
    )
    for snippet, reason in FORBIDDEN_JOURNEY_WORKSPACE_SNIPPETS.items():
        if snippet in journey_workspace:
            failures.append(
                f"desktop/melodex/journey_workspace.py contains {snippet!r}; {reason}."
            )

    playback_feature = (ROOT / "desktop/melodex/playback_feature.py").read_text(
        encoding="utf-8"
    )
    for snippet, reason in FORBIDDEN_PLAYBACK_FEATURE_SNIPPETS.items():
        if snippet in playback_feature:
            failures.append(
                f"desktop/melodex/playback_feature.py contains {snippet!r}; {reason}."
            )

    chiasm_feature = (ROOT / "desktop/melodex/chiasm_feature.py").read_text(
        encoding="utf-8"
    )
    for snippet, reason in FORBIDDEN_CHIASM_FEATURE_SNIPPETS.items():
        if snippet in chiasm_feature:
            failures.append(
                f"desktop/melodex/chiasm_feature.py contains {snippet!r}; {reason}."
            )

    if failures:
        print("\nCodebase guardrail failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
