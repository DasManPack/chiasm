Warning: truncated output (original token count: 26034)
Total output lines: 3158

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import melodex.library_scan_process as library_scan_process


def _track(path: str, artist: str, album: str, title: str, number: int, year: int = 2000):
    return {
        "provider_id": "local",
        "track_id": path,
        "local_path": path,
        "artist": artist,
        "album": album,
        "title": title,
        "track_number": number,
        "year": year,
    }


def test_visual_library_defaults_to_album_cards_and_filters():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    browser.resize(1000, 700)
    browser.show()
    browser.set_catalog(
        [
            _track("/a/01.mp3", "Artist A", "Album A", "One", 1, 2001),
            _track("/a/02.mp3", "Artist A", "Album A", "Two", 2, 2001),
            _track("/b/01.mp3", "Artist B", "Album B", "Three", 1, 2010),
        ]
    )
    app.processEvents()

    assert browser.current_view() == "albums"
    assert len(browser.albums) == 2
    metrics = browser.last_catalog_metrics
    assert metrics["track_count"] == 3
    assert metrics["album_count"] == 2
    assert metrics["artist_count"] == 2
    assert metrics["main_thread"] is True
    assert metrics["total_seconds"] >= metrics["album_model_seconds"]
    assert len(browser.cards) == 2
    assert all(not card.cover.pixmap().isNull() for card in browser.cards.values())

    browser.search.setText("Album A")
    app.processEvents()
    assert len(browser._visible_albums) == 1
    assert browser._visible_albums[0]["title"] == "Album A"

    browser.search.clear()
    app.processEvents()
    browser.set_view("artists")
    assert browser.stack.currentWidget() is browser.artist_page
    assert len(browser.artist_rows) == 2
    assert len(browser.artist_cards) == 2
    assert browser.images_button.text() == "Get artist photos"
    assert all(not card.has_artist_photo for card in browser.artist_cards.values())
    assert all(hasattr(card, "photo_button") for card in browser.artist_cards.values())

    browser.set_view("tracks")
    assert browser.stack.currentWidget() is browser.track_list
    assert browser.track_model.rowCount() == 3
    app.processEvents()
    app.processEvents()
    assert len(browser.track_rows) == 3

    browser.set_catalog([])
    assert browser.stack.currentWidget() is browser.empty

    browser.deleteLater()
    app.processEvents()



def test_library_reuses_rendered_state_for_same_catalog_revision():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    browser.resize(1000, 700)
    browser.show()

    catalog = [
        _track("/a/01.mp3", "Artist A", "Album A", "One", 1, 2001),
        _track("/b/01.mp3", "Artist B", "Album B", "Two", 1, 2002),
    ]
    browser.set_catalog(catalog, revision=7)
    app.processEvents()

    first_cards = list(browser.cards.values())
    assert len(first_cards) == 2
    preserved_card = first_cards[0]

    browser.search.setText("Album A")
    app.processEvents()
    assert len(browser._visible_albums) == 1

    # Reopening My Music with the same provider revision must retain the
    # existing rendered widgets and user state rather than clearing/rebuilding.
    browser.set_catalog(catalog, revision=7)
    app.processEvents()

    assert preserved_card in browser.cards.values()
    assert browser.search.text() == "Album A"
    assert len(browser._visible_albums) == 1

    # A real catalog revision must still rebuild the visible model.
    changed = catalog + [
        _track("/c/01.mp3", "Artist C", "Album C", "Three", 1, 2003),
    ]
    browser.set_catalog(changed, revision=8)
    app.processEvents()

    assert len(browser.albums) == 3
    assert preserved_card not in browser.cards.values()

    browser.deleteLater()
    app.processEvents()


