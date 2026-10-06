from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _player():
    import pytest

    try:
        from PySide6.QtWidgets import QApplication
        from melodex.player import FlowPlayer
    except ImportError as exc:
        pytest.skip(f"Qt desktop runtime is unavailable: {exc}")

    QApplication.instance() or QApplication([])
    player = FlowPlayer(lambda track: dict(track))
    loaded = []

    def fake_load(index: int, play: bool = True, deck=None):
        player.index = index
        loaded.append((index, bool(play)))

    player._load_index = fake_load
    return player, loaded


def test_jump_to_uses_public_queue_contract():
    player, loaded = _player()
    player.set_queue([{"track_id": "a"}, {"track_id": "b"}], 0, False)

    assert player.jump_to(1, autoplay=True) is True
    assert player.index == 1
    assert loaded == [(1, True)]
    assert player.jump_to(4) is False

    player.close()


def test_replace_queue_item_emits_and_can_replay():
    player, loaded = _player()
    changes = []
    player.queueChanged.connect(lambda queue: changes.append([dict(x) for x in queue]))
    player.set_queue([{"track_id": "a"}, {"track_id": "b"}], 0, False)
    changes.clear()

    assert player.replace_queue_item(
        0,
        {"track_id": "resolved", "stream_url": "https://example.invalid/a"},
        autoplay=True,
    ) is True

    assert player.queue[0]["track_id"] == "resolved"
    assert changes[-1][0]["track_id"] == "resolved"
    assert loaded == [(0, True)]
    assert player.replace_queue_item(9, {"track_id": "x"}) is False

    player.close()


def test_merge_queue_items_updates_matching_rows_once():
    player, _loaded = _player()
    changes = []
    player.queueChanged.connect(lambda queue: changes.append([dict(x) for x in queue]))
    player.set_queue(
        [
            {"track_id": "a", "local_path": "/music/a.flac", "title": "Old"},
            {"track_id": "b", "local_path": "/music/b.flac", "title": "Other"},
            {"track_id": "c", "local_path": "/music/a.flac", "title": "Old again"},
        ],
        0,
        False,
    )
    changes.clear()

    count = player.merge_queue_items(
        lambda item: item.get("local_path") == "/music/a.flac",
        {"title": "Corrected"},
    )

    assert count == 2
    assert [row["title"] for row in player.queue] == [
        "Corrected",
        "Other",
        "Corrected",
    ]
    assert len(changes) == 1

    player.close()


def test_append_queue_owns_empty_and_nonempty_cases():
    player, _loaded = _player()
    player.append_queue([{"track_id": "a"}], autoplay=False)
    player.append_queue([{"track_id": "b"}], autoplay=False)

    assert [row["track_id"] for row in player.queue_snapshot()] == ["a", "b"]

    player.close()


def test_set_playing_freezes_both_decks_during_crossfade():
    from PySide6.QtMultimedia import QMediaPlayer

    player, _loaded = _player()

    class FakeSource:
        @staticmethod
        def isEmpty():
            return False

    class FakeDeck:
        def __init__(self):
            self.state = QMediaPlayer.PlayingState

        def playbackState(self):
            return self.state

        def source(self):
            return FakeSource()

        def pause(self):
            self.state = QMediaPlayer.PausedState

        def play(self):
            self.state = QMediaPlayer.PlayingState

        def stop(self):
            self.state = QMediaPlayer.StoppedState

    player.players = [FakeDeck(), FakeDeck()]
    player.active = 0
    player.index = 1
    player._crossfading = True
    changes = []
    player.playingChanged.connect(changes.append)

    player.set_playing(False)
    assert [deck.playbackState() for deck in player.players] == [
        QMediaPlayer.PausedState,
        QMediaPlayer.PausedState,
    ]
    player.set_playing(True)
    assert [deck.playbackState() for deck in player.players] == [
        QMediaPlayer.PlayingState,
        QMediaPlayer.PlayingState,
    ]
    assert changes == [False, True]
    player.close()


def test_replace_queue_and_play_stops_crossfade_before_starting_route():
    from PySide6.QtMultimedia import QMediaPlayer

    player, loaded = _player()

    class FakeDeck:
        def __init__(self):
            self.state = QMediaPlayer.PlayingState
            self.stops = 0

        def stop(self):
            self.stops += 1
            self.state = QMediaPlayer.StoppedState

    player.players = [FakeDeck(), FakeDeck()]
    player.active = 1
    player._crossfading = True
    player._transition_ms = 5000

    player.replace_queue_and_play(
        [{"track_id": "first"}, {"track_id": "second"}],
        start=1,
        autoplay=True,
    )

    assert [deck.stops for deck in player.players] == [1, 1]
    assert player._crossfading is False
    assert player._transition_ms == 0
    assert player.index == 1
    assert player.queue[1]["track_id"] == "second"
    assert loaded == [(1, True)]
    player.close()
