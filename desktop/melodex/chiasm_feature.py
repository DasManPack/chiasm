"""Own Chiasm's spatial collection page and listening interactions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCompleter,
    QFileDialog,
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ChiasmFeature(QObject):
    """Build and coordinate the spatial collection through explicit boundaries.

    The feature owns its page, field state, Trace, artwork loading, and Arc
    route. FlowPlayer remains authoritative; playback changes leave through
    semantic signals connected by the application shell.
    """

    playPauseRequested = Signal()
    nextRequested = Signal()
    replaceQueueAndPlayRequested = Signal(object, int, bool)
    replaceUpcomingRequested = Signal(object)
    setPlayingRequested = Signal(bool)
    statusMessageRequested = Signal(str, int)
    interactionMeasured = Signal(str, float)
    addMusicFolderRequested = Signal()

    def __init__(
        self,
        providers: Any,
        user_state: Any,
        *,
        local_intelligence: Callable[[], Any],
        metadata: Callable[[], Any],
        run_async: Callable[..., Any],
        player_status: Callable[[], dict[str, Any]],
        current_track: Callable[[], dict[str, Any] | None],
        page_titles: dict[str, QLabel],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.providers = providers
        self.state = user_state
        self._local_intelligence_getter = local_intelligence
        self._metadata_getter = metadata
        self._run_async = run_async
        self._player_status = player_status
        self._current_track_getter = current_track
        self.page_titles = page_titles

        self.page = QWidget()
        self.built = False
        self.chiasm_adapter: Any = None
        self.chiasm_canvas: Any = None
        self.chiasm_album_tracks: dict[str, list[dict[str, Any]]] = {}
        self.chiasm_track_to_album: dict[str, str] = {}
        self.chiasm_arc_route_ids: list[str] = []
        self.chiasm_arc_reasons: list[str] = []
        self.chiasm_arc_current_index = 0
        self.chiasm_arc_active = False
        self.chiasm_arc_paused = False

        layout = QVBoxLayout(self.page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(6)
        title = QLabel("Chiasm")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.page_titles["chiasm"] = title
        subtitle = QLabel("Preparing your collection for in-place listening…")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)
        hint = QLabel("Opening…")
        hint.setObjectName("pageHint")
        layout.addWidget(hint)
        layout.addStretch(1)

    @property
    def local_intelligence(self) -> Any:
        return self._local_intelligence_getter()

    @property
    def metadata(self) -> Any:
        return self._metadata_getter()

    def _status(self, message: str, timeout_ms: int = 0) -> None:
        self.statusMessageRequested.emit(str(message), int(timeout_ms))

    def explore_card(self, navigate: Callable[[str], None]) -> QWidget:
        from .ux_components import ActionCard

        card = ActionCard(
            "Chiasm",
            "Enter your collection as a place and listen without leaving it.",
            eyebrow="In place",
            action_text="Open field",
        )
        card.clicked.connect(lambda: navigate("chiasm"))
        return card

    @staticmethod
    def _clear_layout(layout) -> None:
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            if child_layout is not None:
                ChiasmFeature._clear_layout(child_layout)
                child_layout.deleteLater()
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def build(self) -> None:
        if self.built:
            return

        from chiasm.field_view import FieldCanvas
        from chiasm.melodex_adapter import MelodexCollectionAdapter

        layout = self.page.layout()
        if layout is None:
            layout = QVBoxLayout(self.page)
        else:
            self._clear_layout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(16, 12, 16, 8)
        header.setSpacing(10)
        mark = QLabel()
        mark_path = Path(__file__).resolve().parent / "assets" / "chiasm-mark.png"
        pixmap = QPixmap(str(mark_path))
        if not pixmap.isNull():
            mark.setPixmap(pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        mark.setFixedSize(30, 30)
        mark.setAccessibleName("Chiasm")
        header.addWidget(mark)
        header.addStretch(1)
        self.find_album_button = QToolButton()
        self.find_album_button.setText("Find")
        self.find_album_button.setObjectName("chiasmFindAlbum")
        self.find_album_button.setMinimumSize(54, 36)
        self.find_album_button.setAccessibleName("Find an album or artist")
        self.find_album_button.setToolTip("Find an album or artist in this field (Ctrl+F)")
        self.find_album_button.setEnabled(False)
        self.find_album_button.clicked.connect(self._show_album_search)
        header.addWidget(self.find_album_button)

        self.album_search = QLineEdit(self.page)
        self.album_search.setObjectName("chiasmAlbumSearch")
        self.album_search.setPlaceholderText("Album or artist")
        self.album_search.setAccessibleName("Find an album or artist in this collection")
        self.album_search.setClearButtonEnabled(True)
        self.album_search.setFixedWidth(250)
        self.album_search.hide()
        self._album_search_model = QStandardItemModel(self.album_search)
        self._album_search_completer = QCompleter(self._album_search_model, self.album_search)
        self._album_search_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._album_search_completer.setFilterMode(Qt.MatchContains)
        self._album_search_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.album_search.setCompleter(self._album_search_completer)
        self._album_search_completer.activated[str].connect(
            self._choose_album_search_result
        )
        self.album_search.returnPressed.connect(self._submit_album_search)
        header.addWidget(self.album_search)

        add_folder = QPushButton("＋  Add folder")
        add_folder.setObjectName("chiasmAddFolder")
        add_folder.setMinimumSize(112, 36)
        add_folder.setToolTip("Add a music folder")
        add_folder.setAccessibleName("Add a music folder")
        add_folder.setCursor(Qt.PointingHandCursor)
        add_folder.clicked.connect(self.addMusicFolderRequested.emit)
        header.addWidget(add_folder)
        layout.addLayout(header)
        self.page_titles["chiasm"] = mark

        self.chiasm_adapter = MelodexCollectionAdapter(
            self.providers,
            local_intelligence=lambda: self.local_intelligence,
            metadata=lambda: self.metadata,
        )
        self.chiasm_canvas = FieldCanvas(
            (),
            parent=self.page,
            live_playback=True,
        )
        self.chiasm_canvas.interactionMeasured.connect(self.interactionMeasured.emit)
        self.chiasm_canvas.findRequested.connect(self._show_album_search)
        self.chiasm_canvas.albumFocused.connect(
            lambda album_id: self._record_chiasm_trace_event(album_id, "explore")
        )
        self.chiasm_canvas.playRequested.connect(self._play_chiasm_album)
        self.chiasm_canvas.playPauseRequested.connect(self.playPauseRequested.emit)
        self.chiasm_canvas.nextRequested.connect(self.nextRequested.emit)
        self.chiasm_canvas.arcRequested.connect(self._start_chiasm_arc)
        self.chiasm_canvas.arcSteerRequested.connect(self._steer_chiasm_arc)
        self.chiasm_canvas.arcPauseRequested.connect(self._toggle_chiasm_arc_pause)
        self.chiasm_canvas.arcTakeControlRequested.connect(
            self._take_control_from_chiasm_arc
        )
        self.chiasm_canvas.artworkRequested.connect(self._chiasm_artwork_requested)
        layout.addWidget(self.chiasm_canvas, 1)
        self.built = True
        self._refresh_chiasm_trace()
        self._sync_chiasm_playback()

    def refresh(self) -> None:
        if self.chiasm_canvas is None:
            return
        self._status("Preparing your albums for Chiasm…", 3000)
        self._run_async(
            self.chiasm_adapter.build_collection,
            self._apply_chiasm_payload,
            priority="visible",
            task_name="chiasm-field-model",
            replace_key="page:chiasm-field",
        )

    def on_track_changed(self, track: object) -> None:
        self._record_chiasm_listening_album(track)
        self._sync_chiasm_playback()

    def on_playing_changed(self, _playing: bool) -> None:
        self._sync_chiasm_playback()

    def on_position_changed(self, _position: int, _duration: int) -> None:
        self._sync_chiasm_playback()

    def handle_arc_play_pause(self) -> bool:
        if not self.chiasm_arc_active:
            return False
        is_playing = bool(self._player_status().get("playing"))
        self.chiasm_arc_paused = is_playing
        self.setPlayingRequested.emit(not is_playing)
        return True

    def _refresh_chiasm_trace(self) -> None:
        canvas = self.chiasm_canvas
        if canvas is None:
            return
        entries = self.state.recent_chiasm_trace(48)
        for entry in entries:
            album_id = str(entry.get("album_id") or "")
            entry["playable"] = bool(self.chiasm_album_tracks.get(album_id))
        canvas.set_trace(entries)

    def _record_chiasm_trace_event(self, album_id: str, activity: str) -> None:
        canvas = self.chiasm_canvas
        if canvas is None:
            return
        album = canvas.album_by_id(str(album_id or ""))
        if album is None:
            return
        self.state.record_chiasm_trace(
            album.id,
            title=album.title,
            artist=album.artist,
            activity=activity,
            limit=48,
        )
        self._refresh_chiasm_trace()

    def _record_chiasm_listening_album(self, track: object) -> None:
        row = dict(track) if isinstance(track, dict) else {}
        path = str(row.get("local_path") or "").strip()
        album_id = self.chiasm_track_to_album.get(path)
        if album_id:
            self._record_chiasm_trace_event(album_id, "listen")

    def _play_chiasm_album(self, album_id: str) -> None:
        tracks = [
            dict(track)
            for track in self.chiasm_album_tracks.get(str(album_id), [])
        ]
        if not tracks:
            self._status("This album has no playable local tracks", 4000)
            return
        album = self.chiasm_canvas.album_by_id(str(album_id))
        self._clear_chiasm_arc()
        self.replaceQueueAndPlayRequested.emit(tracks, 0, True)
        if album is not None:
            self._status(f"Playing {album.artist} — {album.title}", 4500)

    def _sync_chiasm_playback(self) -> None:
        canvas = self.chiasm_canvas
        if canvas is None:
            return
        status = self._player_status()
        track = status.get("current_track")
        row = dict(track) if isinstance(track, dict) else None
        track_path = str((row or {}).get("local_path") or "").strip()
        queue = list(status.get("queue") or [])
        index = int(status.get("index", -1))
        canvas.set_playback_state(
            row,
            playing=bool(status.get("playing")),
            position_ms=int(status.get("position_ms") or 0),
            duration_ms=int(status.get("duration_ms") or 0),
            album_id=self.chiasm_track_to_album.get(track_path),
            can_next=index >= 0 and index + 1 < len(queue),
        )
        if self.chiasm_arc_active:
            current_album_id = self.chiasm_track_to_album.get(track_path)
            if current_album_id not in self.chiasm_arc_route_ids:
                self._clear_chiasm_arc()
            else:
                self.chiasm_arc_current_index = self.chiasm_arc_route_ids.index(
                    current_album_id
                )
                self.chiasm_arc_paused = not bool(status.get("playing"))
                next_index = self.chiasm_arc_current_index + 1
                next_album = (
                    canvas.album_by_id(self.chiasm_arc_route_ids[next_index])
                    if next_index < len(self.chiasm_arc_route_ids)
                    else None
                )
                reason = (
                    self.chiasm_arc_reasons[self.chiasm_arc_current_index]
                    if next_album is not None
                    and self.chiasm_arc_current_index < len(self.chiasm_arc_reasons)
                    else ""
                )
                canvas.set_arc_state(
                    active=True,
                    paused=self.chiasm_arc_paused,
                    next_album=next_album,
                    reason=reason,
                )
        else:
            canvas.set_arc_state(active=False)

    def _chiasm_current_album_id(self) -> str | None:
        current = self._current_track_getter() or {}
        path = str(current.get("local_path") or "").strip()
        return self.chiasm_track_to_album.get(path)

    def _remaining_chiasm_album_tracks(self, album_id: str) -> list[dict[str, Any]]:
        tracks = [
            dict(track)
            for track in self.chiasm_album_tracks.get(str(album_id), [])
        ]
        current = self._current_track_getter() or {}
        current_path = str(current.get("local_path") or "").strip()
        if not current_path:
            return tracks
        current_index = next(
            (
                index
                for index, track in enumerate(tracks)
                if str(track.get("local_path") or "").strip() == current_path
            ),
            None,
        )
        return tracks[current_index + 1 :] if current_index is not None else tracks

    def _chiasm_arc_tail(self, album_ids: list[str]) -> list[dict[str, Any]]:
        return [
            dict(track)
            for album_id in album_ids
            for track in self.chiasm_album_tracks.get(album_id, [])
        ]

    def _chiasm_arc_albums(self):
        return tuple(
            album
            for album in self.chiasm_canvas.albums
            if self.chiasm_album_tracks.get(album.id)
        )

    def _start_chiasm_arc(self, album_id: str) -> None:
        from chiasm.arc_model import build_arc_route

        seed_id = str(album_id or "").strip()
        seed_tracks = self.chiasm_album_tracks.get(seed_id, [])
        if not seed_tracks:
            self._status("This album has no playable local tracks", 4000)
            return
        hops = build_arc_route(self._chiasm_arc_albums(), seed_id)
        if not hops:
            self._status("Arc needs at least two local albums to make a route.", 6000)
            return

        route_ids = [seed_id, *(hop.album_id for hop in hops)]
        reasons = [hop.reason for hop in hops]
        if self._chiasm_current_album_id() == seed_id:
            upcoming = self._remaining_chiasm_album_tracks(seed_id)
            upcoming.extend(self._chiasm_arc_tail(route_ids[1:]))
            self.replaceUpcomingRequested.emit(upcoming)
        else:
            self.replaceQueueAndPlayRequested.emit(
                [*seed_tracks, *self._chiasm_arc_tail(route_ids[1:])],
                0,
                True,
            )
        self.chiasm_arc_route_ids = route_ids
        self.chiasm_arc_reasons = reasons
        self.chiasm_arc_current_index = 0
        self.chiasm_arc_active = True
        self.chiasm_arc_paused = not bool(self._player_status().get("playing"))
        self._sync_chiasm_playback()
        next_album = self.chiasm_canvas.album_by_id(route_ids[1])
        self._status(
            f"Arc started · next: {next_album.title} · {reasons[0]}",
            6000,
        )

    def _steer_chiasm_arc(self, album_id: str) -> None:
        from chiasm.arc_model import build_arc_route

        current_id = self._chiasm_current_album_id()
        target_id = str(album_id or "").strip()
        target_tracks = self.chiasm_album_tracks.get(target_id, [])
        if not self.chiasm_arc_active or not current_id or not target_tracks:
            return
        if target_id == current_id:
            self._status("Choose a different album to steer the Arc", 3500)
            return

        hops = build_arc_route(
            self._chiasm_arc_albums(),
            target_id,
            exclude_ids=(current_id,),
        )
        route_ids = [current_id, target_id, *(hop.album_id for hop in hops)]
        reasons = ["chosen by you", *(hop.reason for hop in hops)]
        upcoming = self._remaining_chiasm_album_tracks(current_id)
        upcoming.extend(self._chiasm_arc_tail(route_ids[1:]))
        self.replaceUpcomingRequested.emit(upcoming)
        self.chiasm_arc_route_ids = route_ids
        self.chiasm_arc_reasons = reasons
        self.chiasm_arc_current_index = 0
        self.chiasm_arc_paused = not bool(self._player_status().get("playing"))
        self._sync_chiasm_playback()
        target = self.chiasm_canvas.album_by_id(target_id)
        if target is not None:
            self._status(f"Arc steered · next: {target.title} · chosen by you", 4500)

    def _toggle_chiasm_arc_pause(self) -> None:
        if self.chiasm_arc_active:
            self.playPauseRequested.emit()

    def _take_control_from_chiasm_arc(self) -> None:
        if not self.chiasm_arc_active:
            return
        self.replaceUpcomingRequested.emit([])
        self._clear_chiasm_arc()
        self._status("Arc ended · current track continues; choose what plays next", 5000)

    def _clear_chiasm_arc(self) -> None:
        self.chiasm_arc_active = False
        self.chiasm_arc_paused = False
        self.chiasm_arc_route_ids = []
        self.chiasm_arc_reasons = []
        self.chiasm_arc_current_index = 0
        if self.chiasm_canvas is not None:
            self.chiasm_canvas.set_arc_state(active=False)

    def _apply_chiasm_payload(self, payload: object) -> None:
        if not isinstance(payload, dict) or self.chiasm_canvas is None:
            return
        self.chiasm_album_tracks = {
            str(album_id): [
                dict(track)
                for track in list(tracks or [])
                if isinstance(track, dict)
            ]
            for album_id, tracks in dict(payload.get("tracks_by_album") or {}).items()
        }
        self.chiasm_track_to_album = {
            str(path): str(album_id)
            for path, album_id in dict(payload.get("track_to_album") or {}).items()
        }
        albums = tuple(payload.get("albums") or ())
        self.chiasm_canvas.set_albums(albums)
        self._refresh_album_search_index(albums)
        self._refresh_chiasm_trace()
        self._record_chiasm_listening_album(self._current_track_getter())
        self._sync_chiasm_playback()
        status = str(payload.get("status") or "ready")
        if status == "provider-unavailable":
            message = (
                "Local music is temporarily unavailable · Chiasm will be ready "
                "when the catalog returns"
            )
        elif status == "empty":
            message = "Add local music to build Chiasm's field"
        elif status == "metadata-only":
            message = (
                f"Chiasm ready · {len(albums):,} local albums · metadata layout · "
                "double-click or open a lens to play"
            )
        else:
            message = (
                f"Chiasm ready · {len(albums):,} local albums · "
                "double-click or open a lens to play"
            )
        self._status(message, 5000)

    def _refresh_album_search_index(self, albums: tuple[Any, ...]) -> None:
        model = getattr(self, "_album_search_model", None)
        if model is None:
            return
        model.clear()
        entries = []
        labels: dict[str, int] = {}
        for album in albums:
            title = str(getattr(album, "title", "") or "Untitled album").strip()
            artist = str(getattr(album, "artist", "") or "Unknown artist").strip()
            label = f"{title} — {artist}"
            labels[label] = labels.get(label, 0) + 1
            entries.append((album, title, artist, label))
        used_labels: set[str] = set()
        for album, title, artist, label in entries:
            if labels[label] > 1:
                suffix = str(getattr(album, "region", "") or "").strip()
                if not suffix:
                    suffix = str(getattr(album, "id", "") or "")[:8]
                label = f"{label} · {suffix}"
                if label in used_labels:
                    label = f"{label} · {str(getattr(album, 'id', '') or '')[:8]}"
            used_labels.add(label)
            item = QStandardItem(label)
            item.setData(str(getattr(album, "id", "") or ""), Qt.UserRole)
            model.appendRow(item)
        self.find_album_button.setEnabled(bool(albums))
        if not albums:
            self.album_search.clear()
            self.album_search.hide()

    def _show_album_search(self) -> None:
        if self.chiasm_canvas is None or not self.chiasm_canvas.albums:
            return
        self.album_search.show()
        self.album_search.setFocus(Qt.ShortcutFocusReason)
        self.album_search.selectAll()

    def _submit_album_search(self) -> None:
        query = self.album_search.text().strip().casefold()
        if not query:
            return
        completer = self._album_search_completer
        current = str(completer.currentCompletion() or "")
        labels = [
            str(self._album_search_model.item(row).text())
            for row in range(self._album_search_model.rowCount())
        ]
        candidate = current if query in current.casefold() else next(
            (label for label in labels if query in label.casefold()),
            "",
        )
        if candidate:
            self._choose_album_search_result(candidate)
            return
        self._status(
            f'No album or artist found for “{self.album_search.text().strip()}”',
            3500,
        )

    def _choose_album_search_result(self, label: str) -> None:
        wanted = str(label or "")
        album_id = ""
        for row in range(self._album_search_model.rowCount()):
            item = self._album_search_model.item(row)
            if item is not None and item.text() == wanted:
                album_id = str(item.data(Qt.UserRole) or "")
                break
        if not album_id or self.chiasm_canvas is None:
            return
        if self.chiasm_canvas.reveal_album(album_id):
            self.album_search.clear()
            self.album_search.hide()
            self.chiasm_canvas.setFocus(Qt.ShortcutFocusReason)

    def _chiasm_artwork_requested(self, request: object) -> None:
        if not isinstance(request, dict) or self.chiasm_canvas is None:
            return
        try:
            generation = int(request.get("generation", -1))
        except (TypeError, ValueError):
            return
        album_ids = tuple(
            dict.fromkeys(
                str(album_id)
                for album_id in request.get("album_ids", ())
                if album_id
            )
        )[:24]
        if not album_ids:
            return
        tracks_by_album = {
            album_id: [
                dict(track)
                for track in self.chiasm_album_tracks.get(album_id, ())
            ]
            for album_id in album_ids
        }
        adapter = self.chiasm_adapter
        canvas = self.chiasm_canvas

        def load() -> dict[str, Any]:
            from chiasm.artwork import read_field_artwork

            paths = adapter.local_artwork_paths(
                tracks_by_album,
                album_ids,
                max_items=24,
            )
            images = {}
            for album_id, path in paths.items():
                try:
                    images[album_id] = read_field_artwork(path)
                except Exception:
                    images[album_id] = read_field_artwork("")
            return {
                "generation": generation,
                "album_ids": album_ids,
                "images": images,
            }

        self._run_async(
            load,
            canvas.set_artwork_batch,
            priority="visible",
            task_name="chiasm-local-artwork",
        )


def create_chiasm_feature(host: Any) -> ChiasmFeature:
    """Connect shell services and signals while keeping feature state local."""
    feature = ChiasmFeature(
        host.providers,
        host.state,
        local_intelligence=lambda: host.local_intelligence,
        metadata=lambda: host.metadata,
        run_async=host._run_async,
        player_status=host.player.status,
        current_track=host.playback_feature.current_track,
        page_titles=host.page_titles,
        parent=host,
    )
    host.playback_feature.playPauseRequested.connect(
        lambda: feature.handle_arc_play_pause() or host.player.play_pause()
    )
    feature.playPauseRequested.connect(host.playback_feature.playPauseRequested.emit)
    feature.nextRequested.connect(host.playback_feature.nextRequested.emit)
    feature.replaceQueueAndPlayRequested.connect(host.player.replace_queue_and_play)
    feature.replaceUpcomingRequested.connect(host.player.replace_upcoming)
    feature.setPlayingRequested.connect(host.player.set_playing)
    feature.statusMessageRequested.connect(
        lambda message, timeout: (
            feature.chiasm_canvas.show_notice(message, timeout)
            if feature.chiasm_canvas is not None
            else host.statusBar().showMessage(message, timeout)
        )
    )
    feature.interactionMeasured.connect(host.responsiveness.record_interaction)
    add_folder_handler = getattr(host, "_choose_music_folder", None)
    if callable(add_folder_handler):
        feature.addMusicFolderRequested.connect(add_folder_handler)
    host.player.trackChanged.connect(feature.on_track_changed)
    host.player.playingChanged.connect(feature.on_playing_changed)
    host.player.positionChanged.connect(feature.on_position_changed)
    host.pages["chiasm"] = feature.page
    host.stack.addWidget(feature.page)
    return feature


def choose_music_folder(host: Any) -> None:
    """Add a local folder through Chiasm's in-field first-use control."""
    folder = QFileDialog.getExistingDirectory(host, "Choose a music folder")
    if not folder:
        return
    roots = host.providers.local_roots()
    path = Path(folder)
    if path not in roots:
        roots.append(path)
    host.providers.configure_local_roots(roots)
    came_from_home = host.current_page == "home"
    host._start_local_scan("folder added")
    if came_from_home:
        host.open_page("library")


def enter_chiasm_mode(host: Any) -> None:
    """Make the spatial field the only visible application surface."""
    from PySide6.QtGui import QAction, QShortcut

    host.open_page("chiasm")
    host.navigation.ensure_lazy_page_built("chiasm")
    page = host.chiasm_feature.page
    host.stack.removeWidget(page)
    inherited_shell = host.takeCentralWidget()
    host._inherited_shell_widget = inherited_shell
    if inherited_shell is not None:
        inherited_shell.hide()
    host.menuBar().hide()
    for action in host.findChildren(QAction):
        action.setEnabled(False)
    for shortcut in host.findChildren(QShortcut):
        shortcut.setEnabled(False)
    host.setCentralWidget(page)
    page.show()
    host.setWindowTitle("Chiasm")
    host.statusBar().hide()
    host.resize(1440, 900)