def test_large_library_progressively_renders_widgets():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    browser.resize(1100, 760)
    browser.show()

    tracks = [
        _track(
            f"/large/{index:04d}.flac",
            f"Artist {index:04d}",
            f"Album {index:04d}",
            f"Track {index:04d}",
            1,
            1980 + (index % 40),
        )
        for index in range(350)
    ]
    browser.set_catalog(tracks)
    app.processEvents()

    # Models still contain the whole collection, but heavyweight Qt cards do not.
    assert len(browser.albums) == 350
    assert len(browser.artist_rows) == 350
    assert len(browser.cards) == browser._album_batch_size == 120
    assert browser.album_more_button.isVisible()
    assert "Showing 120 of 350 albums" in browser.album_more_button.text()
    assert len(browser.artist_cards) == 0
    assert len(browser.track_rows) == 0

    browser._show_more_albums()
    app.processEvents()
    assert len(browser.cards) == 240
    assert "Showing 240 of 350 albums" in browser.album_more_button.text()

    # Search resets to a small render window and drops no-longer-visible cards.
    browser.search.setText("Album 0349")
    app.processEvents()
    assert len(browser._visible_albums) == 1
    assert len(browser.cards) == 1
    assert not browser.album_more_button.isVisible()

    browser.search.clear()
    browser.set_view("artists")
    app.processEvents()
    assert len(browser.artist_cards) == 120
    assert browser.artist_more_button.isVisible()
    browser._show_more_artists()
    app.processEvents()
    assert len(browser.artist_cards) == 240

    # Tracks expose the whole model immediately, but rich TrackRow widgets
    # exist only for the viewport plus a small overscan window.
    browser.set_view("tracks")
    app.processEvents()
    app.processEvents()
    assert browser.stack.currentWidget() is browser.track_list
    assert browser.track_model.rowCount() == 350
    assert len(browser._visible_tracks) == 350
    initial_keys = set(browser.track_rows)
    assert initial_keys
    viewport_rows = max(
        1,
        browser.track_list.viewport().height() // browser._track_row_height + 3,
    )
    max_hydrated = viewport_rows + browser._track_overscan_rows * 2
    assert len(browser.track_rows) <= max_hydrated
    assert browser.last_track_virtualization_metrics["model_row_count"] == 350
    assert browser.last_track_virtualization_metrics["hydrated_row_count"] == len(
        browser.track_rows
    )

    # Scrolling moves the hydration window instead of accumulating hundreds
    # or thousands of TrackRow widgets.
    browser.track_list.scrollToBottom()
    app.processEvents()
    app.processEvents()
    assert browser.last_track_virtualization_metrics["window_start"] > 0
    assert len(browser.track_rows) <= max_hydrated
    assert set(browser.track_rows) != initial_keys

    browser.search.setText("Track 0349")
    app.processEvents()
    app.processEvents()
    assert len(browser._visible_tracks) == 1
    assert browser.track_model.rowCount() == 1
    assert len(browser.track_rows) == 1

    browser.deleteLater()
    app.processEvents()

def test_redesigned_main_window_builds_with_goal_navigation(monkeypatch, tmp_path):
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QApplication, QLabel, QPushButton
        from melodex.chiasm_feature import enter_chiasm_mode
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.show()
    app.processEvents()

    assert list(window.nav_buttons) == [
        "home",
        "library",
        "explore",
        "journeys",
        "playlists",
        "sources",
    ]
    assert "now_playing" not in window.nav_buttons
    assert "album_wall" not in window.nav_buttons
    assert not hasattr(window, "library_browser")
    assert not hasattr(window.playback_feature, "rich_now")
    assert window._built_lazy_pages == set()

    window.open_page("library")
    app.processEvents()
    assert not hasattr(window, "library_browser")
    QTest.qWait(window._page_refresh_delay_ms + 10)
    app.processEvents()
    assert hasattr(window, "library_browser")
    assert "library" in window._built_lazy_pages

    window.open_page("now_playing")
    app.processEvents()
    assert not hasattr(window.playback_feature, "rich_now")
    QTest.qWait(window._page_refresh_delay_ms + 10)
    app.processEvents()
    assert hasattr(window.playback_feature.rich_now, "import_lyrics_button")
    assert hasattr(window.playback_feature.rich_now, "paste_lyrics_button")
    assert hasattr(window.playback_feature.rich_now, "find_lyrics_plugin_button")
    assert hasattr(window.playback_feature.rich_now, "online_lyrics_button")
    assert window.playback_feature.rich_now.online_lyrics_button.text() == "Refresh lyrics"
    assert hasattr(window.playback_feature.rich_now, "auto_online_lyrics")
    assert window.playback_feature.rich_now.auto_online_lyrics.isChecked() is False
    assert "now_playing" in window._built_lazy_pages
    assert hasattr(window, "sources_feature")
    assert set(window.sources_feature.source_feature_buttons) == {
        "",
        "search",
        "lyrics",
        "artwork",
        "recommendations",
        "context",
    }
    assert window.sources_feature.source_feature_buttons["lyrics"].text() == "Lyrics"
    assert window.playback_feature.now_views.tabText(0) == "Now Playing"
    assert window.playback_feature.now_views.tabText(1) == "Visuals"
    assert window.playlists_stack.currentWidget() is window.playlists_empty
    assert (
        window.journey_workspace.archive.journey_recipes_stack.currentWidget()
        is window.journey_workspace.archive.journey_recipes_empty
    )

    window.playback_feature.on_playing_changed(True)
    assert window.playback_feature.play_button.text() == "❚❚"
    window.playback_feature.on_playing_changed(False)
    assert window.playback_feature.play_button.text() == "▶"

    window.open_page("sources")
    app.processEvents()
    assert window.sources_feature.source_primary_button.text() == "Use selected"
    window.open_page("explore")
    app.processEvents()
    assert window.stack.currentWidget() is window.pages["explore"]
    assert bool(window.nav_buttons["explore"].property("active"))

    window.power_toggle.setChecked(False)
    app.processEvents()
    assert not window.sources_feature.source_power_panel.isVisible()
    assert not window.playback_feature.player_power_actions.isVisible()

    enter_chiasm_mode(window)
    app.processEvents()
    assert window.centralWidget() is window.chiasm_feature.page
    assert not window._inherited_shell_widget.isVisible()
    assert window.menuBar().isHidden()
    assert all(not action.isEnabled() for action in window.findChildren(QAction))
    assert window.findChild(QPushButton, "chiasmAddFolder") is not None
    assert window.chiasm_feature.chiasm_canvas is not None

    window.close()
    app.processEvents()


