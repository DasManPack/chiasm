from __future__ import annotations

import argparse
import json
from math import ceil
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from chiasm.field_model import Album  # noqa: E402
from chiasm.field_view import FieldCanvas  # noqa: E402
from melodex.living_canvas import LivingCanvasView  # noqa: E402
from melodex.lyrics_state import LyricFrame  # noqa: E402
from melodex.visualization_models import (  # noqa: E402
    MemoryMark,
    VisualNeighbour,
    build_constellation,
)
from melodex.visualization_profile import build_visual_profile  # noqa: E402
from melodex.visualization_scene import LivingScene  # noqa: E402


TRACK = {
    "artist": "Night Transit",
    "title": "Glass Horizons",
    "album": "Afterimage",
    "duration": 242,
}
ANALYSIS = {
    "bpm": 124,
    "energy": 0.74,
    "spectral_centroid": 1780,
    "onset_density": 0.14,
    "energy_curve": [
        0.18, 0.22, 0.30, 0.45, 0.61, 0.78, 0.86, 0.72,
        0.54, 0.48, 0.66, 0.82, 0.91, 0.70, 0.52, 0.34,
    ],
}
PALETTE = ("#75b8ff", "#4f7fdc", "#8d79d8", "#d574a9", "#6aa8c7", "#bed7ff")


def _album_art(path: Path, style: str = "dark") -> None:
    image = QImage(640, 640, QImage.Format_ARGB32_Premultiplied)
    bright = style == "bright"
    image.fill(QColor("#eaf1f8" if bright else "#07111d"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)

    bg = QLinearGradient(0, 0, 640, 640)
    if bright:
        bg.setColorAt(0.0, QColor("#f5e8d9"))
        bg.setColorAt(0.42, QColor("#a9d6e8"))
        bg.setColorAt(1.0, QColor("#d9c8ef"))
    else:
        bg.setColorAt(0.0, QColor("#0b1630"))
        bg.setColorAt(0.42, QColor("#274f7d"))
        bg.setColorAt(1.0, QColor("#101120"))
    painter.fillRect(image.rect(), bg)

    for x, y, radius, color in (
        (155, 180, 150, QColor(95, 177, 255, 110 if not bright else 145)),
        (470, 250, 190, QColor(107, 92, 220, 80 if not bright else 115)),
        (330, 500, 175, QColor(220, 91, 159, 65 if not bright else 105)),
    ):
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(x, y), radius, radius)

    painter.setPen(QColor(240, 247, 255, 210) if not bright else QColor(34, 48, 69, 190))
    painter.drawLine(70, 500, 570, 145)
    painter.setPen(QColor(180, 213, 245, 100) if not bright else QColor(49, 91, 130, 100))
    for offset in range(5):
        painter.drawLine(80, 535 + offset * 12, 520, 235 + offset * 7)
    painter.end()
    image.save(str(path))


def _save_widget(widget, path: Path, width: int, height: int) -> None:
    widget.resize(width, height)
    widget.show()
    QApplication.processEvents()
    image = QImage(widget.size(), QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor("#050910"))
    widget.render(image)
    if not image.save(str(path)):
        raise RuntimeError(f"Could not save {path.name}")
    widget.hide()
    QApplication.processEvents()


def _profile(track=TRACK, analysis=ANALYSIS):
    return build_visual_profile(track, analysis)


def _scene(width: int, height: int, track=TRACK, analysis=ANALYSIS) -> LivingScene:
    scene = LivingScene()
    scene.resize(width, height)
    scene.set_profile(_profile(track, analysis))
    scene.set_palette(PALETTE)
    scene.set_accent_color(QColor("#79b9ff"))
    scene.set_position_fraction(0.58)
    scene.set_quality("auto")
    scene._phase = 2.35
    scene._refresh_visual_state()
    return scene


