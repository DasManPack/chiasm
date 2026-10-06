from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"

FLUID_GATE_TESTS = [
    "desktop/tests/test_background_scheduler.py",
    "desktop/tests/test_responsiveness.py",
    "desktop/tests/test_responsiveness_gate.py",
    "desktop/tests/test_chiasm_field.py::ChiasmFieldTests::test_large_collection_field_interaction_ack_stays_inside_fluid_budget",
    "desktop/tests/test_chiasm_field.py::ChiasmFieldTests::test_field_renders_and_direct_manipulation_works_without_player_services",
    "desktop/tests/test_chiasm_field.py::ChiasmFieldTests::test_live_playback_controls_request_host_actions_and_keep_place",
    "desktop/tests/test_chiasm_field.py::ChiasmFieldTests::test_trace_lens_revisits_an_album_and_requests_play_from_that_stop",
    "desktop/tests/test_chiasm_field.py::ChiasmFieldTests::test_accessible_description_notifies_qt_only_when_text_changes",
    "desktop/tests/test_chiasm_field.py::ChiasmFieldTests::test_chiasm_interaction_measurements_reach_export_monitor",
    "desktop/tests/test_motion.py",
    "desktop/tests/test_fluid_soak_probe.py",
    "desktop/tests/test_library_index.py::test_provider_manager_defers_cached_catalog_hydration_until_first_use",
    "desktop/tests/test_plugin_config.py::test_default_secret_store_is_deferred_until_secret_access",
    "desktop/tests/test_startup_metrics.py::test_main_window_does_not_eager_import_heavy_page_modules",
    "desktop/tests/test_startup_metrics.py::test_flow_import_keeps_numpy_cold",
    "desktop/tests/test_startup_metrics.py::test_main_window_import_keeps_optional_numeric_and_http_stacks_cold",
    "desktop/tests/test_packaged_startup_probe.py",
    "desktop/tests/test_startup_metrics.py::test_local_control_bridge_is_submitted_as_background_work",
    "desktop/tests/test_startup_metrics.py::test_async_jobs_share_process_lived_ui_dispatcher",
    "desktop/tests/test_startup_metrics.py::test_async_completion_after_window_close_is_harmless",
    "desktop/tests/test_gui_redesign.py::test_slow_source_config_check_keeps_qt_event_loop_responsive",
    "desktop/tests/test_sources_feature.py::test_sources_feature_renders_providers_extensions_and_health",
    "desktop/tests/test_sources_feature.py::test_sources_feature_routes_primary_actions_through_policy",
    "desktop/tests/test_sources_feature.py::test_sources_feature_owns_install_remove_and_health_workflows",
    "desktop/tests/test_sources_feature.py::test_sources_feature_config_refresh_updates_owned_state",
    "desktop/tests/test_journey_workspace.py::test_journey_workspace_owns_default_state_and_lazy_music_map",
    "desktop/tests/test_journey_workspace.py::test_journey_workspace_requests_playback_semantically",
    "desktop/tests/test_journey_workspace.py::test_journey_live_track_change_and_manual_skip_stay_inside_workspace",
    "desktop/tests/test_journey_workspace.py::test_journey_archive_requests_recipe_and_replay_through_workspace",
    "desktop/tests/test_playback_feature.py::test_playback_feature_owns_persistent_surfaces_and_lazy_now_playing",
    "desktop/tests/test_playback_feature.py::test_transport_seek_and_queue_actions_are_semantic",
    "desktop/tests/test_playback_feature.py::test_track_change_updates_owned_state_and_emits_snapshot",
    "desktop/tests/test_playback_feature.py::test_flow_refinement_requests_new_queue_without_player_access",
    "desktop/tests/test_playback_state.py",
    "desktop/tests/test_gui_redesign.py::test_navigation_shell_changes_before_slow_page_population",
    "desktop/tests/test_gui_redesign.py::test_heavy_pages_build_once_after_navigation_shell",
    "desktop/tests/test_gui_redesign.py::test_rapid_navigation_drops_stale_page_population",
    "desktop/tests/test_gui_redesign.py::test_search_keeps_previous_results_visible_while_refreshing",
    "desktop/tests/test_gui_redesign.py::test_fast_search_never_flashes_delayed_loading_placeholder",
    "desktop/tests/test_gui_redesign.py::test_search_failure_preserves_stale_useful_results",
    "desktop/tests/test_gui_redesign.py::test_library_reuses_rendered_state_for_same_catalog_revision",
    "desktop/tests/test_gui_redesign.py::test_large_library_progressively_renders_widgets",
    "desktop/tests/test_gui_redesign.py::test_cached_album_artwork_prioritizes_viewport_and_scroll_target",
    "desktop/tests/test_gui_redesign.py::test_cached_artist_photos_use_same_viewport_priority",
    "desktop/tests/test_gui_redesign.py::test_run_async_replace_key_drops_stale_completion",
    "desktop/tests/test_gui_redesign.py::test_navigation_invalidates_hidden_page_build",
    "desktop/tests/test_gui_redesign.py::test_global_scan_activity_persists_across_navigation",
    "desktop/tests/test_gui_redesign.py::test_slow_library_scan_keeps_qt_event_loop_responsive",
    "desktop/tests/test_gui_redesign.py::test_love_and_keep_acknowledge_before_persistence",
    "desktop/tests/test_gui_redesign.py::test_optimistic_taste_action_rolls_back_if_persistence_fails",
    "desktop/tests/test_gui_redesign.py::test_next_track_prefetch_is_local_only_and_consumed_on_advance",
    "desktop/tests/test_gui_redesign.py::test_next_track_prefetch_yields_to_large_library_scan",
    "desktop/tests/test_gui_redesign.py::test_navigation_motion_happens_after_immediate_shell_change",
]


def _qt_preflight() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        raise SystemExit(
            "Fluid Melodex gate cannot run: Qt Widgets runtime is unavailable: "
            f"{exc}"
        ) from exc

    app = QApplication.instance() or QApplication([])
    app.processEvents()


def main() -> int:
    _qt_preflight()

    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    current_pythonpath = env.get("PYTHONPATH", "")
    desktop_path = str(DESKTOP)
    env["PYTHONPATH"] = (
        desktop_path
        if not current_pythonpath
        else desktop_path + os.pathsep + current_pythonpath
    )

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--maxfail=1",
        *FLUID_GATE_TESTS,
    ]
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
