from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QImage
        from PySide6.QtWidgets import QApplication
        return Qt, QColor, QImage, QApplication
    except ImportError as exc:
        import pytest
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")


def test_lyric_flow_is_animated_and_transitions_between_lines():
    Qt, QColor, QImage, QApplication = _qt()
    from melodex.lyrics_state import LyricFrame
    from melodex.visualization_profile import build_visual_profile
    from melodex.visualization_scene import LivingScene

    app = QApplication.instance() or QApplication([])
    scene = LivingScene()
    scene.resize(900, 520)
    scene.set_profile(build_visual_profile(
        {"artist": "Example", "title": "Glow", "duration": 180},
        {
            "bpm": 112,
            "energy": 0.7,
            "spectral_centroid": 1500,
            "onset_density": 0.12,
            "energy_curve": [0.2, 0.7, 0.4, 0.9, 0.6],
        },
    ))
    scene.set_mode("lyrics")
    scene.show()
    scene.set_playing(True)
    app.processEvents()

    assert scene.animated_mode
    first = LyricFrame("", "First line", "Second line", True, "LRCLIB", 0)
    second = LyricFrame("First line", "Second line", "Third line", True, "LRCLIB", 1)
    scene.set_lyrics(first)
    scene.set_lyrics(second)
    assert scene._lyric_transition == 0.0

    scene._last_tick = time.monotonic() - 0.19
    scene._advance()
    assert 0.0 < scene._lyric_transition < 1.0

    image = QImage(scene.size(), QImage.Format_ARGB32)
    image.fill(QColor("#000000"))
    scene.render(image)
    assert not image.isNull()
    assert image.pixelColor(image.width() // 2, image.height() // 2) != QColor("#000000")

    scene.deleteLater()
    app.processEvents()


def test_lyric_flow_uses_cached_soft_artwork_background(tmp_path):
    Qt, QColor, QImage, QApplication = _qt()
    from melodex.visualization_profile import build_visual_profile
    from melodex.visualization_scene import LivingScene

    app = QApplication.instance() or QApplication([])
    art = QImage(80, 80, QImage.Format_ARGB32)
    art.fill(QColor("#d33b72"))
    path = tmp_path / "cover.png"
    assert art.save(str(path))

    scene = LivingScene()
    scene.resize(700, 420)
    scene.set_mode("lyrics")
    scene.set_profile(build_visual_profile({"artist": "A", "title": "B"}))
    scene.set_artwork(str(path))
    assert not scene._artwork_source.isNull()
    assert max(scene._artwork_source.width(), scene._artwork_source.height()) <= 256

    rendered = QImage(scene.size(), QImage.Format_ARGB32)
    rendered.fill(QColor("#000000"))
    scene.render(rendered)
    assert not scene._artwork_cache.isNull()
    assert max(scene._artwork_cache.width(), scene._artwork_cache.height()) <= (
        scene._quality_budget().artwork_cache_px
    )

    scene.deleteLater()
    app.processEvents()


def test_fullscreen_lyric_flow_reuses_the_same_document_and_timing():
    Qt, QColor, QImage, QApplication = _qt()
    from melodex.living_canvas import LivingCanvasView
    from melodex.lyrics_state import build_lyrics_document

    app = QApplication.instance() or QApplication([])
    view = LivingCanvasView()
    view.set_track({"artist": "Example", "title": "Track", "duration": 10})
    document = build_lyrics_document({
        "source": "local",
        "synced": [
            {"time_ms": 0, "text": "First"},
            {"time_ms": 5000, "text": "Second"},
        ],
    })
    view.set_lyrics(document)
    view.set_position(6000, 10000)
    view.show_lyric_flow_fullscreen()
    app.processEvents()

    assert view._lyric_flow_dialog is not None
    assert view._lyric_flow_scene is not None
    assert view._lyric_flow_scene.mode == "lyrics"
    assert view._lyric_flow_scene._immersive
    assert view._lyric_flow_scene._lyrics.current == "Second"

    view.set_position(1000, 10000)
    assert view._lyric_flow_scene._lyrics.current == "First"

    view._lyric_flow_dialog.close()
    app.processEvents()
    view.deleteLater()
    app.processEvents()


def test_now_playing_fullscreen_button_requests_lyric_flow_and_artwork_is_shared(tmp_path):
    Qt, QColor, QImage, QApplication = _qt()
    from melodex.rich_now_playing import RichNowPlayingWidget

    app = QApplication.instance() or QApplication([])
    widget = RichNowPlayingWidget(object())
    fullscreen = []
    artwork = []
    widget.lyricsFullscreenRequested.connect(lambda: fullscreen.append(True))
    widget.artworkChanged.connect(artwork.append)

    widget._apply_lyrics({
        "text": "Some words",
        "source": "local",
    })
    widget._show_fullscreen_lyrics()
    assert fullscreen == [True]

    art = QImage(40, 40, QImage.Format_ARGB32)
    art.fill(QColor("#236dc0"))
    path = tmp_path / "art.png"
    assert art.save(str(path))
    widget._set_art(str(path))
    assert artwork[-1] == str(path)

    widget._set_art("")
    assert artwork[-1] == ""

    widget.deleteLater()
    app.processEvents()