def _neighbours(count: int = 18) -> tuple[VisualNeighbour, ...]:
    relations = ("Up next", "Played earlier", "Recently heard")
    candidates = []
    titles = ("Neon Return", "Parallel Lines", "Afterimage", "Soft Signal")
    for index in range(max(0, min(24, int(count)))):
        artist = (
            "Night Transit"
            if index < 4
            else ("Blue Static" if index < 9 else f"Artist {index + 1}")
        )
        title = titles[index] if index < 4 else f"Track {index + 1}"
        candidates.append(
            {
                "_visual_token": index + 1,
                "_visual_relation": relations[index % len(relations)],
                "artist": artist,
                "title": title,
                "album": "Afterimage" if index < 3 else f"Album {1 + index // 3}",
            }
        )
    return build_constellation(TRACK, candidates, limit=18)


def _memory(count: int = 36) -> tuple[MemoryMark, ...]:
    marks = []
    total = max(0, min(128, int(count)))
    for index in range(total):
        hour = (index * 5) % 24
        daypart = (
            "Late night" if hour < 5 or hour >= 22
            else "Morning" if hour < 12
            else "Afternoon" if hour < 17
            else "Evening"
        )
        marks.append(
            MemoryMark(
                label=f"Session {index + 1}",
                detail=f"Artist {1 + index % 8}",
                count=1 + index % 7,
                hue=(205 + index * 17) % 360,
                x=index / max(1, total - 1),
                y=0.14 + 0.68 * hour / 24.0,
                span=0.008 + (index % 5) * 0.006,
                time_label=f"Sep {10 + index // 3:02d} · {hour:02d}:{(index * 7) % 60:02d}",
                representative=f"Track {index + 1} · Artist {1 + index % 8}",
                daypart=daypart,
            )
        )
    return tuple(marks)


TRACK_SCENARIOS = (
    {
        "id": "sparse-acoustic",
        "track": {"artist": "Quiet Room Trio", "title": "Wood and Air", "duration": 214},
        "analysis": {
            "bpm": 82, "energy": 0.22, "spectral_centroid": 920,
            "onset_density": 0.035,
            "energy_curve": [0.12, 0.16, 0.22, 0.18, 0.26, 0.21, 0.29, 0.23],
        },
    },
    {
        "id": "dense-rock",
        "track": {"artist": "North Arcade", "title": "Overload", "duration": 246},
        "analysis": {
            "bpm": 146, "energy": 0.91, "spectral_centroid": 3020,
            "onset_density": 0.30,
            "energy_curve": [0.65, 0.92, 0.82, 0.97, 0.76, 0.94, 0.88, 0.99],
        },
    },
    {
        "id": "ambient",
        "track": {"artist": "Slow Meridian", "title": "Low Cloud", "duration": 378},
        "analysis": {
            "bpm": 62, "energy": 0.14, "spectral_centroid": 780,
            "onset_density": 0.018,
            "energy_curve": [0.12, 0.14, 0.11, 0.16, 0.13, 0.17, 0.12, 0.15],
        },
    },
    {
        "id": "electronic",
        "track": TRACK,
        "analysis": ANALYSIS,
    },
    {
        "id": "bass-heavy",
        "track": {"artist": "Subsurface", "title": "Pressure Field", "duration": 228},
        "analysis": {
            "bpm": 100, "energy": 0.74, "spectral_centroid": 620,
            "onset_density": 0.105,
            "energy_curve": [0.44, 0.72, 0.68, 0.78, 0.55, 0.83, 0.72, 0.76],
        },
    },
    {
        "id": "highly-dynamic",
        "track": {"artist": "Cinder Atlas", "title": "Quiet to Wide", "duration": 291},
        "analysis": {
            "bpm": 118, "energy": 0.58, "spectral_centroid": 2100,
            "onset_density": 0.17,
            "energy_curve": [0.08, 0.13, 0.24, 0.86, 0.96, 0.32, 0.12, 0.91],
        },
    },
)


