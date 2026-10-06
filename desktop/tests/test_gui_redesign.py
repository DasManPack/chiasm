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
            f"Track {index:02d}",
            1,
            1990 + index,
        )
        for index in range(17)
    ]
    browser.set_catalog(tracks)
    browser.set_view("albums")

    batches = []
    browser.onlineArtworkRequested.connect(
        lambda rows: batches.append([dict(row) for row in rows])
    )

    browser._request_online_artwork()
    assert len(batches) == 1
    assert len(batches[0]) == 4
    assert browser.album_artwork_lookup_remaining() == 17

    while browser._album_lookup_active:
        current = list(browser._album_lookup_inflight_rows)
        outcomes = [
            {"key": row["key"], "status": "found"}
            for row in current
        ]
        browser.finish_album_artwork_lookup_batch(outcomes)

    snapshot = browser.artwork_lookup_snapshot()
    assert snapshot["completed"] == 17
    assert snapshot["found"] == 17
    assert snapshot["total"] == 17
    assert [len(batch) for batch in batches] == [4, 4, 4, 4, 1]
    assert browser.images_button.isEnabled() is True
    assert browser.images_button.text() == "Find missing artwork"
    browser.deleteLater()
    app.processEvents()

def test_artwork_progress_labels_are_compact():
    try:
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    assert LibraryBrowser._progress_item_label("Air") == "Air"
    label = LibraryBrowser._progress_item_label(
        "A Winged Victory For The Sullen",
        22,
    )
    assert len(label) <= 22
    assert label.endswith("…")



def test_source_card_uses_icon_and_origin_badge():
    try:
        from PySide6.QtWidgets import QApplication, QLabel
        from melodex.ux_components import SourceCard
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    card = SourceCard(
        "Lyrics helper",
        "Adds lyrics to Now Playing.",
        "Ready",
        kind="Lyrics",
        icon_key="lyrics",
        origin="Registry",
    )
    badge = card.findChild(QLabel, "sourceBadge")
    assert badge is not None
    assert badge.text() == "“"
    assert card.findChild(QLabel, "originPill") is not None
    card.deleteLater()
    app.processEvents()



def test_plugin_centre_is_outcome_and_management_focused(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication, QLabel
        import melodex.main_window as main_window
        from melodex.plugin_directory import PluginDirectoryDialog, PluginDirectoryCard
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)
    monkeypatch.setattr(PluginDirectoryDialog, "load_registry", lambda self, force=False: None)

    window = main_window.MainWindow()
    dialog = PluginDirectoryDialog(window.providers, parent=window)

    assert dialog.view.itemData(0) == "all"
    assert dialog.view.findData("installed") >= 0
    assert dialog.view.findData("available") >= 0
    assert dialog.view.findData("setup") >= 0
    assert dialog.view.findData("updates") >= 0
    assert set(dialog.view_buttons) == {
        "all",
        "installed",
        "available",
        "setup",
        "updates",
    }
    assert dialog.toggle_button.text() == "Disable"
    assert dialog.remove_button.text() == "Remove"
    assert dialog.toggle_button.isEnabled() is False
    assert dialog.remove_button.isEnabled() is False

    lyrics_entry = {
        "id": "org.example.lyrics",
        "name": "Lyrics helper",
        "kind": "enrichment",
        "status": "community",
        "description": "Adds lyrics.",
        "capabilities": ["lyrics"],
        "distribution": {},
        "source": {},
        "review": {},
        "permissions": [],
    }
    assert PluginDirectoryDialog._where_used(lyrics_entry) == "Now Playing → Lyrics"
    assert PluginDirectoryDialog._where_used(
        {**lyrics_entry, "kind": "provider", "capabilities": ["search", "playback"]}
    ) == "Explore → Search everything"

    card = PluginDirectoryCard(
        lyrics_entry,
        "Setup needed",
        installed=True,
    )
    state = card.findChild(QLabel, "pluginDirectoryState")
    assert state is not None
    assert state.text() == "Setup needed"
    assert state.property("state") == "attention"
    assert card.findChild(QLabel, "pluginCapabilityChip") is not None
    usage = card.findChild(QLabel, "pluginDirectoryUsage")
    assert usage is not None
    assert "Now Playing" in usage.text()

    dialog.plugins = [lyrics_entry]
    dialog._apply_filter()
    assert dialog.rows.count() == 1
    assert dialog.view_buttons["all"].text() == "All  1"
    assert dialog.view_buttons["available"].text() == "Available  1"
    assert dialog.list_stack.currentWidget() is dialog.rows

    dialog._select_view("installed")
    assert dialog.rows.count() == 0
    assert dialog.list_stack.currentWidget() is dialog.empty_state
    assert dialog.empty_title.text() == "No optional plugins installed"
    assert dialog.view_buttons["installed"].isChecked()

    dialog._clear_filters()
    assert dialog.view.currentData() == "all"
    assert dialog.rows.count() == 1

    card.deleteLater()
    dialog.close()
    window.close()
    app.processEvents()




def test_heavy_pages_build_once_after_navigation_shell(monkeypatch, tmp_path):
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
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

    assert not hasattr(window, "library_browser")
    assert "library" not in window._built_lazy_pages

    window.open_page("library")
    app.processEvents()
    assert window.stack.currentWidget() is window.pages["library"]
    assert not hasattr(window, "library_browser")

    QTest.qWait(window._page_refresh_delay_ms + 10)
    app.processEvents()
    first_browser = window.library_browser
    first_metric = window.lazy_page_build_metrics["library"]
    assert first_metric >= 0.0

    window.open_page("home")
    app.processEvents()
    window.open_page("library")
    QTest.qWait(window._page_refresh_delay_ms + 10)
    app.processEvents()

    assert window.library_browser is first_browser
    assert window.lazy_page_build_metrics["library"] == first_metric

    window.close()
    app.processEvents()