def test_cached_album_artwork_prioritizes_viewport_and_scroll_target():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    browser.resize(1100, 760)
    browser.show()

    batches = []
    browser.artworkRequested.connect(
        lambda rows: batches.append([dict(row) for row in rows])
    )

    tracks = [
        _track(
            f"/viewport/albums/{index:03d}.flac",
            f"Artist {index:03d}",
            f"Album {index:03d}",
            f"Track {index:03d}",
            1,
            1980 + (index % 40),
        )
        for index in range(120)
    ]
    browser.set_catalog(tracks)
    app.processEvents()
    app.processEvents()
    if not batches:
        browser._emit_viewport_artwork_batch(
            "albums",
            browser._artwork_generation("albums"),
        )

    assert batches
    first = batches[0]
    assert 1 <= len(first) <= browser._viewport_artwork_batch_size

    visible, near, _distant = browser._card_artwork_priority("albums")
    priority_keys = {
        str(row.get("key") or "")
        for row in visible + near
    }
    assert {row["key"] for row in first} <= priority_keys
    assert browser.last_artwork_priority_metrics["requested_now"] <= 12

    # Move to the bottom while the first cache batch is still in flight.
    # Completing that old batch should continue from the new viewport, not
    # from the top of the collection.
    scrollbar = browser.album_scroll.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    app.processEvents()
    before = len(batches)
    browser.set_artwork({row["key"]: "" for row in first})
    app.processEvents()
    app.processEvents()
    if len(batches) == before:
        browser._emit_viewport_artwork_batch(
            "albums",
            browser._artwork_generation("albums"),
        )

    assert len(batches) > before
    second = batches[-1]
    visible2, near2, distant2 = browser._card_artwork_priority("albums")
    bottom_priority = {
        str(row.get("key") or "")
        for row in visible2 + near2
    }
    assert {row["key"] for row in second} <= bottom_priority
    assert {row["key"] for row in second}.isdisjoint(
        {row["key"] for row in first}
    )
    assert browser.last_artwork_priority_metrics["scroll_value"] > 0

    # Once viewport work is exhausted, distant cache hydration stays tiny.
    browser._album_cache_inflight = False
    for row in visible2 + near2:
        browser._art_requested.add(str(row.get("key") or ""))
    distant_keys = {
        str(row.get("key") or "")
        for row in distant2
    }
    before = len(batches)
    browser._emit_viewport_artwork_batch(
        "albums",
        browser._artwork_generation("albums"),
        idle=True,
    )
    if distant_keys:
        assert len(batches) == before + 1
        idle_batch = batches[-1]
        assert 1 <= len(idle_batch) <= browser._idle_artwork_batch_size
        assert {row["key"] for row in idle_batch} <= distant_keys

    browser.deleteLater()
    app.processEvents()


