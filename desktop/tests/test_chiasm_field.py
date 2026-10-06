from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ChiasmFieldTests(unittest.TestCase):
    def test_local_trace_coalesces_album_activity_and_keeps_a_bounded_route(self):
        from melodex.user_state import UserState

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "taste.sqlite3"
            state = UserState(state_path)
            state.record_chiasm_trace(
                "album-a", title="First", artist="Artist", activity="explore", limit=3
            )
            state.record_chiasm_trace(
                "album-a", title="First", artist="Artist", activity="listen", limit=3
            )
            coalesced = state.recent_chiasm_trace(1)
            state.record_chiasm_trace(
                "album-b", title="Second", artist="Artist", activity="explore", limit=3
            )
            state.record_chiasm_trace(
                "album-a", title="First", artist="Artist", activity="explore", limit=3
            )
            state.record_chiasm_trace(
                "album-c", title="Third", artist="Artist", activity="listen", limit=3
            )
            state.record_chiasm_trace(
                "album-d", title="Fourth", artist="Artist", activity="explore", limit=3
            )
            state.close()

            reopened = UserState(state_path)
            trace = reopened.recent_chiasm_trace(10)
            reopened.close()

        self.assertEqual([item["album_id"] for item in trace], ["album-d", "album-c", "album-a"])
        self.assertEqual(coalesced[0]["activity"], "explore+listen")
        self.assertTrue(all("local_path" not in item and "rel" not in item for item in trace))

    def test_demo_field_has_fifty_stable_album_locations(self):
        from chiasm.field_model import DEMO_COLLECTION, make_demo_collection

        self.assertEqual(len(DEMO_COLLECTION), 50)
        self.assertEqual(len({album.id for album in DEMO_COLLECTION}), 50)
        self.assertEqual(make_demo_collection(), DEMO_COLLECTION)
        self.assertEqual(len({album.region for album in DEMO_COLLECTION}), 5)

    def test_album_lens_context_uses_only_shared_named_region(self):
        from chiasm.field_model import DEMO_COLLECTION, album_lens_context

        album = DEMO_COLLECTION[0]
        context = album_lens_context(DEMO_COLLECTION, album)
        regional_titles = tuple(
            candidate.title
            for candidate in DEMO_COLLECTION
            if candidate.region == album.region and candidate.id != album.id
        )

        self.assertEqual(context.albums_in_region, 10)
        self.assertEqual(context.other_titles, regional_titles[:3])
        self.assertNotIn(album.title, context.other_titles)

    def test_collection_rows_adapt_to_stable_field_albums(self):
        from chiasm.field_model import albums_from_collection_rows

        rows = [
            {
                "key": "album-a",
                "title": "First",
                "artist": "Artist",
                "genres": ["Shoegaze", "Dream pop", "Shoegaze"],
                "fallback_x": 0.2,
            },
            {"key": "album-b", "title": "Second", "artist": "Artist"},
            {"title": "Missing stable key", "artist": "Ignored"},
        ]
        positions = {"album-a": (120.0, -40.0), "album-b": (-80.0, 60.0)}

        albums = albums_from_collection_rows(rows, positions)

        self.assertEqual([album.id for album in albums], ["album-a", "album-b"])
        self.assertEqual((albums[0].x, albums[0].y), (120.0, -40.0))
        self.assertEqual((albums[1].x, albums[1].y), (-80.0, 60.0))
        self.assertEqual(albums[0].region, "")
        self.assertEqual(albums[0].genres, ("Shoegaze", "Dream pop"))
        self.assertEqual(albums[0].analysed_tracks, 0)
        self.assertEqual(albums_from_collection_rows(rows, positions), albums)

        from chiasm.field_model import album_lens_context

        self.assertEqual(album_lens_context(albums, albums[0]).albums_in_region, 0)

    def test_collection_rows_keep_only_explicit_regions_and_adapt_sound_evidence(self):
        from chiasm.field_model import SoundLink, albums_from_collection_rows

        rows = [
            {
                "key": "first",
                "title": "First",
                "artist": "Artist A",
                "region": "Northern Shelf",
                "analysed_tracks": 4,
            },
            {"key": "second", "title": "Second", "artist": "Artist B"},
        ]
        links = {"first": (SoundLink("second", 0.82, 3),)}

        albums = albums_from_collection_rows(
            rows,
            {"first": (0.0, 0.0), "second": (9000.0, 9000.0)},
            links,
            {"first": 2, "second": 1},
        )

        self.assertEqual(albums[0].region, "Northern Shelf")
        self.assertEqual(albums[0].analysed_tracks, 4)
        self.assertEqual(albums[0].sound_sampled_tracks, 2)
        self.assertEqual(albums[0].sound_links, links["first"])
        self.assertEqual(albums[1].region, "")
        self.assertEqual(albums[1].analysed_tracks, 0)
        self.assertEqual(albums[1].sound_sampled_tracks, 1)

    def test_melodex_adapter_builds_local_collection_and_degrades_without_analysis(self):
        from chiasm.melodex_adapter import MelodexCollectionAdapter

        catalog = [
            {
                "track_id": "one",
                "local_path": "/music/Artist/Record/01.flac",
                "artist": "Artist",
                "album_artist": "Artist",
                "album": "Record",
                "title": "First",
                "track_number": 1,
                "genre": "Ambient",
            },
            {
                "track_id": "two",
                "local_path": "/music/Artist/Record/02.flac",
                "artist": "Artist",
                "album_artist": "Artist",
                "album": "Record",
                "title": "Second",
                "track_number": 2,
                "genre": "Ambient",
            },
        ]

        class Providers:
            def local_catalog(self):
                return catalog

        class UnavailableIntelligence:
            def build_snapshot(self, *_args, **_kwargs):
                raise RuntimeError("analysis service unavailable")

        class NoAnalysis:
            def build_snapshot(self, *_args, **_kwargs):
                return [], [], {}, 0

        adapter = MelodexCollectionAdapter(
            Providers(),
            local_intelligence=UnavailableIntelligence,
            metadata=lambda: object(),
        )
        payload = adapter.build_collection()

        self.assertEqual(payload["status"], "metadata-only")
        self.assertEqual(len(payload["albums"]), 1)
        album = payload["albums"][0]
        self.assertEqual((album.title, album.artist, album.genres), ("Record", "Artist", ("Ambient",)))
        self.assertEqual(len(payload["tracks_by_album"][album.id]), 2)
        self.assertEqual(payload["track_to_album"][catalog[1]["local_path"]], album.id)

        no_analysis = MelodexCollectionAdapter(
            Providers(),
            local_intelligence=NoAnalysis,
            metadata=lambda: object(),
        ).build_collection()
        self.assertEqual(no_analysis["status"], "metadata-only")
        self.assertEqual(no_analysis["albums"], payload["albums"])

    def test_melodex_adapter_handles_provider_and_empty_catalog_unavailability(self):
        from chiasm.melodex_adapter import MelodexCollectionAdapter

        class BrokenProviders:
            def local_catalog(self):
                raise OSError("provider unavailable")

        class EmptyProviders:
            def local_catalog(self):
                return []

        make_adapter = lambda providers: MelodexCollectionAdapter(
            providers,
            local_intelligence=lambda: self.fail("must not load intelligence without a catalog"),
            metadata=lambda: object(),
        )
        unavailable = make_adapter(BrokenProviders()).build_collection()
        empty = make_adapter(EmptyProviders()).build_collection()

        self.assertEqual(unavailable["status"], "provider-unavailable")
        self.assertEqual(unavailable["albums"], ())
        self.assertEqual(empty["status"], "empty")
        self.assertEqual(empty["tracks_by_album"], {})

    def test_melodex_artwork_adapter_caps_local_cache_requests(self):
        from chiasm.melodex_adapter import MAX_ARTWORK_BATCH, MelodexCollectionAdapter

        calls: list[str] = []

        class Metadata:
            def local_artwork(self, track):
                calls.append(track["local_path"])
                return {"path": f"/cache/{track['track_id']}.jpg"}

            def artwork(self, *_args, **_kwargs):
                raise AssertionError("Chiasm artwork must not make online lookups")

        ids = [f"album-{index}" for index in range(MAX_ARTWORK_BATCH + 6)]
        tracks_by_album = {
            album_id: [{"track_id": album_id, "local_path": f"/music/{album_id}.flac"}]
            for album_id in ids
        }
        adapter = MelodexCollectionAdapter(
            object(),
            local_intelligence=lambda: object(),
            metadata=Metadata,
        )

        paths = adapter.local_artwork_paths(tracks_by_album, ids, max_items=100)

        self.assertEqual(len(paths), MAX_ARTWORK_BATCH)
        self.assertEqual(len(calls), MAX_ARTWORK_BATCH)
        self.assertEqual(paths[ids[0]], f"/cache/{ids[0]}.jpg")

    def test_melodex_adapter_keeps_large_catalog_field_within_album_cap(self):
        from chiasm.melodex_adapter import MAX_COLLECTION_ALBUMS, MelodexCollectionAdapter

        catalog = [
            {
                "track_id": f"track-{index}",
                "local_path": f"/music/Artist/Album {index}/track.flac",
                "artist": "Artist",
                "album_artist": "Artist",
                "album": f"Album {index}",
                "title": "Track",
            }
            for index in range(MAX_COLLECTION_ALBUMS + 105)
        ]

        class Providers:
            def local_catalog(self):
                return catalog

        class NoAnalysis:
            def build_snapshot(self, _catalog, _seeds, *, max_tracks, analyse_seeds):
                self.max_tracks = max_tracks
                self.analyse_seeds = analyse_seeds
                return [], [], {}, 0

        intelligence = NoAnalysis()
        adapter = MelodexCollectionAdapter(
            Providers(),
            local_intelligence=lambda: intelligence,
            metadata=lambda: object(),
        )
        payload = adapter.build_collection()

        self.assertEqual(len(payload["albums"]), MAX_COLLECTION_ALBUMS)
        self.assertEqual(len(payload["tracks_by_album"]), MAX_COLLECTION_ALBUMS)
        self.assertEqual(intelligence.max_tracks, 5000)
        self.assertFalse(intelligence.analyse_seeds)
        self.assertEqual(payload["albums"], adapter.build_collection()["albums"])

    def test_album_horizon_uses_named_evidence_and_keeps_unresolved_explicit(self):
        from chiasm.field_model import Album, SoundLink
        from chiasm.relationship_model import album_horizon

        focus = Album(
            "focus", "Focus", "Artist A", "", 0, 0, 0,
            ("Shoegaze",),
            analysed_tracks=4,
            sound_sampled_tracks=1,
            sound_links=(SoundLink("sound-only", 0.77, 2),),
        )
        same_artist = Album(
            "artist", "Far Artist", "Artist A", "", 9000, 9000, 1,
            sound_sampled_tracks=1,
        )
        same_genre = Album(
            "genre", "Near Genre", "Artist B", "", 1, 1, 2, ("Shoegaze",),
            sound_sampled_tracks=1,
        )
        sound_only = Album(
            "sound-only", "Sound", "Artist C", "", -1, -1, 3,
            sound_sampled_tracks=1,
        )
        unresolved = Album("unresolved", "Unresolved", "Artist D", "", 0, 0, 4, ("Jazz",))

        result = album_horizon(
            (focus, same_artist, same_genre, sound_only, unresolved),
            focus,
        )

        self.assertEqual(
            [link.album_id for link in result.links],
            ["artist", "genre", "sound-only"],
        )
        by_id = {link.album_id: link for link in result.links}
        self.assertEqual(by_id["artist"].reasons, ("same artist",))
        self.assertEqual(by_id["genre"].reasons, ("shared genre: Shoegaze",))
        self.assertEqual(by_id["sound-only"].kinds, ("sound",))
        self.assertIn("2 track edges", by_id["sound-only"].summary)
        self.assertEqual(result.linked_count, 3)
        self.assertEqual(result.unresolved_count, 1)
        self.assertEqual(result.unsampled_album_count, 1)

    def test_track_edges_aggregate_to_symmetric_album_links(self):
        from chiasm.relationship_model import album_sound_links_from_track_edges

        links = album_sound_links_from_track_edges(
            [
                {"a": "a1", "b": "b1", "similarity": 0.71},
                {"a": "a2", "b": "b2", "similarity": 0.84},
                {"a": "a1", "b": "a2", "similarity": 0.99},
                {"a": "unknown", "b": "b1", "similarity": 0.99},
                {"a": "a1", "b": "b1", "similarity": 1.5},
            ],
            {"a1": "album-a", "a2": "album-a", "b1": "album-b", "b2": "album-b"},
        )

        self.assertEqual(len(links["album-a"]), 1)
        self.assertEqual(len(links["album-b"]), 1)
        self.assertEqual(links["album-a"][0].album_id, "album-b")
        self.assertAlmostEqual(links["album-a"][0].similarity, 0.84)
        self.assertEqual(links["album-a"][0].track_links, 2)
        self.assertEqual(links["album-b"][0].album_id, "album-a")

    def test_arc_uses_explicit_artist_and_genre_links_not_field_distance(self):
        from chiasm.arc_model import build_arc_route
        from chiasm.field_model import Album

        albums = (
            Album("start", "First", "Artist A", "Artist A", 0, 0, 0, ("Shoegaze",)),
            Album(
                "same-artist",
                "Later",
                "Artist A",
                "Artist A",
                5000,
                5000,
                1,
                ("Shoegaze",),
            ),
            Album("same-genre", "Other", "Artist B", "Artist B", 1, 1, 2, ("Shoegaze",)),
            Album("unrelated", "Far", "Artist C", "Artist C", 0, 0, 3, ("Jazz",)),
        )

        route = build_arc_route(albums, "start", max_hops=2)

        self.assertEqual([hop.album_id for hop in route], ["same-artist", "same-genre"])
        self.assertEqual(route[0].reason, "same artist; shares Shoegaze")
        self.assertEqual(route[1].reason, "shares genre: Shoegaze")
        self.assertNotIn("unrelated", [hop.album_id for hop in route])

    def test_arc_falls_back_transparently_and_never_repeats(self):
        from chiasm.arc_model import build_arc_route
        from chiasm.field_model import Album

        isolated = Album("isolated", "Only", "Artist A", "Artist A", 0, 0, 0)
        unrelated = Album("unrelated", "Other", "Artist B", "Artist B", 0, 0, 1)
        albums = (isolated, unrelated)
        fallback = build_arc_route(albums, "isolated")
        self.assertEqual([hop.album_id for hop in fallback], ["unrelated"])
        self.assertEqual(
            fallback[0].reason,
            "next album in collection (alphabetical fallback)",
        )
        self.assertEqual(build_arc_route(albums, "missing"), ())

        linked = (
            Album("isolated", "Only", "Artist A", "Artist A", 0, 0, 0, ("Pop",)),
            Album("second", "Second", "Artist B", "Artist B", 0, 0, 1, ("Pop",)),
            Album("third", "Third", "Artist C", "Artist C", 0, 0, 2, ("Pop",)),
        )
        route = build_arc_route(linked, "isolated", max_hops=10)
        self.assertEqual([hop.album_id for hop in route], ["second", "third"])
        steered = build_arc_route(
            linked,
            "second",
            max_hops=10,
            exclude_ids=("isolated",),
        )
        self.assertEqual([hop.album_id for hop in steered], ["third"])

        large_collection = tuple(
            Album(
                f"album-{index:02d}",
                f"Title {index:02d}",
                f"Artist {index:02d}",
                f"Artist {index:02d}",
                float(index),
                0.0,
                index % 8,
                ("Ambient",),
            )
            for index in range(15)
        )
        bounded = build_arc_route(large_collection, "album-00")
        self.assertLessEqual(len(bounded) + 1, 12)

    def test_pointer_centered_zoom_keeps_the_world_anchor_in_place(self):
        from chiasm.field_model import FieldCamera

        camera = FieldCamera(center_x=140, center_y=-75, zoom=0.88)
        pointer = (930, 230)
        before = camera.screen_to_world(*pointer, 1280, 800)

        self.assertTrue(camera.zoom_at(1.7, *pointer, 1280, 800))
        after = camera.screen_to_world(*pointer, 1280, 800)

        for old, new in zip(before, after):
            self.assertAlmostEqual(old, new, places=9)

    def test_camera_zoom_clamps_and_pan_preserves_the_world_point_under_drag(self):
        from chiasm.field_model import FieldCamera

        camera = FieldCamera()
        self.assertTrue(camera.is_at_home)
        camera.zoom_at(100, 640, 400, 1280, 800)
        self.assertEqual(camera.zoom, camera.max_zoom)
        self.assertFalse(camera.is_at_home)
        camera.zoom_at(0.001, 640, 400, 1280, 800)
        self.assertEqual(camera.zoom, camera.min_zoom)

        pointer = (730, 360)
        before = camera.screen_to_world(*pointer, 1280, 800)
        camera.pan_screen(38, -21)
        self.assertAlmostEqual(camera.center_x, -38 / camera.zoom)
        self.assertAlmostEqual(camera.center_y, 21 / camera.zoom)
        after = camera.screen_to_world(pointer[0] + 38, pointer[1] - 21, 1280, 800)
        for old, new in zip(before, after):
            self.assertAlmostEqual(old, new, places=9)
        camera.home()
        self.assertTrue(camera.is_at_home)

    def test_focus_depth_cue_is_local_and_never_changes_album_coordinates(self):
        from chiasm.field_model import Album, album_depth_cue, album_hit_radius

        focus = Album("focus", "Focus", "Artist", "Region", 0, 0, 0)
        near = Album("near", "Near", "Artist", "Region", 120, 0, 1)
        far = Album("far", "Far", "Artist", "Region", 1600, 0, 2)
        positions = ((focus.x, focus.y), (near.x, near.y), (far.x, far.y))

        focused_cue = album_depth_cue(focus, focus, None)
        near_cue = album_depth_cue(near, focus, None)
        far_cue = album_depth_cue(far, focus, None)

        self.assertGreater(focused_cue.scale, near_cue.scale)
        self.assertGreater(near_cue.scale, far_cue.scale)
        self.assertGreater(focused_cue.opacity, near_cue.opacity)
        self.assertGreater(near_cue.opacity, far_cue.opacity)
        self.assertGreater(focused_cue.focus_strength, near_cue.focus_strength)
        self.assertGreater(near_cue.focus_strength, far_cue.focus_strength)
        self.assertGreaterEqual(album_hit_radius(near, focus, None, 0.36) * 0.36, 22)
        self.assertEqual(positions, ((focus.x, focus.y), (near.x, near.y), (far.x, far.y)))

    def test_semantic_zoom_resolves_regions_albums_and_detail_in_order(self):
        from chiasm.field_model import SemanticLevel, semantic_zoom_level

        self.assertIs(semantic_zoom_level(0.36), SemanticLevel.OVERVIEW)
        self.assertIs(semantic_zoom_level(0.88), SemanticLevel.ALBUMS)
        self.assertIs(semantic_zoom_level(1.2), SemanticLevel.DETAIL)

    def test_hit_targets_keep_a_44_pixel_diameter_at_supported_zooms(self):
        from chiasm.field_model import Album, album_hit_radius

        focus = Album("focus", "Focus", "Artist", "Region", 0, 0, 0)
        near = Album("near", "Near", "Artist", "Region", 120, 0, 1)
        far = Album("far", "Far", "Artist", "Region", 1600, 0, 2)
        cases = (
            (focus, focus, None),
            (near, focus, None),
            (far, focus, far.id),
            (far, None, far.id),
        )

        for zoom in (0.36, 0.55, 0.88, 1.2, 2.8):
            for album, selected, hovered_id in cases:
                with self.subTest(zoom=zoom, album=album.id, focus=selected is not None):
                    diameter = 2 * album_hit_radius(album, selected, hovered_id, zoom) * zoom
                    self.assertGreaterEqual(diameter, 44.0)

    def test_large_collection_field_interaction_ack_stays_inside_fluid_budget(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from math import ceil

            from PySide6.QtCore import QPoint, QPointF, Qt
            from PySide6.QtGui import QWheelEvent
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication

            from chiasm.field_model import Album
            from chiasm.field_view import FieldCanvas
            from melodex.responsiveness import UiResponsivenessMonitor
            from melodex.responsiveness_gate import evaluate_responsiveness_summary
        except ImportError as exc:
            self.skipTest(f"Qt desktop runtime is unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        albums = tuple(
            Album(
                f"album-{index}",
                f"Album {index}",
                "Artist",
                "",
                index * 1000.0,
                0.0,
                index % 8,
            )
            for index in range(1200)
        )
        field = FieldCanvas(albums)
        field.resize(1280, 720)
        field.show()
        field.setFocus()
        app.processEvents()

        monitor = UiResponsivenessMonitor()
        field.interactionMeasured.connect(monitor.record_interaction)
        target = field.screen_point_for(albums[0]).toPoint()
        for _ in range(24):
            QTest.mouseClick(field, Qt.LeftButton, pos=target)
            QTest.keyClick(field, Qt.Key_Right)
            app.processEvents()

        drag_start = QPoint(field.width() // 2, field.height() // 2)
        drag_end = drag_start + QPoint(60, 40)
        QTest.mousePress(field, Qt.LeftButton, pos=drag_start)
        threshold = QApplication.startDragDistance()
        QTest.mouseMove(field, drag_start + QPoint(max(1, threshold // 3), 0), delay=10)
        QTest.mouseMove(field, drag_start + QPoint(max(2, threshold * 2 // 3), 0), delay=10)
        QTest.mouseMove(field, drag_end, delay=10)
        QTest.mouseRelease(field, Qt.LeftButton, pos=drag_end)

        wheel_position = QPointF(field.width() * 0.7, field.height() * 0.45)
        wheel_event = QWheelEvent(
            wheel_position,
            QPointF(field.mapToGlobal(wheel_position.toPoint())),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(field, wheel_event)
        app.processEvents()

        interactions = monitor.summary()["recent_interactions"]
        durations = sorted(float(item["duration_ms"]) for item in interactions)
        labels = {str(item["label"]) for item in interactions}
        self.assertGreaterEqual(len(durations), 48)
        self.assertIn("chiasm:key", labels)
        self.assertIn("chiasm:drag", labels)
        self.assertIn("chiasm:wheel", labels)
        self.assertTrue(
            labels
            <= {
                "chiasm:pointer-press",
                "chiasm:pointer-release",
                "chiasm:pointer-double-click",
                "chiasm:drag",
                "chiasm:wheel",
                "chiasm:key",
            }
        )
        p95 = durations[ceil(0.95 * len(durations)) - 1]
        result = evaluate_responsiveness_summary(
            {
                "interaction_count": len(durations),
                "interaction_p95_ms": p95,
                "recent_interactions": interactions,
            },
            require_interactions=True,
            require_interaction_prefixes=("chiasm:",),
        )
        self.assertTrue(result["passed"], result["errors"])

        field.deleteLater()
        monitor.deleteLater()
        app.processEvents()

    def test_field_renders_and_direct_manipulation_works_without_player_services(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import QEvent, QPoint, QPointF, QPropertyAnimation, Qt
            from PySide6.QtGui import QImage, QMouseEvent, QWheelEvent
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication

            from chiasm.field_view import FieldCanvas
        except ImportError as exc:
            self.skipTest(f"Qt desktop runtime is unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        field = FieldCanvas()
        field.resize(1280, 820)
        self.assertEqual(field.accessibleName(), "Chiasm spatial music field")
        self.assertIn("No album is focused.", field.accessibleDescription())
        self.assertIn("H or Home returns to the starting view", field.accessibleDescription())
        self.assertNotIn("Home choose Trace", field.accessibleDescription())
        self.assertEqual(field.findChildren(QPropertyAnimation), [])
        field.show()
        app.processEvents()

        image = QImage(field.size(), QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        field.render(image)
        opaque_pixels = sum(
            image.pixelColor(x, y).alpha() > 0
            for x in range(image.width())
            for y in range(image.height())
        )
        self.assertGreater(opaque_pixels, 100_000)
        self.assertTrue(field._visible_ids)

        field.setFocus()
        before_pan = (field.camera.center_x, field.camera.center_y)
        drag_start = QPoint(field.width() // 2, field.height() // 2)
        drag_end = drag_start + QPoint(60, 40)
        QTest.mousePress(field, Qt.LeftButton, pos=drag_start)
        threshold = QApplication.startDragDistance()
        QTest.mouseMove(field, drag_start + QPoint(max(1, threshold // 3), 0), delay=10)
        QTest.mouseMove(field, drag_start + QPoint(max(2, threshold * 2 // 3), 0), delay=10)
        QTest.mouseMove(field, drag_end, delay=10)
        QTest.mouseRelease(field, Qt.LeftButton, pos=drag_end)
        app.processEvents()
        self.assertAlmostEqual(field.camera.center_x, before_pan[0] - 60 / field.camera.zoom)
        self.assertAlmostEqual(field.camera.center_y, before_pan[1] - 40 / field.camera.zoom)

        QTest.keyClick(field, Qt.Key_Home)
        app.processEvents()
        self.assertEqual(field.camera.center_x, 0.0)
        self.assertEqual(field.camera.center_y, 0.0)
        self.assertEqual(field.camera.zoom, 0.88)

        QTest.keyClick(field, Qt.Key_Right)
        app.processEvents()
        self.assertNotEqual(field.camera.center_x, 0.0)
        QTest.keyClick(field, Qt.Key_Plus)
        app.processEvents()
        self.assertGreater(field.camera.zoom, 0.88)
        QTest.keyClick(field, Qt.Key_H)
        app.processEvents()
        self.assertTrue(field.camera.is_at_home)

        wheel_position = QPointF(field.width() / 2, field.height() / 2)
        wheel_event = QWheelEvent(
            wheel_position,
            QPointF(field.mapToGlobal(wheel_position.toPoint())),
            QPoint(0, 24),
            QPoint(0, 0),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(field, wheel_event)
        app.processEvents()
        self.assertNotEqual(field.camera.center_y, 0.0)
        self.assertEqual(field.camera.zoom, 0.88)
        self.assertFalse(field.camera.is_at_home)

        mouse_wheel_position = QPointF(field.width() * 0.7, field.height() * 0.45)
        world_anchor = field.camera.screen_to_world(
            mouse_wheel_position.x(),
            mouse_wheel_position.y(),
            field.width(),
            field.height(),
        )
        mouse_wheel_event = QWheelEvent(
            mouse_wheel_position,
            QPointF(field.mapToGlobal(mouse_wheel_position.toPoint())),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(field, mouse_wheel_event)
        app.processEvents()
        self.assertGreater(field.camera.zoom, 0.88)
        after_zoom_anchor = field.camera.screen_to_world(
            mouse_wheel_position.x(),
            mouse_wheel_position.y(),
            field.width(),
            field.height(),
        )
        for before, after in zip(world_anchor, after_zoom_anchor):
            self.assertAlmostEqual(before, after, places=8)

        home_button = field._home_cue_rect.center().toPoint()
        QTest.mouseClick(field, Qt.LeftButton, pos=home_button)
        app.processEvents()
        self.assertTrue(field.camera.is_at_home)

        album = None
        point = None
        for candidate in field.albums:
            candidate_point = field.screen_point_for(candidate)
            if 60 < candidate_point.x() < field.width() - 60 and 60 < candidate_point.y() < field.height() - 60:
                album = candidate
                point = candidate_point
                break
        self.assertIsNotNone(album)
        self.assertIsNotNone(point)
        assert album is not None and point is not None
        local_point = point
        global_point = QPointF(field.mapToGlobal(local_point.toPoint()))
        hover_move = QMouseEvent(
            QEvent.Type.MouseMove,
            local_point,
            local_point,
            global_point,
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(field, hover_move)
        app.processEvents()
        self.assertEqual(field.hovered_id, album.id)

        before_small_jitter = (field.camera.center_x, field.camera.center_y, field.camera.zoom)
        nearby_point = point.toPoint() + QPoint(1, 0)
        QTest.mousePress(field, Qt.LeftButton, pos=point.toPoint())
        QTest.mouseMove(field, nearby_point, delay=10)
        QTest.mouseRelease(field, Qt.LeftButton, pos=nearby_point)
        app.processEvents()
        self.assertEqual(
            (field.camera.center_x, field.camera.center_y, field.camera.zoom),
            before_small_jitter,
        )
        self.assertEqual(field.focused_id, album.id)
        self.assertIn(f"Focused album: {album.title}", field.accessibleDescription())

        camera_before_lens = (
            field.camera.center_x,
            field.camera.center_y,
            field.camera.zoom,
        )
        hover_before_lens = field.hovered_id
        positions_before_lens = tuple((item.x, item.y) for item in field.albums)
        QTest.keyClick(field, Qt.Key_Return)
        app.processEvents()
        self.assertTrue(field._lens_open)
        self.assertIn("Horizon lens is open", field.accessibleDescription())
        self.assertTrue(field._lens_rect.isValid())
        self.assertEqual(field.focused_id, album.id)
        self.assertEqual(
            (field.camera.center_x, field.camera.center_y, field.camera.zoom),
            camera_before_lens,
        )
        self.assertEqual(field.hovered_id, hover_before_lens)
        self.assertEqual(tuple((item.x, item.y) for item in field.albums), positions_before_lens)

        QTest.keyClick(field, Qt.Key_Escape)
        app.processEvents()
        self.assertFalse(field._lens_open)
        self.assertEqual(field.focused_id, album.id)
        self.assertEqual(
            (field.camera.center_x, field.camera.center_y, field.camera.zoom),
            camera_before_lens,
        )
        self.assertEqual(tuple((item.x, item.y) for item in field.albums), positions_before_lens)

        QTest.keyClick(field, Qt.Key_Return)
        app.processEvents()
        anchor_before_pan = (field._lens_anchor.x(), field._lens_anchor.y())
        QTest.keyClick(field, Qt.Key_Right)
        app.processEvents()
        self.assertTrue(field._lens_open)
        self.assertNotEqual(
            (field._lens_anchor.x(), field._lens_anchor.y()),
            anchor_before_pan,
        )
        camera_after_lens_pan = (
            field.camera.center_x,
            field.camera.center_y,
            field.camera.zoom,
        )
        QTest.keyClick(field, Qt.Key_Escape)
        app.processEvents()
        self.assertFalse(field._lens_open)
        self.assertEqual(field.focused_id, album.id)
        self.assertEqual(
            (field.camera.center_x, field.camera.center_y, field.camera.zoom),
            camera_after_lens_pan,
        )

        QTest.keyClick(field, Qt.Key_Return)
        app.processEvents()
        close_button = field._lens_close_rect.center().toPoint()
        QTest.mouseClick(field, Qt.LeftButton, pos=close_button)
        app.processEvents()
        self.assertFalse(field._lens_open)
        self.assertEqual(field.focused_id, album.id)
        self.assertEqual(
            (field.camera.center_x, field.camera.center_y, field.camera.zoom),
            camera_after_lens_pan,
        )

        played: list[str] = []
        field.mockPlayed.connect(played.append)
        point = field.screen_point_for(album)
        QTest.mouseDClick(field, Qt.LeftButton, pos=point.toPoint())
        app.processEvents()
        self.assertEqual(played, [album.id])
        self.assertTrue(field._play_toast.startswith("Mock play"))

        QTest.keyClick(field, Qt.Key_Escape)
        app.processEvents()
        self.assertIsNone(field.focused_id)

        field.deleteLater()
        app.processEvents()

    def test_live_playback_controls_request_host_actions_and_keep_place(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication

            from chiasm.field_model import Album
            from chiasm.field_view import FieldCanvas
        except ImportError as exc:
            self.skipTest(f"Qt desktop runtime is unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        album = Album("live-album", "Night Maps", "Aster", "", 0, 0, 3, ("Ambient",))
        field = FieldCanvas((album,), live_playback=True)
        field.resize(800, 600)
        field.show()
        app.processEvents()

        play_requests: list[str] = []
        pause_requests: list[bool] = []
        next_requests: list[bool] = []
        arc_requests: list[str] = []
        arc_steer_requests: list[str] = []
        arc_pause_requests: list[bool] = []
        arc_control_requests: list[bool] = []
        field.playRequested.connect(play_requests.append)
        field.playPauseRequested.connect(lambda: pause_requests.append(True))
        field.nextRequested.connect(lambda: next_requests.append(True))
        field.arcRequested.connect(arc_requests.append)
        field.arcSteerRequested.connect(arc_steer_requests.append)
        field.arcPauseRequested.connect(lambda: arc_pause_requests.append(True))
        field.arcTakeControlRequested.connect(lambda: arc_control_requests.append(True))

        album_point = field.screen_point_for(album).toPoint()
        QTest.mouseDClick(field, Qt.LeftButton, pos=album_point)
        app.processEvents()
        self.assertEqual(play_requests, [album.id])

        field.focus_album(album)
        field.open_lens()
        app.processEvents()
        lens_play = field._lens_play_rect.center().toPoint()
        QTest.mouseClick(field, Qt.LeftButton, pos=lens_play)
        app.processEvents()
        self.assertEqual(play_requests, [album.id, album.id])

        field.camera.center_x = 120.0
        field.camera.center_y = -40.0
        field.camera.zoom = 1.1
        camera_before_refresh = (
            field.camera.center_x,
            field.camera.center_y,
            field.camera.zoom,
        )
        field.set_playback_state(
            {"artist": "Aster", "title": "First Light", "local_path": "/music/first.flac"},
            playing=True,
            position_ms=12_000,
            duration_ms=210_000,
            album_id=album.id,
            can_next=True,
        )
        self.assertIn("First Light", field.accessibleDescription())
        self.assertIn("playback is playing", field.accessibleDescription())
        field.set_albums((album,))
        app.processEvents()
        self.assertEqual(field._current_track["title"], "First Light")
        self.assertTrue(field._playing)
        self.assertTrue(field._lens_open)
        self.assertEqual(field.focused_id, album.id)
        self.assertEqual(
            (field.camera.center_x, field.camera.center_y, field.camera.zoom),
            camera_before_refresh,
        )

        field.setFocus()
        QTest.keyClick(field, Qt.Key_Space)
        QTest.keyClick(field, Qt.Key_N)
        app.processEvents()
        self.assertEqual(pause_requests, [True])
        self.assertEqual(next_requests, [True])

        play_button = field._transport_play_rect.center().toPoint()
        next_button = field._transport_next_rect.center().toPoint()
        QTest.mouseClick(field, Qt.LeftButton, pos=play_button)
        QTest.mouseClick(field, Qt.LeftButton, pos=next_button)
        app.processEvents()
        self.assertEqual(pause_requests, [True, True])
        self.assertEqual(next_requests, [True, True])

        lens_arc = field._lens_arc_rect.center().toPoint()
        QTest.mouseClick(field, Qt.LeftButton, pos=lens_arc)
        app.processEvents()
        self.assertEqual(arc_requests, [album.id])

        next_album = Album(
            "next-album", "Second Light", "Boreal", "", 500, 0, 4, ("Ambient",)
        )
        field.set_albums((album, next_album))
        field.set_arc_state(
            active=True,
            next_album=next_album,
            reason="chosen by you",
        )
        app.processEvents()
        lens_arc = field._lens_arc_rect.center().toPoint()
        QTest.mouseClick(field, Qt.LeftButton, pos=lens_arc)
        app.processEvents()
        self.assertEqual(arc_steer_requests, [album.id])

        field.setFocus()
        QTest.keyClick(field, Qt.Key_A)
        QTest.keyClick(field, Qt.Key_T)
        app.processEvents()
        self.assertEqual(arc_steer_requests, [album.id, album.id])
        self.assertEqual(arc_control_requests, [True])

        toggle_arc = field._arc_toggle_rect.center().toPoint()
        take_control = field._arc_take_control_rect.center().toPoint()
        QTest.mouseClick(field, Qt.LeftButton, pos=toggle_arc)
        QTest.mouseClick(field, Qt.LeftButton, pos=take_control)
        app.processEvents()
        self.assertEqual(arc_pause_requests, [True])
        self.assertEqual(arc_control_requests, [True, True])

        self.assertTrue(field._lens_horizon_rects)
        horizon_row = field._lens_horizon_rects[0].center().toPoint()
        zoom_before_horizon = field.camera.zoom
        positions_before_horizon = tuple((item.x, item.y) for item in field.albums)
        QTest.mouseClick(field, Qt.LeftButton, pos=horizon_row)
        app.processEvents()
        self.assertEqual(field.focused_id, next_album.id)
        self.assertTrue(field._lens_open)
        self.assertEqual((field.camera.center_x, field.camera.center_y), (next_album.x, next_album.y))
        self.assertEqual(field.camera.zoom, zoom_before_horizon)
        self.assertEqual(
            tuple((item.x, item.y) for item in field.albums),
            positions_before_horizon,
        )
        QTest.keyClick(field, Qt.Key_1)
        app.processEvents()
        self.assertEqual(field.focused_id, album.id)
        self.assertEqual((field.camera.center_x, field.camera.center_y), (album.x, album.y))
        self.assertEqual(field.camera.zoom, zoom_before_horizon)
        self.assertEqual(
            tuple((item.x, item.y) for item in field.albums),
            positions_before_horizon,
        )

        field.deleteLater()
        app.processEvents()

    def test_trace_lens_revisits_an_album_and_requests_play_from_that_stop(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import QPoint, Qt
            from PySide6.QtGui import QImage
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication

            from chiasm.field_model import Album
            from chiasm.field_view import FieldCanvas
        except ImportError as exc:
            self.skipTest(f"Qt desktop runtime is unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        first = Album("first", "First Album", "Aster", "", -110, 0, 0)
        last = Album("last", "Last Album", "Vela", "", 140, 40, 1)
        field = FieldCanvas((first, last), live_playback=True)
        field.resize(900, 640)
        field.show()
        field.set_trace(
            [
                {
                    "album_id": last.id,
                    "title": last.title,
                    "artist": last.artist,
                    "activity": "listen",
                    "recorded_at": 1.0,
                    "playable": True,
                },
                {
                    "album_id": first.id,
                    "title": first.title,
                    "artist": first.artist,
                    "activity": "explore",
                    "recorded_at": 0.5,
                    "playable": True,
                },
                {
                    "album_id": last.id,
                    "title": last.title,
                    "artist": last.artist,
                    "activity": "explore",
                    "recorded_at": 0.2,
                    "playable": True,
                },
            ]
        )
        field.setFocus()
        QTest.keyClick(field, Qt.Key_BracketRight)
        self.assertEqual(field.focused_id, first.id)
        self.assertEqual((field.camera.center_x, field.camera.center_y), (first.x, first.y))
        self.assertIn("bracket keys focus", field.accessibleDescription())
        QTest.keyClick(field, Qt.Key_BracketRight)
        self.assertEqual(field.focused_id, last.id)
        self.assertEqual((field.camera.center_x, field.camera.center_y), (last.x, last.y))
        QTest.keyClick(field, Qt.Key_BracketLeft)
        self.assertEqual(field.focused_id, first.id)
        field.open_lens()
        zoom_before_focus_move = field.camera.zoom
        QTest.keyClick(field, Qt.Key_BracketRight)
        self.assertEqual(field.focused_id, last.id)
        self.assertTrue(field._lens_open)
        self.assertEqual(field.camera.zoom, zoom_before_focus_move)
        QTest.keyClick(field, Qt.Key_BracketLeft)
        self.assertEqual(field.focused_id, first.id)
        self.assertTrue(field._lens_open)
        QTest.keyClick(field, Qt.Key_Tab, Qt.ControlModifier)
        self.assertEqual(field._lens_panel, "trace")
        self.assertIn(
            "Ctrl+Tab switches between Horizon and Trace",
            field.accessibleDescription(),
        )
        QTest.keyClick(field, Qt.Key_Tab, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertEqual(field._lens_panel, "horizon")
        app.processEvents()

        def render_field():
            image = QImage(field.size(), QImage.Format_ARGB32)
            image.fill(Qt.transparent)
            field.render(image)
            app.processEvents()

        render_field()
        QTest.mouseClick(
            field,
            Qt.LeftButton,
            pos=field._lens_trace_tab_rect.center().toPoint(),
        )
        render_field()
        self.assertEqual(field._lens_panel, "trace")
        self.assertIn("Trace lens is open", field.accessibleDescription())
        self.assertIn("Trace stops shown: Last Album by Vela", field.accessibleDescription())
        self.assertIn("Earlier stops are available with PageUp", field.accessibleDescription())
        self.assertTrue(field._lens_trace_rects)
        QTest.keyClick(field, Qt.Key_PageUp)
        self.assertGreater(field._lens_trace_offset, 0)
        self.assertIn("Newer stops are available with PageDown", field.accessibleDescription())
        QTest.keyClick(field, Qt.Key_PageDown)
        self.assertEqual(field._lens_trace_offset, 0)
        self.assertIn("Earlier stops are available with PageUp", field.accessibleDescription())

        row_point = field._lens_trace_rects[0].topLeft().toPoint() + QPoint(12, 15)
        QTest.mouseClick(field, Qt.LeftButton, pos=row_point)
        app.processEvents()
        self.assertEqual(field.focused_id, last.id)
        self.assertEqual((field.camera.center_x, field.camera.center_y), (last.x, last.y))
        self.assertTrue(field._lens_open)

        play_requests: list[str] = []
        field.playRequested.connect(play_requests.append)
        QTest.keyClick(field, Qt.Key_Return, Qt.ControlModifier)
        self.assertEqual(play_requests, [last.id])
        render_field()
        QTest.mouseClick(
            field,
            Qt.LeftButton,
            pos=field._lens_trace_tab_rect.center().toPoint(),
        )
        render_field()
        QTest.mouseClick(
            field,
            Qt.LeftButton,
            pos=field._lens_trace_play_rects[0].center().toPoint(),
        )
        app.processEvents()
        self.assertEqual(play_requests, [last.id, last.id])

        field.deleteLater()
        app.processEvents()

    def test_accessible_description_notifies_qt_only_when_text_changes(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from types import SimpleNamespace
            from unittest.mock import Mock, patch

            from PySide6.QtGui import QAccessible
            from PySide6.QtWidgets import QApplication

            import chiasm.field_view as field_view
            from chiasm.field_model import Album
            from chiasm.field_view import FieldCanvas
        except ImportError as exc:
            self.skipTest(f"Qt desktop runtime is unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        album = Album("accessible", "Accessible Album", "Aster", "", 24, -12, 0)
        field = FieldCanvas((album,))
        notify_accessibility = Mock()
        accessible_api = SimpleNamespace(
            Event=QAccessible.Event,
            updateAccessibility=notify_accessibility,
        )

        with patch.object(field_view, "QAccessible", accessible_api):
            field._refresh_accessible_description()
            notify_accessibility.assert_not_called()

            field.focus_album(album)
            notify_accessibility.assert_called_once()
            event = notify_accessibility.call_args.args[0]
            self.assertEqual(event.type(), QAccessible.Event.DescriptionChanged)

            field.focus_album(album)
            notify_accessibility.assert_called_once()

        field.deleteLater()
        app.processEvents()

    def test_chiasm_interaction_measurements_reach_export_monitor(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from types import SimpleNamespace

            from PySide6.QtCore import QObject, Signal
            from PySide6.QtWidgets import QApplication

            from melodex.chiasm_feature import create_chiasm_feature
            from melodex.responsiveness import UiResponsivenessMonitor
        except ImportError as exc:
            self.skipTest(f"Qt desktop runtime is unavailable: {exc}")

        class FakePlaybackFeature(QObject):
            playPauseRequested = Signal()
            nextRequested = Signal()
            current_track = None

        class FakePlayer(QObject):
            trackChanged = Signal(object)
            playingChanged = Signal(bool)
            positionChanged = Signal(int, int)

            @staticmethod
            def status():
                return {"playing": False, "queue": [], "index": -1}

            @staticmethod
            def replace_queue_and_play(*_args):
                pass

            @staticmethod
            def replace_upcoming(*_args):
                pass

            @staticmethod
            def set_playing(*_args):
                pass

        class FakeHost(QObject):
            def __init__(self):
                super().__init__()
                self.providers = SimpleNamespace(local_catalog=lambda: [])
                self.state = SimpleNamespace(recent_chiasm_trace=lambda _limit: [])
                self.local_intelligence = None
                self.metadata = None
                self._run_async = lambda *_args, **_kwargs: None
                self.player = FakePlayer()
                self.playback_feature = FakePlaybackFeature()
                self.page_titles = {}
                self.responsiveness = UiResponsivenessMonitor()
                self.pages = {}
                self.stack = SimpleNamespace(addWidget=lambda _widget: None)
                self._status_bar = SimpleNamespace(showMessage=lambda *_args: None)

            def statusBar(self):
                return self._status_bar

        app = QApplication.instance() or QApplication([])
        host = FakeHost()
        feature = create_chiasm_feature(host)
        feature.build()
        feature.chiasm_canvas.interactionMeasured.emit("chiasm:key", 12.5)
        app.processEvents()

        interactions = host.responsiveness.summary()["recent_interactions"]
        self.assertEqual(interactions[-1]["label"], "chiasm:key")
        self.assertEqual(interactions[-1]["duration_ms"], 12.5)
        self.assertIn("chiasm", host.pages)

        host.responsiveness.stop()
        feature.deleteLater()
        host.deleteLater()
        app.processEvents()

    def test_artwork_batches_are_bounded_and_reject_stale_collection_results(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QImage
            from PySide6.QtWidgets import QApplication

            from chiasm.field_model import Album
            from chiasm.field_view import FieldCanvas
        except ImportError as exc:
            self.skipTest(f"Qt desktop runtime is unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        albums = tuple(
            Album(f"album-{index}", f"Album {index}", "Artist", "", index * 4, 0, index % 8)
            for index in range(40)
        )
        field = FieldCanvas(albums, live_playback=True)
        field.resize(1000, 700)
        field.show()
        app.processEvents()
        field.camera.zoom = 0.9
        field._visible_ids = tuple(album.id for album in albums)
        batches: list[dict] = []
        field.artworkRequested.connect(batches.append)

        field._request_visible_artwork()

        self.assertEqual(len(batches), 1)
        self.assertLessEqual(len(batches[0]["album_ids"]), field._artwork_batch_limit)
        first_id = batches[0]["album_ids"][0]
        field.set_artwork_batch(
            {
                "generation": batches[0]["generation"],
                "album_ids": batches[0]["album_ids"],
                "images": {first_id: QImage(8, 8, QImage.Format_ARGB32)},
            }
        )
        self.assertIn(first_id, field._artwork_cache)

        old_generation = field._artwork_generation
        field.set_albums((albums[0],))
        stale = QImage(8, 8, QImage.Format_ARGB32)
        field.set_artwork_batch(
            {
                "generation": old_generation,
                "album_ids": (albums[0].id,),
                "images": {albums[0].id: stale},
            }
        )
        self.assertNotIn(albums[0].id, field._artwork_cache)
        field.deleteLater()
        app.processEvents()
