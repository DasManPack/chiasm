from __future__ import annotations

import ast
import json
import os
import inspect
import threading
import time
import subprocess
import sys

from pathlib import Path

import pytest

from melodex.startup_metrics import StartupTimeline


def test_startup_timeline_records_monotonic_deltas(tmp_path) -> None:
    timeline = StartupTimeline(started_at=10.0)
    timeline.mark("module_ready", now=10.125)
    timeline.mark("ui_ready", now=10.300)

    summary = timeline.summary()
    assert summary["schema"] == 1
    assert summary["total_ms"] == pytest.approx(300.0)
    assert summary["events"] == [
        {
            "phase": "module_ready",
            "elapsed_ms": pytest.approx(125.0),
            "delta_ms": pytest.approx(125.0),
        },
        {
            "phase": "ui_ready",
            "elapsed_ms": pytest.approx(300.0),
            "delta_ms": pytest.approx(175.0),
        },
    ]

    path = timeline.write_json(tmp_path / "startup.json")
    stored = json.loads(path.read_text("utf-8"))
    assert stored["events"][1]["phase"] == "ui_ready"


def test_startup_timeline_rejects_empty_phase() -> None:
    timeline = StartupTimeline(started_at=0.0)
    with pytest.raises(ValueError):
        timeline.mark("   ", now=1.0)


def test_main_window_does_not_eager_import_heavy_page_modules() -> None:
    path = Path(__file__).resolve().parents[1] / "melodex" / "main_window.py"
    tree = ast.parse(path.read_text("utf-8"))
    imported = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
    }
    forbidden = {
        "library_browser",
        "rich_now_playing",
        "living_canvas",
        "album_wall",
        "album_wall_model",
        "music_map",
        "music_map_model",
        "visualization_models",
        "plugin_directory",
        # P9d: Home/playback startup must not import optional feature graphs.
        "mind",
        "local_intelligence",
        "music_knowledge",
        "music_pathfinder",
        "music_journey",
        "music_journey_live",
        "journey_recipe",
        "journey_replay",
        "llm_bridge",
        "metadata",
        "playlist_io",
        "plugin_configuration_dialog",
        "plugin_onboarding",
        "diagnostics",
        "library_scan_process",
    }
    assert forbidden.isdisjoint(imported), imported & forbidden


def test_provider_manager_keeps_plugin_registry_lazy(tmp_path) -> None:
    from melodex.provider_manager import ProviderManager

    manager = ProviderManager(tmp_path / "data")
    try:
        assert manager._registry is None
        registry = manager.registry
        assert registry is manager._registry
    finally:
        manager.close()


def test_flow_import_keeps_numpy_cold() -> None:
    desktop = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    existing = str(env.get("PYTHONPATH") or "")
    env["PYTHONPATH"] = (
        str(desktop)
        if not existing
        else str(desktop) + os.pathsep + existing
    )
    code = (
        "import sys; import melodex.flow; "
        "assert 'numpy' not in sys.modules, 'Flow eagerly imported NumPy'"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=desktop.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_main_window_import_keeps_optional_numeric_and_http_stacks_cold() -> None:
    # The broad Python matrix intentionally does not apt-install Qt's Linux
    # display libraries. The dedicated Fluid gate does, so enforce this import
    # contract there while letting the stripped matrix skip cleanly.
    try:
        from PySide6.QtGui import QPixmap  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"Qt GUI runtime is unavailable: {exc}")

    desktop = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    existing = str(env.get("PYTHONPATH") or "")
    env["PYTHONPATH"] = (
        str(desktop)
        if not existing
        else str(desktop) + os.pathsep + existing
    )
    code = (
        "import sys; import melodex.main_window; "
        "assert 'numpy' not in sys.modules, 'MainWindow eagerly imported NumPy'; "
        "assert 'requests' not in sys.modules, 'MainWindow eagerly imported requests'"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=desktop.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def test_local_control_bridge_is_submitted_as_background_work(
    monkeypatch,
    tmp_path: Path,
) -> None:
    try:
        from PySide6.QtCore import QObject, Signal
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        pytest.skip(f"Qt GUI runtime is unavailable: {exc}")

    class SilentFlowPlayer(QObject):
        trackChanged = Signal(dict)
        positionChanged = Signal(int, int)
        playingChanged = Signal(bool)
        queueChanged = Signal(list)
        manualAdvanced = Signal(dict, dict, int, int)
        error = Signal(str)

        def __init__(
            self, _resolver, _transition, parent, *, playback_refresher=None
        ):
            super().__init__(parent)
            self.index = -1
            self.queue = []

        def previous(self):
            pass

        def next(self):
            pass

        def seek(self, _position_ms):
            pass

        def set_queue(self, *_args):
            pass

        def append_queue(self, *_args):
            pass

        def jump_to(self, *_args, **_kwargs):
            pass

        def replace_queue_item(self, *_args, **_kwargs):
            pass

        def status(self):
            return {"playing": False, "queue": [], "index": -1}

        def replace_queue_and_play(self, *_args, **_kwargs):
            pass

        def replace_upcoming(self, *_args, **_kwargs):
            pass

        def set_playing(self, *_args, **_kwargs):
            pass

        def play_pause(self):
            pass

        def close(self):
            pass

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window, "FlowPlayer", SilentFlowPlayer)

    submitted = []

    def hold_submit(self, callback, **kwargs):
        submitted.append(dict(kwargs))
        return True

    monkeypatch.setattr(main_window.BackgroundScheduler, "submit", hold_submit)

    window = main_window.MainWindow()
    try:
        bridge_jobs = [
            item
            for item in submitted
            if item.get("name") == "local-control-bridge"
        ]
        assert len(bridge_jobs) == 1
        assert bridge_jobs[0]["priority"] == "background"
        assert window.bridge is None
        assert window._bridge_start_pending is True
    finally:
        window.close()
        app.processEvents()


def test_async_jobs_share_process_lived_ui_dispatcher(
    monkeypatch,
    tmp_path: Path,
) -> None:
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        pytest.skip(f"Qt GUI runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        main_window.MainWindow,
        "_start_local_bridge",
        lambda self: None,
    )

    window = main_window.MainWindow()
    results: list[int] = []
    try:
        dispatcher = window._ui_callback_dispatcher
        assert dispatcher.parent() is app

        source = inspect.getsource(main_window.MainWindow._run_async)
        assert "WorkerSignals()" not in source
        assert "_last_worker" not in source

        for index in range(64):
            window._run_async(
                lambda value=index: value,
                lambda value: results.append(int(value)),
                priority="foreground",
                task_name=f"dispatcher-stress-{index}",
            )

        deadline = time.monotonic() + 5.0
        while len(results) < 64 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)

        assert sorted(results) == list(range(64))
        assert window._ui_callback_dispatcher is dispatcher
    finally:
        window.close()
        app.processEvents()


def test_async_completion_after_window_close_is_harmless(
    monkeypatch,
    tmp_path: Path,
) -> None:
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        pytest.skip(f"Qt GUI runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        main_window.MainWindow,
        "_start_local_bridge",
        lambda self: None,
    )

    release = threading.Event()
    delivered: list[object] = []
    window = main_window.MainWindow()

    def blocked_work():
        release.wait(timeout=2.0)
        return "late"

    window._run_async(
        blocked_work,
        delivered.append,
        priority="foreground",
        task_name="close-race",
    )
    window.close()
    window.deleteLater()
    app.processEvents()

    release.set()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)

    assert delivered == []