def test_cached_artist_photos_use_same_viewport_priority():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    browser.resize(1100, 760)
    browser.show()

    batches = []
    browser.artistImageCacheRequested.connect(
        lambda rows: batches.append([dict(row) for row in rows])
    )
    tracks = [
        _track(
            f"/viewport/artists/{index:03d}.flac",
            f"Artist {index:03d}",
            f"Album {index:03d}",
            f"Track {index:03d}",
            1,
            1990 + (index % 30),
        )
        for index in range(120)
    ]
    browser.set_catalog(tracks)
    browser.set_view("artists")
    app.processEvents()
    app.processEvents()
    if not batches:
        browser._emit_viewport_artwork_batch(
            "artists",
            browser._artwork_generation("artists"),
        )

    assert batches
    first = batches[0]
    assert 1 <= len(first) <= browser._viewport_artwork_batch_size
    visible, near, _distant = browser._card_artwork_priority("artists")
    priority_keys = {
        str(row.get("key") or "")
        for row in visible + near
    }
    assert {row["key"] for row in first} <= priority_keys
    assert browser.last_artwork_priority_metrics["kind"] == "artists"

    browser.deleteLater()
    app.processEvents()


def test_artist_photo_lookup_runs_in_bounded_batches_with_progress():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    tracks = [
        _track(
            f"/artists/{index:02d}.mp3",
            f"Artist {index:02d}",
            f"Album {index:02d}",
            f"Track {index:02d}",
            1,
            2000 + index,
        )
        for index in range(15)
    ]
    browser.set_catalog(tracks)
    browser.set_view("artists")

    batches = []
    browser.artistImageRequested.connect(
        lambda rows: batches.append([dict(row) for row in rows])
    )

    browser._request_online_artwork()
    assert len(batches) == 1
    assert len(batches[0]) == 4
    assert browser.artist_image_lookup_remaining() == 15
    assert browser.images_button.isEnabled() is False
    assert browser.artwork_progress_panel.isVisible() is False or browser.artwork_progress.value() == 0

    first_outcomes = [
        {"key": row["key"], "status": "found" if i < 2 else "no_match"}
        for i, row in enumerate(batches[0])
    ]
    browser.finish_artist_image_lookup_batch(first_outcomes)

    assert len(batches) == 2
    assert len(batches[1]) == 4
    snapshot = browser.artwork_lookup_snapshot()
    assert snapshot["completed"] == 4
    assert snapshot["found"] == 2
    assert snapshot["skipped"] == 2
    assert snapshot["failed"] == 0
    assert snapshot["total"] == 15

    # Finish the remaining batches.
    while browser._artist_lookup_active:
        current = list(browser._artist_lookup_inflight_rows)
        outcomes = [
            {"key": row["key"], "status": "no_match"}
            for row in current
        ]
        browser.finish_artist_image_lookup_batch(outcomes)

    snapshot = browser.artwork_lookup_snapshot()
    assert snapshot["completed"] == 15
    assert snapshot["total"] == 15
    assert snapshot["active"] is False
    assert len(batches) == 4
    assert [len(batch) for batch in batches] == [4, 4, 4, 3]
    assert browser.images_button.isEnabled() is True
    assert browser.images_button.text() == "Get artist photos"
    browser.deleteLater()
    app.processEvents()