def test_plugins_surface_where_their_features_are_used(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
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

    extensions = [
        {
            "id": "org.example.art",
            "name": "Cover Helper",
            "enabled": True,
            "capabilities": ["artwork"],
            "configuration_status": {"declared": False, "ready": True},
        },
        {
            "id": "org.example.lyrics",
            "name": "Lyric Helper",
            "enabled": True,
            "capabilities": ["lyrics"],
            "configuration_status": {"declared": False, "ready": True},
        },
        {
            "id": "org.example.context",
            "name": "Liner Notes",
            "enabled": True,
            "capabilities": ["context"],
            "configuration_status": {"declared": False, "ready": True},
        },
        {
            "id": "org.example.recommend",
            "name": "Taste Helper",
            "enabled": True,
            "capabilities": ["library_suggestions"],
            "configuration_status": {"declared": False, "ready": True},
        },
        {
            "id": "org.example.disabled",
            "name": "Disabled Helper",
            "enabled": False,
            "capabilities": ["artwork", "lyrics"],
            "configuration_status": {"declared": False, "ready": True},
        },
        {
            "id": "org.example.setup",
            "name": "Needs Setup",
            "enabled": True,
            "capabilities": ["context"],
            "configuration_status": {"declared": True, "ready": False},
        },
    ]
    monkeypatch.setattr(
        window.providers,
        "extensions",
        lambda **_kwargs: list(extensions),
    )
    window.navigation.ensure_lazy_page_built("library")
    window.navigation.ensure_lazy_page_built("now_playing")

    window._refresh_plugin_presence()
    app.processEvents()

    assert "Cover Helper" in window.artwork_plugin_presence.label.text()
    assert "Disabled Helper" not in window.artwork_plugin_presence.label.text()
    assert bool(window.artwork_plugin_presence.property("active"))

    assert "Taste Helper" in window.recommendation_plugin_presence.label.text()
    assert not hasattr(window.playback_feature.rich_now, "lyrics_plugin_presence")
    assert "Liner Notes" in window.playback_feature.rich_now.context_plugin_presence.label.text()
    assert "Needs Setup" not in window.playback_feature.rich_now.context_plugin_presence.label.text()

    opened = []
    monkeypatch.setattr(
        window.sources_feature,
        "open_plugin_directory",
        lambda capability="": opened.append(capability),
    )

    window.search_plugin_presence.action.click()
    window.artwork_plugin_presence.action.click()
    window.recommendation_plugin_presence.action.click()
    window.playback_feature.rich_now.manage_lyrics_sources_action.trigger()
    window.playback_feature.rich_now.context_plugin_presence.action.click()

    assert opened == [
        "search",
        "artwork",
        "library_suggestions",
        "lyrics",
        "context",
    ]

    window.close()
    app.processEvents()


def test_feature_presence_bar_distinguishes_core_only_from_active_plugins():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.ux_components import FeaturePresenceBar
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    bar = FeaturePresenceBar(
        "Artwork helpers",
        baseline="Built-in matching is active",
        action_text="Add artwork helper…",
    )

    assert "Built-in matching is active" in bar.label.text()
    assert not bool(bar.property("active"))

    bar.set_items(["Cover Helper", "Cover Helper", "Second Source"])
    assert "Cover Helper" in bar.label.text()
    assert "Second Source" in bar.label.text()
    assert bool(bar.property("active"))

    bar.deleteLater()
    app.processEvents()



def test_lyrics_lookup_outcomes_are_distinct_in_now_playing(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
        from melodex.metadata import track_key
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("now_playing")
    widget = window.playback_feature.rich_now
    widget.track = {
        "artist": "Example Artist",
        "title": "Example Song",
        "provider_id": "local",
        "track_id": "example-song",
    }
    key = track_key(widget.track)

    widget._stage_loaded(
        key,
        "community lyrics",
        {
            "lyrics": {
                "text": "",
                "synced": [],
                "source": "LRCLIB community lyrics",
                "instrumental": False,
                "status": "not_found",
                "error": "",
            }
        },
    )
    assert "No confident lyric match" in widget.lyrics.toPlainText()
    assert widget.online_lyrics_button.text() == "Try again"
    assert "no confident match" in widget.lyrics_source.text().casefold()

    widget._stage_loaded(
        key,
        "community lyrics",
        {
            "lyrics": {
                "text": "",
                "synced": [],
                "source": "LRCLIB",
                "instrumental": False,
                "status": "error",
                "error": "temporary service error",
            }
        },
    )
    assert "could not connect" in widget.lyrics.toPlainText().casefold()
    assert "temporary service error" in widget.lyrics_source.text()

    widget._stage_loaded(
        key,
        "community lyrics",
        {
            "lyrics": {
                "text": "",
                "synced": [],
                "source": "LRCLIB community lyrics",
                "instrumental": True,
                "status": "instrumental",
                "error": "",
            }
        },
    )
    assert "Instrumental track" in widget.lyrics.toPlainText()
    assert widget.online_lyrics_button.text() == "Refresh lyrics"

    window.close()
    app.processEvents()



def test_synced_lyrics_seek_source_switch_and_editability(monkeypatch, tmp_path):
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("now_playing")
    widget = window.playback_feature.rich_now
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"audio")
    widget.track = {
        "artist": "Example Artist",
        "title": "Example Song",
        "provider_id": "local",
        "track_id": str(audio),
        "local_path": str(audio),
    }

    local = {
        "text": "First line\nSecond line",
        "synced": [
            {"time_ms": 1000, "text": "First line"},
            {"time_ms": 3500, "text": "Second line"},
        ],
        "source": "Example Song.lrc",
        "path": str(tmp_path / "Example Song.lrc"),
    }
    online = {
        "text": "Online first\nOnline second",
        "synced": [],
        "source": "LRCLIB community lyrics",
        "status": "found",
        "provenance": {"source_extension_id": "core.lrclib-on-demand"},
    }

    widget._local_lyrics = dict(local)
    widget._online_lyrics = dict(online)
    widget._active_lyrics_source = "online"
    widget._apply_lyrics(online)

    assert widget.lyrics_source_picker.isVisible() is False or widget.lyrics_source_picker.count() == 2
    assert widget.lyrics_source_picker.count() == 2
    assert widget.edit_lyrics_button.isEnabled() is False
    assert widget.translate_lyrics_button.isEnabled() is True

    local_index = widget.lyrics_source_picker.findData("local")
    widget.lyrics_source_picker.setCurrentIndex(local_index)
    assert widget._active_lyrics_source == "local"
    assert widget._current_lyrics["source"] == "Example Song.lrc"
    assert widget.edit_lyrics_button.isEnabled() is True
    assert widget.fullscreen_lyrics_button.isEnabled() is True

    seeks = []
    widget.lyricsSeekRequested.connect(seeks.append)
    widget._lyrics_anchor_clicked(QUrl("seek:3500"))
    assert seeks == [3500]

    widget.set_position(3600)
    assert widget._lyric_index == 1
    assert "Second line" in widget.lyrics.toPlainText()

    window.close()
    app.processEvents()


def test_fullscreen_lyrics_tracks_synced_position(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication, QDialog
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)
    monkeypatch.setattr(QDialog, "showFullScreen", lambda self: self.show())

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("now_playing")
    widget = window.playback_feature.rich_now
    widget.track = {
        "artist": "Example Artist",
        "title": "Example Song",
        "provider_id": "local",
        "track_id": "example-song",
        "local_path": str(tmp_path / "song.mp3"),
    }
    lyrics = {
        "text": "One\nTwo",
        "synced": [
            {"time_ms": 1000, "text": "One"},
            {"time_ms": 4000, "text": "Two"},
        ],
        "source": "Example Song.lrc",
        "path": str(tmp_path / "Example Song.lrc"),
    }
    widget._local_lyrics = dict(lyrics)
    widget._active_lyrics_source = "local"
    widget._apply_lyrics(lyrics)

    canvas = window.playback_feature.living_canvas
    widget._show_fullscreen_lyrics()
    app.processEvents()
    assert canvas._lyric_flow_dialog is not None
    assert canvas._lyric_flow_scene is not None

    window.playback_feature.on_position(1500, 5000)
    app.processEvents()
    assert canvas._lyric_flow_scene._lyrics.current == "One"

    window.playback_feature.on_position(4100, 5000)
    app.processEvents()
    assert widget._lyric_index == 1
    assert canvas._lyric_flow_scene._lyrics.current == "Two"

    dialog = canvas._lyric_flow_dialog
    if dialog is not None:
        dialog.close()
    window.close()
    app.processEvents()


def test_translate_lyrics_is_explicit_and_uses_configured_llm(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
        import melodex.main_window as main_window
        from melodex.llm_bridge import LLMSettings
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    settings = LLMSettings(
        provider="ollama",
        endpoint="http://localhost:11434/api/chat",
        model="qwen-test",
    )
    monkeypatch.setattr(window, "_llm_settings", lambda: settings)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.Yes,
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args, **kwargs: ("Chinese", True),
    )

    prompts = []
    monkeypatch.setattr(
        window.llm,
        "complete",
        lambda settings, prompt, context, history: prompts.append(prompt) or "翻译结果",
    )
    monkeypatch.setattr(
        window,
        "_run_async",
        lambda work, done, *args, **kwargs: done(work()),
    )
    shown = []
    monkeypatch.setattr(
        window.playback_feature,
        "_show_lyrics_translation",
        lambda language, text: shown.append((language, text)),
    )

    window.playback_feature._translate_lyrics({
        "text": "First line\nSecond line",
        "artist": "Example Artist",
        "title": "Example Song",
    })

    assert len(prompts) == 1
    assert "Chinese" in prompts[0]
    assert "First line\nSecond line" in prompts[0]
    assert shown == [("Chinese", "翻译结果")]
    assert window.state.get_text("lyrics_translation_language", "") == "Chinese"

    window.close()
    app.processEvents()


def test_online_lyrics_translation_signal_contains_only_current_lyrics(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("now_playing")
    widget = window.playback_feature.rich_now
    widget.track = {
        "artist": "Artist",
        "title": "Song",
        "provider_id": "remote",
        "track_id": "song",
    }
    lyrics = {
        "text": "Line one\nLine two",
        "synced": [],
        "source": "LRCLIB community lyrics",
        "status": "found",
        "provenance": {"source_extension_id": "core.lrclib-on-demand"},
    }
    widget._online_lyrics = dict(lyrics)
    widget._active_lyrics_source = "online"
    widget._apply_lyrics(lyrics)

    widget.lyricsTranslationRequested.disconnect(
        window.playback_feature._translate_lyrics
    )
    payloads = []
    widget.lyricsTranslationRequested.connect(payloads.append)
    widget.translate_lyrics_button.click()
    app.processEvents()

    assert len(payloads) == 1
    assert payloads[0]["text"] == "Line one\nLine two"
    assert payloads[0]["artist"] == "Artist"
    assert payloads[0]["title"] == "Song"
    assert widget.edit_lyrics_button.isEnabled() is False

    window.close()
    app.processEvents()



def test_online_lyrics_miss_does_not_replace_existing_local_lyrics(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
        from melodex.metadata import track_key
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("now_playing")
    widget = window.playback_feature.rich_now
    widget.track = {
        "artist": "Example Artist",
        "title": "Example Song",
        "provider_id": "local",
        "track_id": "example-song",
        "local_path": str(tmp_path / "song.mp3"),
    }
    local = {
        "text": "My local lyric",
        "synced": [],
        "source": "Example Song.txt",
        "path": str(tmp_path / "Example Song.txt"),
    }
    widget._local_lyrics = dict(local)
    widget._active_lyrics_source = "local"
    widget._apply_lyrics(local)

    widget._stage_loaded(
        track_key(widget.track),
        "community lyrics",
        {
            "lyrics": {
                "text": "",
                "synced": [],
                "source": "LRCLIB community lyrics",
                "instrumental": False,
                "status": "not_found",
                "error": "",
            }
        },
    )

    assert widget._active_lyrics_source == "local"
    assert widget._current_lyrics["source"] == "Example Song.txt"
    assert "My local lyric" in widget.lyrics.toPlainText()
    assert widget.online_lyrics_button.text() == "Try again"

    window.close()
    app.processEvents()



def test_artwork_batch_can_pause_resume_cancel_and_retry_failed():
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
            f"/albums/control-{index:02d}.mp3",
            f"Artist {index:02d}",
            f"Album {index:02d}",
            f"Track {index:02d}",
            1,
            2000 + index,
        )
        for index in range(10)
    ]
    browser.set_catalog(tracks)
    browser.set_view("albums")

    batches = []
    browser.onlineArtworkRequested.connect(
        lambda rows: batches.append([dict(row) for row in rows])
    )
    browser._request_online_artwork()
    assert len(batches) == 1
    assert len(browser._album_lookup_inflight_rows) == 4

    browser._toggle_artwork_lookup_pause()
    assert browser._album_lookup_paused is True
    assert browser.artwork_pause_button.text() == "Resume"

    first = list(browser._album_lookup_inflight_rows)
    browser.finish_album_artwork_lookup_batch([
        {"key": first[0]["key"], "status": "found"},
        {"key": first[1]["key"], "status": "error", "error": "temporary"},
        {"key": first[2]["key"], "status": "no_match"},
        {"key": first[3]["key"], "status": "found"},
    ])
    assert len(batches) == 1
    snapshot = browser.artwork_lookup_snapshot()
    assert snapshot["paused"] is True
    assert snapshot["completed"] == 4
    assert snapshot["found"] == 2
    assert snapshot["skipped"] == 1
    assert snapshot["failed"] == 1

    browser._toggle_artwork_lookup_pause()
    assert browser._album_lookup_paused is False
    assert len(batches) == 2

    # Cancel while the resumed batch is in flight. It should finish that
    # batch but not start another one.
    browser._cancel_artwork_lookup()
    assert browser._album_lookup_cancel_requested is True
    second = list(browser._album_lookup_inflight_rows)
    browser.finish_album_artwork_lookup_batch([
        {"key": row["key"], "status": "found"}
        for row in second
    ])
    assert browser._album_lookup_active is False
    assert len(batches) == 2
    assert browser._album_lookup_failures

    # Retry only the failed item from the first batch.
    browser._album_lookup_cancel_requested = False
    browser._retry_failed_artwork()
    assert browser._album_lookup_active is True
    assert len(browser._album_lookup_inflight_rows) == 1
    retry = list(browser._album_lookup_inflight_rows)
    browser.finish_album_artwork_lookup_batch([
        {"key": retry[0]["key"], "status": "found"}
    ])
    retry_snapshot = browser.artwork_lookup_snapshot()
    assert retry_snapshot["total"] == 1
    assert retry_snapshot["completed"] == 1
    assert retry_snapshot["found"] == 1
    assert retry_snapshot["failed"] == 0

    browser.deleteLater()
    app.processEvents()


def test_artwork_progress_panel_reports_found_no_match_and_failed_counts():
    try:
        from PySide6.QtWidgets import QApplication
        from melodex.library_browser import LibraryBrowser
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    browser = LibraryBrowser()
    browser._album_lookup_stats = {
        "total": 832,
        "completed": 147,
        "found": 101,
        "skipped": 40,
        "failed": 6,
    }
    browser._album_lookup_active = True
    browser._refresh_artwork_progress(kind="albums")

    assert browser.artwork_progress.maximum() == 832
    assert browser.artwork_progress.value() == 147
    assert browser.artwork_progress.format() == "147 / 832"
    assert "Found 101" in browser.artwork_progress_summary.text()
    assert "No match 40" in browser.artwork_progress_summary.text()
    assert "Failed 6" in browser.artwork_progress_summary.text()
    assert "background" in browser.artwork_progress_detail.text().casefold()

    browser.deleteLater()
    app.processEvents()



def test_sources_first_run_orientation_is_dismissible_and_persistent(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication, QLabel
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    first = main_window.MainWindow()
    first.show()
    first.open_page("sources")
    app.processEvents()

    assert first.sources_feature.source_welcome.isVisible()
    title = first.sources_feature.source_welcome.findChild(QLabel, "sourceFirstRunTitle")
    assert title is not None
    assert "nothing else is required" in title.text().casefold()

    first.sources_feature.dismiss_intro()
    app.processEvents()
    assert first.sources_feature.source_welcome.isHidden()
    assert first.state.get_bool("sources_intro_seen", False) is True
    first.close()
    app.processEvents()

    second = main_window.MainWindow()
    second.show()
    second.open_page("sources")
    app.processEvents()
    assert second.sources_feature.source_welcome.isHidden()
    second.close()
    app.processEvents()



def test_native_lyrics_toolbar_hides_plugin_management_chrome(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("now_playing")
    widget = window.playback_feature.rich_now

    assert not hasattr(widget, "lyrics_plugin_presence")
    assert widget.online_lyrics_button.text() == "Refresh lyrics"
    assert widget.fullscreen_lyrics_button.text() == "Full screen"
    assert widget.translate_lyrics_button.text() == "Translate"
    assert widget.more_lyrics_button.text() == "More"
    assert widget.find_lyrics_plugin_button.isHidden()
    assert widget.import_lyrics_button.isHidden()
    assert widget.paste_lyrics_button.isHidden()
    assert widget.auto_online_lyrics.isHidden()

    menu_labels = [
        action.text()
        for action in widget.lyrics_more_menu.actions()
        if action.text()
    ]
    assert menu_labels == [
        "Edit saved lyrics…",
        "Add lyrics file…",
        "Paste lyrics…",
        "Auto-find online",
        "Manage lyric sources…",
    ]

    window.close()
    app.processEvents()


def test_refresh_lyrics_checks_native_and_installed_sources_before_online(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
        from melodex.metadata import track_key
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("now_playing")
    widget = window.playback_feature.rich_now
    widget.track = {
        "artist": "Example Artist",
        "title": "Example Song",
        "provider_id": "local",
        "track_id": "example-song",
    }

    payload = {
        "track_key": track_key(widget.track),
        "track": dict(widget.track),
        "identity": {
            "artist": "Example Artist",
            "title": "Example Song",
        },
        "lyrics": {
            "text": "Lyrics supplied by an installed source",
            "synced": [],
            "source": "Public Domain Lyrics Example",
            "provenance": {
                "source_extension_id": "org.example.lyrics",
                "source_extension_name": "Public Domain Lyrics Example",
            },
        },
        "errors": [],
    }
    monkeypatch.setattr(widget.metadata, "enrich_identity", lambda track: payload)

    online_calls = []
    monkeypatch.setattr(
        widget,
        "_find_lyrics_online",
        lambda force=True: online_calls.append(force),
    )

    def run_immediately(key, name, fn):
        widget._pending.add(name)
        widget._stage_loaded(key, name, fn())

    monkeypatch.setattr(widget, "_run_stage", run_immediately)
    widget._refresh_lyrics_native()
    app.processEvents()

    assert online_calls == []
    assert widget._current_lyrics["source"] == "Public Domain Lyrics Example"
    assert "Lyrics supplied by an installed source" in widget.lyrics.toPlainText()
    assert widget.lyrics_source_picker.count() == 1
    assert widget.lyrics_source_picker.currentText() == "Public Domain Lyrics Example"
    assert widget.online_lyrics_button.text() == "Refresh lyrics"

    window.close()
    app.processEvents()


def test_plain_lyrics_html_uses_explicit_dark_theme_contrast():
    try:
        from melodex.rich_now_playing import RichNowPlayingWidget
    except ImportError as exc:
        import pytest
        pytest.skip(f"Desktop runtime is unavailable: {exc}")

    rendered = RichNowPlayingWidget._plain_lyrics_html("Line one\nLine two")
    assert "color:#edf3fa" in rendered
    assert "font-size:24px" in rendered
    assert "Line one<br>Line two" in rendered



def test_search_keeps_previous_results_visible_while_refreshing(monkeypatch, tmp_path):
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QListWidgetItem
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.search_source.clear()
    window.search_source.addItem("All sources", "all")
    window.search_box.setText("new query")

    old_track = {
        "provider_id": "local",
        "track_id": "old",
        "artist": "Previous Artist",
        "title": "Previous Result",
    }
    old_item = QListWidgetItem("Previous Artist — Previous Result")
    old_item.setData(Qt.UserRole, old_track)
    window.results.addItem(old_item)

    callbacks = {}

    def hold_async(fn, done, on_error=None, **_kwargs):
        callbacks["done"] = done
        callbacks["error"] = on_error

    monkeypatch.setattr(window, "_run_async", hold_async)

    window._search()

    assert window.results.count() == 1
    assert window.results.item(0).data(Qt.UserRole) == old_track
    assert "showing previous results" in window.search_status.text()
    assert window.search_button.text() == "Searching…"

    # Even if the delayed-loading callback runs, useful stale content stays put.
    window._show_delayed_search_loading(
        window._search_sequence,
        "your connected sources",
    )
    assert window.results.count() == 1
    assert window.results.item(0).data(Qt.UserRole) == old_track

    callbacks["done"](
        {
            "items": [
                {
                    "provider_id": "local",
                    "track_id": "fresh",
                    "artist": "Fresh Artist",
                    "title": "Fresh Result",
                }
            ],
            "failures": [],
            "searched": 1,
            "available": 1,
        }
    )

    assert window.results.count() == 1
    assert window.results.item(0).data(Qt.UserRole)["track_id"] == "fresh"
    assert window.search_button.text() == "Search"

    window.close()
    app.processEvents()


def test_fast_search_never_flashes_delayed_loading_placeholder(monkeypatch, tmp_path):
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.search_source.clear()
    window.search_source.addItem("All sources", "all")
    window.search_box.setText("fast query")
    callbacks = {}

    def hold_async(fn, done, on_error=None, **_kwargs):
        callbacks["done"] = done

    monkeypatch.setattr(window, "_run_async", hold_async)
    window._search()
    sequence = window._search_sequence

    # Before 220 ms there is no generic loading row.
    assert window.results.count() == 0

    callbacks["done"](
        {
            "items": [
                {
                    "provider_id": "local",
                    "track_id": "fast",
                    "artist": "Fast Artist",
                    "title": "Fast Result",
                }
            ],
            "failures": [],
            "searched": 1,
            "available": 1,
        }
    )

    # A timer firing after completion must be a no-op.
    window._show_delayed_search_loading(sequence, "your connected sources")
    assert window.results.count() == 1
    assert window.results.item(0).text().startswith("Fast Artist — Fast Result")
    assert window.results.item(0).data(Qt.UserRole)["track_id"] == "fast"

    window.close()
    app.processEvents()


def test_search_failure_preserves_stale_useful_results(monkeypatch, tmp_path):
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QListWidgetItem
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.search_source.clear()
    window.search_source.addItem("All sources", "all")
    window.search_box.setText("offline query")

    old_track = {
        "provider_id": "local",
        "track_id": "cached",
        "artist": "Cached Artist",
        "title": "Cached Result",
    }
    item = QListWidgetItem("Cached Artist — Cached Result")
    item.setData(Qt.UserRole, old_track)
    window.results.addItem(item)

    callbacks = {}

    def hold_async(fn, done, on_error=None, **_kwargs):
        callbacks["error"] = on_error

    monkeypatch.setattr(window, "_run_async", hold_async)
    window._search()
    callbacks["error"]("synthetic provider outage")

    assert window.results.count() == 1
    assert window.results.item(0).data(Qt.UserRole) == old_track
    assert "showing previous results" in window.search_status.text()
    assert window.search_status.toolTip() == "synthetic provider outage"

    window.close()
    app.processEvents()


def test_stale_search_response_cannot_replace_newer_request(monkeypatch, tmp_path):
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.search_source.clear()
    window.search_source.addItem("All sources", "all")
    calls = []

    def hold_async(fn, done, on_error=None, **_kwargs):
        calls.append((done, on_error))

    monkeypatch.setattr(window, "_run_async", hold_async)

    window.search_box.setText("first")
    window._search()
    window.search_box.setText("second")
    window._search()

    calls[0][0](
        {
            "items": [
                {
                    "provider_id": "local",
                    "track_id": "stale",
                    "artist": "Old",
                    "title": "Stale",
                }
            ],
            "failures": [],
            "searched": 1,
            "available": 1,
        }
    )
    assert window.results.count() == 0

    calls[1][0](
        {
            "items": [
                {
                    "provider_id": "local",
                    "track_id": "current",
                    "artist": "New",
                    "title": "Current",
                }
            ],
            "failures": [],
            "searched": 1,
            "available": 1,
        }
    )
    assert window.results.count() == 1
    assert window.results.item(0).data(Qt.UserRole)["track_id"] == "current"

    window.close()
    app.processEvents()


def test_run_async_replace_key_drops_stale_completion(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.background_scheduler.shutdown(wait=True)

    class HeldScheduler:
        def __init__(self):
            self.jobs = []
            self.cancelled = []

        def submit(self, callback, **kwargs):
            self.jobs.append((callback, dict(kwargs)))
            return True

        def cancel_pending(self, replace_key):
            self.cancelled.append(str(replace_key))
            return 0

        def snapshot(self):
            return {}

        def shutdown(self, *, wait=False):
            return None

    scheduler = HeldScheduler()
    window.background_scheduler = scheduler
    applied = []

    window._run_async(
        lambda: "old",
        lambda result: applied.append(("old", result)),
        priority="visible",
        task_name="old-search",
        replace_key="search",
    )
    window._run_async(
        lambda: "new",
        lambda result: applied.append(("new", result)),
        priority="visible",
        task_name="new-search",
        replace_key="search",
    )

    assert [job[1]["replace_key"] for job in scheduler.jobs] == ["search", "search"]

    scheduler.jobs[0][0]()
    app.processEvents()
    assert applied == []
    assert window._async_stale_results_dropped == 1

    scheduler.jobs[1][0]()
    app.processEvents()
    assert applied == [("new", "new")]

    window.close()
    app.processEvents()


def test_navigation_invalidates_hidden_page_build(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    cancelled = []
    monkeypatch.setattr(
        window.background_scheduler,
        "cancel_pending",
        lambda key: cancelled.append(str(key)) or 1,
    )

    window.current_page = "album_wall"
    window.open_page("home")

    assert "page:album-wall-model" in cancelled
    assert window._async_invalidations >= 1

    window.close()
    app.processEvents()


def test_navigation_motion_happens_after_immediate_shell_change(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.open_page("library")

    # Navigation state is already complete; motion is only a short confirmation.
    assert window.current_page == "library"
    assert window.stack.currentWidget() is window.pages["library"]
    assert bool(window.nav_buttons["library"].property("active"))

    title = window.page_titles["library"]
    animation = window.motion.active_animation(title)
    assert animation is not None
    assert animation.duration() == main_window.FAST_MOTION_MS
    effect = title.graphicsEffect()
    assert isinstance(effect, QGraphicsOpacityEffect)
    assert effect.opacity() >= 0.75

    window.close()
    app.processEvents()


def test_navigation_shell_changes_before_slow_page_population(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    refresh_started = []

    def slow_library_refresh():
        refresh_started.append(time.monotonic())
        time.sleep(0.12)

    monkeypatch.setattr(window, "_refresh_library", slow_library_refresh)

    started_at = time.monotonic()
    window.open_page("library")
    shell_seconds = time.monotonic() - started_at

    # The click is complete once the destination shell is selected. Data
    # population must not be part of that foreground interaction.
    assert shell_seconds < 0.10
    assert window.current_page == "library"
    assert window.stack.currentWidget() is window.pages["library"]
    assert bool(window.nav_buttons["library"].property("active"))
    assert refresh_started == []

    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline and not refresh_started:
        app.processEvents()
        time.sleep(0.005)

    assert refresh_started
    window.close()
    app.processEvents()


def test_rapid_navigation_drops_stale_page_population(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    populated = []
    monkeypatch.setattr(
        window,
        "_refresh_library",
        lambda: populated.append("library"),
    )
    monkeypatch.setattr(
        window,
        "_refresh_playlists",
        lambda: populated.append("playlists"),
    )

    window.open_page("library")
    window.open_page("playlists")

    # Both shells were requested before deferred population started. Only the
    # page the user actually ended on should consume refresh work.
    assert window.current_page == "playlists"
    assert window.stack.currentWidget() is window.pages["playlists"]
    assert populated == []

    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline and "playlists" not in populated:
        app.processEvents()
        time.sleep(0.005)

    assert populated == ["playlists"]
    window.close()
    app.processEvents()


def test_slow_source_config_check_keeps_qt_event_loop_responsive(monkeypatch, tmp_path):
    try:
        from types import SimpleNamespace
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    plugin_id = "org.example.slow-config"
    window.providers.providers[plugin_id] = SimpleNamespace(
        info=SimpleNamespace(
            id=plugin_id,
            name="Slow Config Source",
            version="0.1.0",
            description="Synthetic source used by the responsiveness test.",
            capabilities=["search"],
            configuration=[
                {
                    "key": "api_token",
                    "label": "API token",
                    "type": "secret",
                    "required": True,
                }
            ],
            permissions={},
        )
    )
    monkeypatch.setattr(
        window.providers,
        "provider_order",
        lambda: ["local", plugin_id],
    )

    started = threading.Event()
    release = threading.Event()
    worker_threads = []

    def slow_status(requested_id, declarations):
        if requested_id == plugin_id:
            worker_threads.append(
                threading.current_thread() is threading.main_thread()
            )
            started.set()
            release.wait(timeout=2.0)
        return {
            "declared": bool(declarations),
            "configured": {"api_token": True},
            "ready": True,
            "pending": False,
            "pending_required": [],
            "missing_required": [],
            "secret_storage": "test",
        }

    monkeypatch.setattr(window.providers.plugin_config, "status", slow_status)

    timer_fired = []
    QTimer.singleShot(0, lambda: timer_fired.append(True))

    started_at = time.monotonic()
    window.open_page("sources")
    foreground_seconds = time.monotonic() - started_at

    # Opening Sources must not wait for the synthetic Keychain read.
    assert foreground_seconds < 0.25

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and (
        not started.is_set() or not timer_fired
    ):
        app.processEvents()
        time.sleep(0.005)

    assert started.is_set()
    assert timer_fired == [True]
    assert worker_threads == [False]
    assert window.sources_feature.config_refresh_in_progress is True

    release.set()
    deadline = time.monotonic() + 2.0
    while (
        time.monotonic() < deadline
        and window.sources_feature.config_refresh_in_progress
    ):
        app.processEvents()
        time.sleep(0.005)

    assert window.sources_feature.config_refresh_in_progress is False
    window.close()
    app.processEvents()


def test_love_and_keep_acknowledge_before_persistence(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    track = _track(
        str(tmp_path / "track.mp3"),
        "Artist",
        "Album",
        "Track",
        1,
    )
    window.playback_feature._playback_state.start_track(
        track, history_id=1, started_at=1.0
    )
    pending = []

    def hold_async(fn, done, on_error=None, **_kwargs):
        pending.append((fn, done, on_error))

    monkeypatch.setattr(window, "_run_async", hold_async)

    window.playback_feature.record_feedback(True)

    # The visual action completes before persistence is even allowed to run.
    assert window.playback_feature.love_button.text() == "♥ Loved"
    assert window.playback_feature.love_button.isEnabled() is False
    assert len(pending) == 1
    assert window.state.track_signal(track).get("loves", 0) == 0

    result = pending.pop(0)[0]()
    assert result is True
    assert window.state.track_signal(track)["loves"] == 1

    window.playback_feature._set_taste_action_state(loved=False, kept=False)
    window.playback_feature.keep_current()

    assert window.playback_feature.keep_button.text() == "✓ Kept"
    assert window.playback_feature.keep_button.isEnabled() is False
    assert len(pending) == 1
    assert window.state.track_signal(track).get("keeps", 0) == 0

    result = pending.pop(0)[0]()
    assert result is True
    assert window.state.track_signal(track)["keeps"] == 1

    window.close()
    app.processEvents()


def test_optimistic_taste_action_rolls_back_if_persistence_fails(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.playback_feature._playback_state.start_track(
        _track(
            str(tmp_path / "track.mp3"),
            "Artist",
            "Album",
            "Track",
            1,
        ),
        history_id=1,
        started_at=1.0,
    )
    pending = []

    def hold_async(fn, done, on_error=None, **_kwargs):
        pending.append((fn, done, on_error))

    monkeypatch.setattr(window, "_run_async", hold_async)

    window.playback_feature.record_feedback(True)
    assert window.playback_feature.love_button.text() == "♥ Loved"
    assert window.playback_feature.love_button.isEnabled() is False

    error = pending[0][2]
    assert error is not None
    error("synthetic database failure")

    assert window.playback_feature.love_button.text() == "♥"
    assert window.playback_feature.love_button.isEnabled() is True
    assert "Could not save preference" in window.statusBar().currentMessage()

    window.close()
    app.processEvents()


def test_next_track_prefetch_is_local_only_and_consumed_on_advance(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.navigation.ensure_lazy_page_built("now_playing")
    current = _track(
        str(tmp_path / "current.mp3"),
        "Artist",
        "Album",
        "Current",
        1,
    )
    upcoming = _track(
        str(tmp_path / "next.mp3"),
        "Artist",
        "Album",
        "Next",
        2,
    )
    window.player.queue = [dict(current), dict(upcoming)]
    window.player.index = 0
    window.playback_feature.on_queue_changed(window.player.queue, window.player.index)

    artwork_calls = []
    cached_analysis = object()

    def local_artwork(track):
        artwork_calls.append(str(track.get("title") or ""))
        return {"path": str(tmp_path / "next-cover.jpg"), "source": "cache"}

    monkeypatch.setattr(window.metadata, "local_artwork", local_artwork)
    monkeypatch.setattr(
        window.flow,
        "cached_analysis_for",
        lambda _path: cached_analysis,
    )

    def immediate_async(fn, done, on_error=None, **_kwargs):
        try:
            done(fn())
        except Exception as exc:
            if on_error is not None:
                on_error(str(exc))
            else:
                raise

    monkeypatch.setattr(window, "_run_async", immediate_async)

    window.playback_feature._prefetch_sequence = 1
    window.playback_feature._prefetch_next_track_assets(1)

    token = main_window.UserState.track_key(upcoming)
    assert artwork_calls == ["Next"]
    assert token in window.playback_feature._prefetched_track_assets
    assert window.playback_feature._prefetched_track_assets[token]["analysis"] is cached_analysis

    cover_calls = []
    analysis_calls = []
    monkeypatch.setattr(
        window.playback_feature.player_cover,
        "set_cover",
        lambda path, **kwargs: cover_calls.append(path),
    )
    monkeypatch.setattr(
        window.playback_feature.living_canvas,
        "set_track",
        lambda track, analysis: analysis_calls.append(analysis),
    )
    monkeypatch.setattr(window.playback_feature.living_canvas, "refresh_context", lambda: None)
    monkeypatch.setattr(window.playback_feature.rich_now, "set_track", lambda _track: None)
    monkeypatch.setattr(window, "_refresh_home_continue", lambda: None)

    # If prefetch worked, advancing must not call local_artwork a second time.
    window.player.index = 1
    window.playback_feature._playback_state.clear_current_track()
    window.playback_feature.on_track_changed(dict(upcoming))

    assert artwork_calls == ["Next"]
    assert cover_calls[-1] == str(tmp_path / "next-cover.jpg")
    assert analysis_calls[-1] is cached_analysis
    assert token not in window.playback_feature._prefetched_track_assets

    window.close()
    app.processEvents()


def test_next_track_prefetch_yields_to_large_library_scan(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    window = main_window.MainWindow()
    window.player.queue = [
        _track(str(tmp_path / "a.mp3"), "A", "A", "A", 1),
        _track(str(tmp_path / "b.mp3"), "B", "B", "B", 1),
    ]
    window.player.index = 0
    window.playback_feature.on_queue_changed(window.player.queue, window.player.index)
    window.local_scan._runner = object()
    calls = []
    monkeypatch.setattr(
        window,
        "_run_async",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    window.playback_feature._prefetch_sequence = 3
    window.playback_feature._prefetch_next_track_assets(3)

    assert calls == []
    assert window.playback_feature._prefetched_track_assets == {}

    window.local_scan._runner = None
    window.close()
    app.processEvents()


def test_global_scan_activity_persists_across_navigation(monkeypatch, tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_local_bridge", lambda self: None)

    release = threading.Event()

    class HoldingRunner:
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
            self.on_progress(
                {
                    "phase": "discovering",
                    "audio_files_seen": 120,
                }
            )

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def cancel(self, **_kwargs):
            release.set()
            self.on_done({"tracks": [], "cancelled": True})

        def shutdown(self, **_kwargs):
            release.set()

    monkeypatch.setattr(library_scan_process, "LibraryScanProcess", HoldingRunner)

    window = main_window.MainWindow()
    window.show()
    root = tmp_path / "large-library"
    root.mkdir()
    window.providers.configure_local_roots([root])

    window._start_local_scan("test")
    app.processEvents()

    assert window.background_activity.isVisible()
    assert "120 found" in window.background_activity_label.text()
    assert "You can keep using Melodex" in window.background_activity_label.text()
    assert window.background_activity_progress.minimum() == 0
    assert window.background_activity_progress.maximum() == 0
    assert window.background_activity_pause.isEnabled()
    assert window.background_activity_cancel.isEnabled()

    # Progress follows the job rather than disappearing with My Music.
    window.open_page("playlists")
    app.processEvents()
    assert window.current_page == "playlists"
    assert window.background_activity.isVisible()
    assert "You can keep using Melodex" in window.background_activity_label.text()

    window._local_scan_progress(
        window.local_scan.sequence,
        {
            "phase": "metadata",
            "audio_files_seen": 120,
            "completed": 30,
            "total": 120,
            "unchanged": 20,
            "added": 10,
        }
    )
    app.processEvents()
    assert window.background_activity_progress.minimum() == 0
    assert window.background_activity_progress.maximum() == 120
    assert window.background_activity_progress.value() == 30
    assert "Reading tags" in window.background_activity_label.text()

    window._toggle_local_scan_pause()
    app.processEvents()
    assert window.background_activity_pause.text() == "Resume"
    assert "Paused" in window.background_activity_label.text()

    window._toggle_local_scan_pause()
    app.processEvents()
    assert window.background_activity_pause.text() == "Pause"

    window._cancel_local_scan()
    app.processEvents()
    assert release.is_set()
    assert window.local_scan.active is False
    assert window.background_activity.isHidden()

    window.close()
    app.processEvents()


def test_slow_library_scan_keeps_qt_event_loop_responsive(monkeypatch, tmp_path):
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        import melodex.main_window as main_window
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