def _chiasm_collection(count: int) -> tuple[tuple[Album, ...], int]:
    total = max(1, int(count))
    columns = 10 if total <= 50 else 40
    rows = ceil(total / columns)
    focus_index = min(total - 1, (rows // 2) * columns + columns // 2)
    albums = []
    for index in range(total):
        column = index % columns
        row = index // columns
        same_artist = index == focus_index or (index - focus_index) % 24 == 0
        albums.append(
            Album(
                id=f"chiasm-probe-{index:04d}",
                title=f"Afterimage {index + 1:04d}",
                artist="Night Transit" if same_artist else f"Artist {index % 36 + 1:02d}",
                region=f"Region {min(5, column * 5 // columns) + 1}",
                x=(column - (columns - 1) / 2) * 185.0,
                y=(row - (rows - 1) / 2) * 185.0,
                motif=index % 8,
                genres=("Ambient",) if index % 3 else ("Psychedelic",),
            )
        )
    return tuple(albums), focus_index


def capture(out: Path, width: int = 1440, height: int = 900) -> dict[str, object]:
    app = QApplication.instance() or QApplication([])
    out.mkdir(parents=True, exist_ok=True)

    art_path = out / "_fixture_art.png"
    _album_art(art_path)
    bright_art_path = out / "_fixture_art_bright.png"
    _album_art(bright_art_path, "bright")

    manifest: dict[str, object] = {
        "size": [width, height],
        "fixture_source": "synthetic track metadata and cached analysis values",
        "reference_comparison": {
            "status": "pending",
            "note": "Approved P13 concepts are not in the repository; captures do not establish mockup parity.",
        },
        "track_scenarios": TRACK_SCENARIOS,
        "coverage": {
            "track_archetypes": [scenario["id"] for scenario in TRACK_SCENARIOS],
            "artwork": ["dark", "bright"],
            "lyrics": ["synced immersive", "synced windowed", "untimed", "missing"],
            "constellation": ["sparse", "dense"],
            "memory_atlas": ["short", "large"],
            "motion_behavior": [
                "paused, hidden, and minimized timer stops: test_canvas_animation_stops_when_paused_hidden_or_minimized",
                "Battery static rendering: test_profile_pulse_and_weather_respect_battery_static_budget",
            ],
        },
        "captures": [],
    }

    def record(name: str, description: str) -> None:
        manifest["captures"].append({"file": name, "description": description})

    overview = LivingCanvasView()
    overview.set_track(TRACK, ANALYSIS)
    overview.set_palette(PALETTE)
    overview.set_accent_color(QColor("#79b9ff"))
    overview.set_artwork(str(art_path))
    overview.set_position(141000, 242000)
    _save_widget(overview, out / "00-visuals-overview.png", width, height)
    record(
        "00-visuals-overview.png",
        "Visuals shell with Track Sigil, grouped selector, Profile Pulse and dark artwork.",
    )
    overview.deleteLater()

    bright_overview = LivingCanvasView()
    bright_overview.set_track(TRACK, ANALYSIS)
    bright_overview.set_palette(PALETTE)
    bright_overview.set_accent_color(QColor("#79b9ff"))
    bright_overview.set_artwork(str(bright_art_path))
    bright_overview.set_position(141000, 242000)
    _save_widget(
        bright_overview,
        out / "14-visuals-overview-bright-artwork.png",
        width,
        height,
    )
    record(
        "14-visuals-overview-bright-artwork.png",
        "Visuals shell with the same track state over a bright synthetic cover.",
    )
    bright_overview.deleteLater()

    profile = _scene(width, height)
    profile.set_mode("living")
    _save_widget(profile, out / "01-profile-pulse.png", width, height)
    record("01-profile-pulse.png", "Profile Pulse for the electronic synthetic archetype.")
    profile.deleteLater()

    lyrics = _scene(width, height)
    lyrics.set_mode("lyrics")
    lyrics.set_immersive(True)
    lyrics.set_artwork(str(art_path))
    lyrics.set_lyrics(
        LyricFrame(
            "We left the city sleeping",
            "All the glass horizons open",
            "Every signal turns to blue",
            True,
            "LRCLIB",
            14,
        )
    )
    _save_widget(lyrics, out / "02-lyric-flow.png", width, height)
    record("02-lyric-flow.png", "Immersive synced Lyric Flow with artwork atmosphere.")
    lyrics.deleteLater()

    lyric_page = LivingCanvasView()
    lyric_page.set_track(TRACK, ANALYSIS)
    lyric_page.set_palette(PALETTE)
    lyric_page.set_accent_color(QColor("#79b9ff"))
    lyric_page.set_artwork(str(art_path))
    lyric_page.set_lyrics(
        {
            "source": "Synthetic fixture",
            "synced": [
                {"time_ms": 136_000, "text": "We left the city sleeping"},
                {"time_ms": 141_000, "text": "All the glass horizons open"},
                {"time_ms": 146_000, "text": "Every signal turns to blue"},
            ],
        }
    )
    lyric_page.set_position(141_000, 242_000)
    lyric_page.set_playing(False)
    lyric_mode_index = next(
        (
            index
            for index in range(lyric_page.mode_combo.count())
            if lyric_page.mode_combo.itemData(index) == "lyrics"
        ),
        -1,
    )
    if lyric_mode_index < 0:
        raise RuntimeError("Lyric Flow is missing from the built-in visual mode selector")
    lyric_page.mode_combo.setCurrentIndex(lyric_mode_index)
    _save_widget(lyric_page, out / "19-lyric-flow-page.png", width, height)
    record(
        "19-lyric-flow-page.png",
        "Full Visuals page in Lyric Flow with track identity, controls, timed lyrics and seek context.",
    )
    lyric_page.deleteLater()

    unsynced = _scene(width, height)
    unsynced.set_mode("lyrics")
    unsynced.set_immersive(True)
    unsynced.set_artwork(str(art_path))
    unsynced.set_lyrics(
        LyricFrame(
            "First unsynced line",
            "The words should still feel deliberate",
            "Even without timing metadata",
            False,
            "Embedded lyrics",
            6,
        )
    )
    _save_widget(unsynced, out / "03-lyric-flow-unsynced.png", width, height)
    record("03-lyric-flow-unsynced.png", "Untimed Lyric Flow fallback.")
    unsynced.deleteLater()

    windowed_lyrics = _scene(width, height)
    windowed_lyrics.set_mode("lyrics")
    windowed_lyrics.set_immersive(False)
    windowed_lyrics.set_artwork(str(bright_art_path))
    windowed_lyrics.set_lyrics(
        LyricFrame(
            "We left the city sleeping",
            "All the glass horizons open",
            "Every signal turns to blue",
            True,
            "LRCLIB",
            14,
        )
    )
    _save_widget(
        windowed_lyrics,
        out / "16-lyric-flow-windowed-bright-artwork.png",
        width,
        height,
    )
    record(
        "16-lyric-flow-windowed-bright-artwork.png",
        "Windowed synced Lyric Flow over a bright synthetic cover.",
    )
    windowed_lyrics.deleteLater()

    constellation = _scene(width, height)
    constellation.set_mode("constellation")
    constellation.set_neighbours(_neighbours())
    constellation._selected_token = 2
    constellation.set_neighbour_artwork(2, str(art_path))
    _save_widget(constellation, out / "04-constellation.png", width, height)
    record("04-constellation.png", "Dense Constellation with pinned recognition card.")
    constellation.deleteLater()

    sparse_constellation = _scene(width, height)
    sparse_constellation.set_mode("constellation")
    sparse_constellation.set_neighbours(_neighbours(4))
    sparse_constellation._selected_token = 2
    sparse_constellation.set_neighbour_artwork(2, str(art_path))
    _save_widget(
        sparse_constellation,
        out / "17-constellation-sparse.png",
        width,
        height,
    )
    record(
        "17-constellation-sparse.png",
        "Sparse Constellation with four candidates and a pinned recognition card.",
    )
    sparse_constellation.deleteLater()

    weather = _scene(width, height)
    weather.set_mode("weather")
    _save_widget(weather, out / "05-sonic-weather.png", width, height)
    record("05-sonic-weather.png", "Sonic Weather for the electronic archetype.")
    weather.deleteLater()

    for scenario in TRACK_SCENARIOS:
        scenario_id = str(scenario["id"])
        if scenario_id == "electronic":
            continue
        track = scenario["track"]
        analysis = scenario["analysis"]
        profile_scene = _scene(width, height, track, analysis)
        profile_scene.set_mode("living")
        profile_file = f"15-profile-pulse-{scenario_id}.png"
        _save_widget(profile_scene, out / profile_file, width, height)
        record(profile_file, f"Profile Pulse synthetic {scenario_id} archetype.")
        profile_scene.deleteLater()

        weather_scene = _scene(width, height, track, analysis)
        weather_scene.set_mode("weather")
        weather_file = f"15-sonic-weather-{scenario_id}.png"
        _save_widget(weather_scene, out / weather_file, width, height)
        record(weather_file, f"Sonic Weather synthetic {scenario_id} archetype.")
        weather_scene.deleteLater()

    memory = _scene(width, height)
    memory.set_mode("memory")
    memory.set_memory(_memory(), "sessions")
    memory._selected_memory_index = 23
    _save_widget(memory, out / "06-memory-atlas.png", width, height)
    record("06-memory-atlas.png", "Memory Atlas with pinned session card.")
    memory.deleteLater()

    short_memory = _scene(width, height)
    short_memory.set_mode("memory")
    short_memory.set_memory(_memory(8), "sessions")
    short_memory._selected_memory_index = 5
    _save_widget(short_memory, out / "18-memory-atlas-short.png", width, height)
    record("18-memory-atlas-short.png", "Memory Atlas with a short eight-session history.")
    short_memory.deleteLater()

    journey = _scene(width, height)
    journey.set_mode("journey")
    _save_widget(journey, out / "07-musical-journey.png", width, height)
    record("07-musical-journey.png", "Musical Journey context view.")
    journey.deleteLater()

    album = _scene(width, height)
    album.set_mode("album_world")
    _save_widget(album, out / "08-album-world-legacy.png", width, height)
    record(
        "08-album-world-legacy.png",
        "Legacy/internal Album World compatibility renderer; no longer in the public selector.",
    )
    album.deleteLater()

    minimal = _scene(width, height)
    minimal.set_mode("minimal")
    _save_widget(minimal, out / "09-minimal.png", width, height)
    record("09-minimal.png", "Minimal watch scene.")
    minimal.deleteLater()

    reduced = _scene(width, height)
    reduced.set_mode("weather")
    reduced.set_quality("auto")
    reduced._effective_quality = "eco"
    reduced._performance.effective = "eco"
    reduced._phase = 2.35
    reduced._refresh_visual_state()
    _save_widget(reduced, out / "10-auto-reduced-weather.png", width, height)
    record("10-auto-reduced-weather.png", "Sonic Weather with Auto reduced rendering budget.")
    reduced.deleteLater()

    empty = _scene(width, height)
    empty.set_mode("lyrics")
    empty.set_immersive(True)
    empty.set_lyrics(LyricFrame("", "", "", False, "", -1))
    _save_widget(empty, out / "11-lyrics-empty.png", width, height)
    record("11-lyrics-empty.png", "Lyric Flow empty state.")
    empty.deleteLater()

    albums_50, focus_50 = _chiasm_collection(50)
    chiasm_overview = FieldCanvas(albums_50)
    chiasm_overview.camera.zoom = 0.62
    chiasm_overview.focus_album(albums_50[focus_50])
    chiasm_overview.open_lens()
    _save_widget(
        chiasm_overview,
        out / "12-chiasm-50-album-lens.png",
        width,
        height,
    )
    record(
        "12-chiasm-50-album-lens.png",
        "Chiasm's 50-album field with the focused album lens attached inside the collection.",
    )
    chiasm_overview.deleteLater()

    albums_1200, focus_1200 = _chiasm_collection(1200)
    chiasm_large = FieldCanvas(albums_1200, live_playback=True)
    focus_album = albums_1200[focus_1200]
    next_album = next(
        album
        for album in albums_1200
        if album.id != focus_album.id and album.artist == focus_album.artist
    )
    chiasm_large.camera.center_x = focus_album.x
    chiasm_large.camera.center_y = focus_album.y
    chiasm_large.camera.zoom = 1.28
    chiasm_large.set_playback_state(
        {
            "artist": focus_album.artist,
            "title": "Glass Horizons",
            "local_path": "/synthetic/afterimage/track.flac",
        },
        playing=True,
        position_ms=141_000,
        duration_ms=242_000,
        album_id=focus_album.id,
        can_next=True,
    )
    chiasm_large.set_arc_state(
        active=True,
        next_album=next_album,
        reason="same artist",
    )
    chiasm_large.set_trace(
        [
            {
                "album_id": focus_album.id,
                "title": focus_album.title,
                "artist": focus_album.artist,
                "activity": "listen",
                "recorded_at": 1.0,
                "playable": True,
            }
        ]
    )
    chiasm_large.focus_album(focus_album)
    chiasm_large.open_lens()
    _save_widget(
        chiasm_large,
        out / "13-chiasm-1200-album-playing-lens.png",
        width,
        height,
    )
    record(
        "13-chiasm-1200-album-playing-lens.png",
        "Chiasm's 1,200-album field with Horizon lens, current track, and an explainable Arc.",
    )
    chiasm_large.deleteLater()

    discovery_albums, known_index = _chiasm_collection(50)
    known_album = discovery_albums[known_index]
    connected_album = next(
        album
        for album in discovery_albums
        if album.id != known_album.id
        and album.artist != known_album.artist
        and set(album.genres).intersection(known_album.genres)
    )

    discovery_horizon = FieldCanvas(discovery_albums)
    discovery_horizon.camera.center_x = known_album.x
    discovery_horizon.camera.center_y = known_album.y
    discovery_horizon.camera.zoom = 1.28
    discovery_horizon.focus_album(known_album)
    discovery_horizon.open_lens()
    _save_widget(
        discovery_horizon,
        out / "14-chiasm-discovery-horizon.png",
        width,
        height,
    )
    record(
        "14-chiasm-discovery-horizon.png",
        "C11 starting point: a familiar album with a named shared-genre Horizon link to a less familiar album.",
    )
    discovery_horizon.deleteLater()

    discovery_trace = FieldCanvas(discovery_albums, live_playback=True)
    discovery_trace.camera.center_x = connected_album.x
    discovery_trace.camera.center_y = connected_album.y
    discovery_trace.camera.zoom = 1.28
    discovery_trace.set_playback_state(
        {
            "artist": connected_album.artist,
            "title": "Blue Hour",
            "local_path": "/synthetic/discovery/track.flac",
        },
        playing=True,
        position_ms=48_000,
        duration_ms=216_000,
        album_id=connected_album.id,
        can_next=True,
    )
    discovery_trace.set_trace(
        [
            {
                "album_id": connected_album.id,
                "title": connected_album.title,
                "artist": connected_album.artist,
                "activity": "listen",
                "recorded_at": 2.0,
                "playable": True,
            },
            {
                "album_id": known_album.id,
                "title": known_album.title,
                "artist": known_album.artist,
                "activity": "explore",
                "recorded_at": 1.0,
                "playable": True,
            },
        ]
    )
    discovery_trace.focus_album(connected_album)
    discovery_trace.open_lens()
    discovery_trace._lens_panel = "trace"
    discovery_trace._refresh_accessible_description()
    _save_widget(
        discovery_trace,
        out / "15-chiasm-discovery-trace.png",
        width,
        height,
    )
    record(
        "15-chiasm-discovery-trace.png",
        "C11 return point: a connected album playing, with the familiar starting album in Trace.",
    )
    discovery_trace.deleteLater()

    QApplication.processEvents()
    art_path.unlink(missing_ok=True)
    bright_art_path.unlink(missing_ok=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture deterministic Melodex visual QA scenes.")
    parser.add_argument("--output", type=Path, default=Path("visual-qa"))
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    manifest = capture(args.output, args.width, args.height)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