def test_album_artwork_lookup_runs_all_missing_albums_in_bounded_batches():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    tracks = [
        _track(
            f"/albums/{index:02d}.mp3",
            f"Artist {index:02d}",
            f"Album {index:02d}",
            f"Track {index…16034 tokens truncated…dex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    started = threading.Event()
    release = threading.Event()
    worker_thread = {}

    class SlowRunner:
        def __init__(
            self,
            data_dir,
            roots,
            *,
            on_progress,
            on_done,
            on_error,
            **_kwargs,
        ):
            self.roots = [Path(x) for x in roots]
            self.on_progress = on_progress
            self.on_done = on_done
            self.on_error = on_error
            self.paused = False

        def start(self):
            def work():
                worker_thread["name"] = threading.current_thread().name
                worker_thread["main"] = (
                    threading.current_thread() is threading.main_thread()
                )
                started.set()
                release.wait(timeout=2)
                self.on_done(
                    {
                        "tracks": [],
                        "metrics": {
                            "thread_name": threading.current_thread().name,
                            "main_thread": False,
                            "root_count": 1,
                            "tracks_indexed": 0,
                            "total_seconds": 0.1,
                        },
                        "changes": {},
                        "cancelled": False,
                    }
                )

            threading.Thread(target=work, name="fake-scan-process", daemon=True).start()

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def cancel(self, **_kwargs):
            self.on_done({"tracks": [], "cancelled": True})

        def shutdown(self, **_kwargs):
            release.set()

    monkeypatch.setattr(library_scan_process, "LibraryScanProcess", SlowRunner)

    window = main_window.MainWindow()
    root = tmp_path / "slow-nas"
    root.mkdir()
    window.providers.configure_local_roots([root])

    apply_threads = []
    original_apply = window.providers.apply_local_scan_snapshot

    def record_apply(snapshot):
        apply_threads.append(
            threading.current_thread() is threading.main_thread()
        )
        return original_apply(snapshot)

    monkeypatch.setattr(
        window.providers,
        "apply_local_scan_snapshot",
        record_apply,
    )

    timer_fired = []
    QTimer.singleShot(0, lambda: timer_fired.append(True))
    window._start_local_scan("test")

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and (not started.is_set() or not timer_fired):
        app.processEvents()
        time.sleep(0.005)

    assert started.is_set()
    assert timer_fired == [True]
    assert window.local_scan.active is True
    assert worker_thread["main"] is False

    release.set()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and window.local_scan.active:
        app.processEvents()
        time.sleep(0.005)

    assert window.local_scan.active is False
    assert apply_threads == [True]
    window.close()
    app.processEvents()


def test_root_change_during_scan_discards_stale_snapshot(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    root_a.mkdir()
    root_b.mkdir()

    first_started = threading.Event()
    first_cancelled = threading.Event()
    calls = []

    class RestartingRunner:
        def __init__(
            self,
            data_dir,
            roots,
            *,
            on_progress,
            on_done,
            on_error,
            **_kwargs,
        ):
            self.roots = [Path(x) for x in roots]
            self.on_done = on_done
            self.on_error = on_error
            self.paused = False
            self.cancel_event = threading.Event()
            calls.append(tuple(str(x) for x in self.roots))
            self.number = len(calls)

        def start(self):
            if self.number == 1:
                def first():
                    first_started.set()
                    self.cancel_event.wait(timeout=2)
                    first_cancelled.set()
                    self.on_done(
                        {
                            "tracks": [],
                            "metrics": {},
                            "changes": {},
                            "cancelled": True,
                        }
                    )
                threading.Thread(target=first, daemon=True).start()
                return

            fresh = {
                "provider_id": "local",
                "track_id": str(root_b / "fresh.flac"),
                "local_path": str(root_b / "fresh.flac"),
                "title": "Fresh",
                "artist": "New",
            }
            threading.Thread(
                target=lambda: self.on_done(
                    {
                        "tracks": [fresh],
                        "metrics": {"tracks_indexed": 1, "main_thread": False},
                        "changes": {"added": 1},
                        "cancelled": False,
                    }
                ),
                daemon=True,
            ).start()

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def cancel(self, **_kwargs):
            self.cancel_event.set()

        def shutdown(self, **_kwargs):
            self.cancel_event.set()

    monkeypatch.setattr(library_scan_process, "LibraryScanProcess", RestartingRunner)

    window = main_window.MainWindow()
    window.providers.configure_local_roots([root_a])
    window._start_local_scan("first")

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not first_started.is_set():
        app.processEvents()
        time.sleep(0.005)
    assert first_started.is_set()

    window.providers.configure_local_roots([root_a, root_b])
    window._start_local_scan("roots changed")
    assert window.local_scan.pending is True

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and (
        window.local_scan.active or len(calls) < 2
    ):
        app.processEvents()
        time.sleep(0.005)

    assert first_cancelled.is_set()
    catalog = window.providers.local_catalog()
    assert len(calls) == 2
    assert calls[0] == (str(root_a),)
    assert calls[1] == (str(root_a), str(root_b))
    assert len(catalog) == 1
    assert catalog[0]["title"] == "Fresh"

    window.close()
    app.processEvents()


def test_library_scan_progress_panel_is_clear_and_reassuring():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    browser.show()

    browser.begin_scan("test")
    app.processEvents()

    assert browser.scan_progress_panel.isVisible()
    assert browser.scan_progress.maximum() == 0
    assert "never copied" in browser.scan_safety_note.text().lower()
    assert browser.scan_pause_button.text() == "Pause"
    assert browser.scan_cancel_button.text() == "Cancel"

    pause_requests = []
    cancel_requests = []
    browser.scanPauseRequested.connect(lambda: pause_requests.append(True))
    browser.scanCancelRequested.connect(lambda: cancel_requests.append(True))
    browser.scan_pause_button.click()
    browser.scan_cancel_button.click()
    assert pause_requests == [True]
    assert cancel_requests == [True]

    browser.set_scan_progress(
        {
            "phase": "discovering",
            "audio_files_seen": 12700,
            "completed": 0,
            "total": 0,
            "current": "Massive Attack",
        }
    )
    assert "12,700" in browser.scan_progress_summary.text()
    assert "Massive Attack" in browser.scan_progress_detail.text()

    browser.set_scan_progress(
        {
            "phase": "metadata",
            "audio_files_seen": 12700,
            "completed": 6350,
            "total": 12700,
            "current": "Teardrop.flac",
        }
    )
    assert browser.scan_progress.maximum() == 12700
    assert browser.scan_progress.value() == 6350
    assert "6,350" in browser.scan_progress_summary.text()
    assert browser.scan_progress_detail.text() == "Teardrop.flac"

    browser.set_scan_progress(
        {
            "phase": "metadata",
            "audio_files_seen": 12700,
            "completed": 0,
            "total": 0,
            "unchanged": 12700,
        }
    )
    assert browser.scan_progress.value() == 1
    assert "already up to date" in browser.scan_progress_summary.text().lower()
    assert "12,700 unchanged" in browser.scan_progress_detail.text()
    assert "no audio files need reopening" in browser.scan_progress_detail.text()

    browser.set_scan_progress({"phase": "saving"})
    assert "saving library index" in browser.scan_progress_summary.text().lower()
    assert "on this computer" in browser.scan_progress_detail.text().lower()

    browser.set_scan_paused(True)
    assert browser.scan_pause_button.text() == "Resume"
    assert "paused" in browser.scan_progress_title.text().lower()

    browser.set_scan_cancelling()
    assert not browser.scan_pause_button.isEnabled()
    assert not browser.scan_cancel_button.isEnabled()

    browser.finish_scan("cancelled")
    assert "cancelled" in browser.scan_progress_title.text().lower()
    assert "existing library" in browser.scan_progress_summary.text().lower()

    browser.finish_scan(
        "complete",
        count=12700,
        changes={
            "unchanged": 12695,
            "added": 2,
            "changed": 2,
            "removed": 1,
        },
    )
    assert "12,700" in browser.scan_progress_summary.text()
    assert "12,695 unchanged" in browser.scan_progress_detail.text()
    assert "2 new" in browser.scan_progress_detail.text()
    assert "2 updated" in browser.scan_progress_detail.text()
    assert "1 removed" in browser.scan_progress_detail.text()

    browser.deleteLater()
    app.processEvents()


def test_cancelled_main_window_scan_keeps_existing_catalog(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    worker_started = threading.Event()

    class CancellableRunner:
        def __init__(
            self,
            data_dir,
            roots,
            *,
            on_progress,
            on_done,
            on_error,
            **_kwargs,
        ):
            self.roots = [Path(x) for x in roots]
            self.on_done = on_done
            self.paused = False

        def start(self):
            worker_started.set()

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def cancel(self, **_kwargs):
            threading.Thread(
                target=lambda: self.on_done(
                    {
                        "tracks": [],
                        "metrics": {"tracks_indexed": 0, "main_thread": False},
                        "changes": {},
                        "cancelled": True,
                        "hard_cancelled": True,
                    }
                ),
                daemon=True,
            ).start()

        def shutdown(self, **_kwargs):
            pass

    monkeypatch.setattr(library_scan_process, "LibraryScanProcess", CancellableRunner)

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("library")
    root = tmp_path / "nas"
    root.mkdir()
    window.providers.configure_local_roots([root])

    existing = {
        "provider_id": "local",
        "track_id": "/existing.flac",
        "local_path": "/existing.flac",
        "title": "Existing",
        "artist": "Existing Artist",
        "album": "Existing Album",
    }
    window.providers.apply_local_scan_snapshot(
        {"tracks": [existing], "metrics": {"tracks_indexed": 1}}
    )
    window._refresh_library()

    window._start_local_scan("cancel test")
    assert worker_started.is_set()
    window._cancel_local_scan()

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and window.local_scan.active:
        app.processEvents()
        time.sleep(0.005)

    assert window.local_scan.active is False
    catalog = window.providers.local_catalog()
    assert len(catalog) == 1
    assert catalog[0]["title"] == "Existing"
    assert "cancelled" in window.library_browser.scan_progress_title.text().lower()
    assert "unresponsive scanner terminated" in window.statusBar().currentMessage()

    window.close()
    app.processEvents()


def test_indexed_library_loads_on_startup_without_automatic_rescan(
    monkeypatch,
    tmp_path,
):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
        from melodex.library_index import LocalLibraryIndex
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    root = tmp_path / "offline-synology"
    (tmp_path / "sources.json").write_text(
        __import__("json").dumps({"local_roots": [str(root)]}),
        encoding="utf-8",
    )

    index = LocalLibraryIndex(tmp_path / "library-index.sqlite3")
    index.sync_roots([root])
    cached = {
        "provider_id": "local",
        "track_id": str(root / "Artist" / "song.flac"),
        "local_path": str(root / "Artist" / "song.flac"),
        "artist": "Cached Artist",
        "album": "Cached Album",
        "title": "Cached Song",
        "source": "local",
    }
    index.replace_scan(
        [root],
        {
            "tracks": [cached],
            "index_tracks": [dict(cached)],
            "root_states": [{"path": str(root), "available": True}],
            "metrics": {"tracks_indexed": 1},
            "cancelled": False,
        },
    )

    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)
    scans = []
    monkeypatch.setattr(
        main_window.MainWindow,
        "_start_local_scan",
        lambda self, reason="scan": scans.append(reason),
    )

    window = main_window.MainWindow()
    window.show()
    app.processEvents()

    assert scans == []
    assert window.providers.local_index_ready() is True
    assert len(window.providers.local_catalog()) == 1
    assert window.providers.local_catalog()[0]["title"] == "Cached Song"
    assert "1 track in your library" in window.home_status.text()

    window.close()
    app.processEvents()


def test_existing_roots_without_index_trigger_one_migration_scan(
    monkeypatch,
    tmp_path,
):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    root = tmp_path / "old-library"
    (tmp_path / "sources.json").write_text(
        __import__("json").dumps({"local_roots": [str(root)]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)
    scans = []
    monkeypatch.setattr(
        main_window.MainWindow,
        "_start_local_scan",
        lambda self, reason="scan": scans.append(reason),
    )

    window = main_window.MainWindow()
    window.show()
    for _ in range(5):
        app.processEvents()
        time.sleep(0.005)

    assert scans == ["initial index"]
    assert window.providers.local_index_ready() is False

    window.close()
    app.processEvents()


def test_gui_library_scan_uses_isolated_runner_not_provider_thread(
    monkeypatch,
    tmp_path,
):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    created = []

    class ImmediateRunner:
        def __init__(
            self,
            data_dir,
            roots,
            *,
            on_progress,
            on_done,
            on_error,
            **_kwargs,
        ):
            self.roots = [Path(x) for x in roots]
            self.on_done = on_done
            self.paused = False
            created.append(
                {
                    "data_dir": Path(data_dir),
                    "roots": list(self.roots),
                }
            )

        def start(self):
            threading.Thread(
                target=lambda: self.on_done(
                    {
                        "tracks": [],
                        "metrics": {"tracks_indexed": 0, "main_thread": False},
                        "changes": {},
                        "cancelled": False,
                    }
                ),
                daemon=True,
            ).start()

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def cancel(self, **_kwargs):
            self.on_done({"tracks": [], "cancelled": True})

        def shutdown(self, **_kwargs):
            pass

    monkeypatch.setattr(library_scan_process, "LibraryScanProcess", ImmediateRunner)

    window = main_window.MainWindow()
    root = tmp_path / "nas"
    window.providers.configure_local_roots([root])

    monkeypatch.setattr(
        window.providers,
        "scan_local_roots_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("GUI must not scan the library in its own process")
        ),
    )
    monkeypatch.setattr(
        window.providers,
        "persist_local_scan_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("GUI must not persist the scan in its own worker thread")
        ),
    )

    window._start_local_scan("isolated process test")
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and window.local_scan.active:
        app.processEvents()
        time.sleep(0.005)

    assert window.local_scan.active is False
    assert len(created) == 1
    assert created[0]["data_dir"] == tmp_path
    assert created[0]["roots"] == [root]

    window.close()
    app.processEvents()
