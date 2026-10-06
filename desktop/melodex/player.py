from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from .playback_gateway import PlaybackGateway


def _expired(value: Any, skew_seconds: int = 15) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp() <= datetime.now(timezone.utc).timestamp() + skew_seconds
    except ValueError:
        return False


class FlowPlayer(QObject):
    trackChanged = Signal(dict)
    positionChanged = Signal(int, int)
    playingChanged = Signal(bool)
    queueChanged = Signal(list)
    manualAdvanced = Signal(dict, dict, int, int)
    error = Signal(str)

    def __init__(
        self,
        resolver,
        transition_for=None,
        parent=None,
        playback_refresher=None,
    ):
        super().__init__(parent)
        self.resolver = resolver
        self.playback_refresher = playback_refresher
        self.transition_for = transition_for
        self.gateway = PlaybackGateway()
        self.players = [QMediaPlayer(self), QMediaPlayer(self)]
        self.outputs = [QAudioOutput(self), QAudioOutput(self)]
        for player, output in zip(self.players, self.outputs):
            player.setAudioOutput(output)
            output.setVolume(1.0)
        self.active = 0
        self.queue: list[dict[str, Any]] = []
        self.index = -1
        self._crossfading = False
        self._transition_ms = 0
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        for player in self.players:
            player.errorOccurred.connect(lambda _error, msg: self.error.emit(str(msg)))

    def set_queue(self, tracks: list[dict[str, Any]], start: int = 0, autoplay: bool = True) -> None:
        self.queue = [dict(item) for item in tracks]
        self.index = max(0, min(len(self.queue) - 1, start)) if self.queue else -1
        self.queueChanged.emit(self.queue)
        if autoplay and self.index >= 0:
            self._load_index(self.index, play=True)

    def replace_queue_and_play(
        self,
        tracks: list[dict[str, Any]],
        start: int = 0,
        autoplay: bool = True,
    ) -> None:
        """Replace the route and cleanly end any in-progress two-deck fade."""
        for player in self.players:
            player.stop()
        self._crossfading = False
        self._transition_ms = 0
        self.outputs[self.active].setVolume(1.0)
        self.outputs[1 - self.active].setVolume(0.0)
        self.queue = [dict(item) for item in tracks]
        self.index = max(0, min(len(self.queue) - 1, int(start))) if self.queue else -1
        self.queueChanged.emit(self.queue)
        self.playingChanged.emit(False)
        if autoplay and self.index >= 0:
            self._load_index(self.index, play=True)

    def append_queue(self, tracks: list[dict[str, Any]], autoplay: bool = False) -> None:
        incoming = [dict(item) for item in tracks]
        if not incoming:
            return
        if not self.queue:
            self.set_queue(incoming, 0, autoplay)
            return
        self.queue.extend(incoming)
        self.queueChanged.emit(self.queue)

    def queue_snapshot(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.queue]

    def jump_to(self, index: int, autoplay: bool = True) -> bool:
        index = int(index)
        if not (0 <= index < len(self.queue)):
            return False
        self.players[self.active].stop()
        self._load_index(index, bool(autoplay))
        return True

    def replace_queue_item(
        self,
        index: int,
        track: dict[str, Any],
        *,
        autoplay: bool = False,
    ) -> bool:
        index = int(index)
        if not (0 <= index < len(self.queue)):
            return False
        self.queue[index] = dict(track)
        self.queueChanged.emit(self.queue)
        if autoplay:
            self.players[self.active].stop()
            self._load_index(index, True)
        return True

    def merge_queue_items(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        changes: dict[str, Any],
    ) -> int:
        updated = 0
        for index, item in enumerate(list(self.queue)):
            row = dict(item)
            if not predicate(row):
                continue
            self.queue[index] = {**row, **dict(changes)}
            updated += 1
        if updated:
            self.queueChanged.emit(self.queue)
        return updated

    def clear_queue(self) -> None:
        for player in self.players:
            player.stop()
        self.queue = []
        self.index = -1
        self._crossfading = False
        self.queueChanged.emit(self.queue)
        self.playingChanged.emit(False)

    def stop(self) -> None:
        for player in self.players:
            player.stop()
        self._crossfading = False
        self.playingChanged.emit(False)

    def close(self) -> None:
        self.stop()
        self.gateway.close()

    def current_track(self) -> dict[str, Any] | None:
        return dict(self.queue[self.index]) if 0 <= self.index < len(self.queue) else None

    def status(self) -> dict[str, Any]:
        player = self.players[self.active]
        return {
            "playing": player.playbackState() == QMediaPlayer.PlayingState,
            "position_ms": int(player.position()),
            "duration_ms": int(player.duration()),
            "volume": float(self.outputs[self.active].volume()),
            "index": int(self.index),
            "current_track": self.current_track(),
            "queue": [dict(item) for item in self.queue],
        }

    def _resolve_for_playback(self, index: int) -> dict[str, Any]:
        resolved = dict(self.resolver(dict(self.queue[index])))
        if _expired(resolved.get("expires_at")) and self.playback_refresher:
            resolved = dict(self.playback_refresher(resolved))
        self.queue[index] = resolved
        return resolved

    def _media_url_for(self, resolved: dict[str, Any]) -> QUrl:
        local = str(resolved.get("local_path") or "")
        if local:
            return QUrl.fromLocalFile(str(Path(local)))
        url = str(resolved.get("stream_url") or resolved.get("url") or "")
        if not url:
            raise RuntimeError("This source did not provide a playable stream")
        guarded_external = "_playback_allowed_hosts" in resolved
        kind = str(resolved.get("kind") or "http").casefold()
        needs_gateway = bool(
            resolved.get("headers")
            or resolved.get("cookies")
            or resolved.get("gateway_required")
            or (guarded_external and kind != "hls")
        )
        if needs_gateway:
            url = self.gateway.register(resolved)
        elif guarded_external:
            self.gateway.validate_resource(resolved)
        return QUrl(url)

    def _load_index(self, index: int, play: bool = True, deck: int | None = None) -> None:
        if not (0 <= index < len(self.queue)):
            return
        self.index = index
        deck = self.active if deck is None else deck
        player = self.players[deck]
        try:
            resolved = self._resolve_for_playback(index)
            player.setSource(self._media_url_for(resolved))
            if play:
                player.play()
                self.playingChanged.emit(True)
            self.trackChanged.emit(dict(self.queue[index]))
        except Exception as exc:
            self.error.emit(str(exc))

    def play_pause(self) -> None:
        player = self.players[self.active]
        if player.playbackState() == QMediaPlayer.PlayingState:
            player.pause()
            self.playingChanged.emit(False)
        else:
            if player.source().isEmpty() and self.index >= 0:
                self._load_index(self.index, True)
            else:
                player.play()
                self.playingChanged.emit(True)

    def set_playing(self, playing: bool) -> None:
        """Set playback state, freezing both decks when a transition is active."""
        player = self.players[self.active]
        if not playing:
            for deck in self.players:
                if deck.playbackState() == QMediaPlayer.PlayingState:
                    deck.pause()
            self.playingChanged.emit(False)
            return

        if player.source().isEmpty() and self.index >= 0:
            self._load_index(self.index, True)
            return
        player.play()
        if self._crossfading:
            self.players[1 - self.active].play()
        self.playingChanged.emit(True)

    def next(self) -> None:
        if self.index + 1 < len(self.queue):
            previous = dict(self.queue[self.index]) if 0 <= self.index < len(self.queue) else {}
            played_ms = int(self.players[self.active].position())
            duration_ms = int(self.players[self.active].duration())
            for player in self.players:
                player.stop()
            self.outputs[self.active].setVolume(1.0)
            self.outputs[1 - self.active].setVolume(0.0)
            self._crossfading = False
            self._transition_ms = 0
            self._load_index(self.index + 1, True)
            current = dict(self.queue[self.index]) if 0 <= self.index < len(self.queue) else {}
            self.manualAdvanced.emit(previous, current, played_ms, duration_ms)

    def replace_upcoming(self, tracks: list[dict[str, Any]]) -> None:
        """Replace only the queue tail, preserving the track currently playing."""
        incoming = [dict(item) for item in tracks]
        if not self.queue or self.index < 0:
            self.set_queue(incoming, 0, False)
            return
        if self._crossfading:
            next_deck = 1 - self.active
            self.players[next_deck].stop()
            self.outputs[next_deck].setVolume(0.0)
            self.outputs[self.active].setVolume(1.0)
            self._crossfading = False
            self._transition_ms = 0
        self.queue = self.queue[: self.index + 1] + incoming
        self.queueChanged.emit(self.queue)

    def previous(self) -> None:
        player = self.players[self.active]
        if player.position() > 5000:
            player.setPosition(0)
        elif self.index > 0:
            player.stop()
            self._load_index(self.index - 1, True)

    def seek(self, ms: int) -> None:
        self.players[self.active].setPosition(max(0, int(ms)))

    def set_volume(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        self.outputs[self.active].setVolume(value)

    def _transition_duration(self) -> int:
        if self.index + 1 >= len(self.queue):
            return 0
        if not self.transition_for:
            return 4500
        try:
            plan = self.transition_for(self.queue[self.index], self.queue[self.index + 1]) or {}
            return max(300, int(plan.get("duration_ms", 4500)))
        except Exception:
            return 4500

    def _begin_crossfade(self) -> None:
        if self._crossfading or self.index + 1 >= len(self.queue):
            return
        self._crossfading = True
        self._transition_ms = self._transition_duration()
        next_deck = 1 - self.active
        self.outputs[next_deck].setVolume(0.0)
        next_index = self.index + 1
        try:
            resolved = self._resolve_for_playback(next_index)
            url = self._media_url_for(resolved)
            if url.isEmpty():
                raise RuntimeError("Next track is not playable")
            self.players[next_deck].setSource(url)
            self.players[next_deck].play()
        except Exception as exc:
            self._crossfading = False
            self.error.emit(str(exc))

    def _tick(self) -> None:
        player = self.players[self.active]
        duration, pos = player.duration(), player.position()
        if duration > 0:
            self.positionChanged.emit(pos, duration)
        if player.playbackState() != QMediaPlayer.PlayingState:
            return
        if self.index + 1 >= len(self.queue):
            return
        transition = self._transition_duration()
        remaining = duration - pos if duration > 0 else 999999999
        if not self._crossfading and duration > 0 and remaining <= transition:
            self._begin_crossfade()
        if self._crossfading:
            next_deck = 1 - self.active
            progress = 1.0 - max(0.0, min(1.0, remaining / max(1, self._transition_ms)))
            self.outputs[self.active].setVolume(max(0.0, 1.0 - progress))
            self.outputs[next_deck].setVolume(min(1.0, progress))
            if progress >= 0.98 or remaining <= 80:
                self.players[self.active].stop()
                self.outputs[self.active].setVolume(1.0)
                self.active = next_deck
                self.index += 1
                self.outputs[self.active].setVolume(1.0)
                self._crossfading = False
                self.trackChanged.emit(dict(self.queue[self.index]))
                self.queueChanged.emit(self.queue)
