from __future__ import annotations

import html
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .lyrics_state import LyricsDocument, build_lyrics_document, lyrics_have_content
from .metadata import RichMetadataService, track_key
from .ux_components import FeaturePresenceBar


class _MetadataSignals(QObject):
    stage = Signal(str, str, object)


def _escape(value: Any) -> str:
    return html.escape(str(value or ""))


class RichNowPlayingWidget(QWidget):
    knowledgeChanged = Signal(object, object)
    accentChanged = Signal(object)
    paletteChanged = Signal(object)
    artworkChanged = Signal(str)
    lyricsChanged = Signal(object)
    lyricsStateChanged = Signal(object)
    lyricsFullscreenRequested = Signal()
    lyricsSeekRequested = Signal(int)
    lyricsTranslationRequested = Signal(object)
    lyricsPluginRequested = Signal()
    contextPluginRequested = Signal()
    onlineLyricsPreferenceChanged = Signal(bool)

    """Progressively enriched Now Playing view.

    Identity is deliberately emitted first. Artwork, artist data, credits,
    discography and album thumbnails are independent follow-up stages so slow
    network enrichment never leaves the whole page looking unidentified.
    """

    def __init__(
        self,
        metadata: RichMetadataService,
        parent=None,
        *,
        auto_online_lyrics: bool = False,
    ):
        super().__init__(parent)
        self.metadata = metadata
        self._accent_color = QColor("#7eb4ff")
        self._palette_colors = self._fallback_palette(self._accent_color)
        self.track: dict[str, Any] = {}
        self.bundle: dict[str, Any] = {}
        self._lyric_index = -2
        self._lyrics_document = LyricsDocument.empty()
        self._current_lyrics: dict[str, Any] = {}
        self._local_lyrics: dict[str, Any] = {}
        self._online_lyrics: dict[str, Any] = {}
        self._active_lyrics_source = ""
        self._identity: dict[str, Any] = {}
        self._album_art_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._artist_display_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._pending: set[str] = set()
        self._context_started = False
        self._auto_online_lyrics = bool(auto_online_lyrics)
        self._online_lyrics_attempted = False
        self._signals = _MetadataSignals(self)
        self._signals.stage.connect(self._stage_loaded)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 8, 0, 0); outer.setSpacing(16)
        hero = QHBoxLayout(); hero.setSpacing(24); outer.addLayout(hero)
        self.art = QLabel("♫"); self.art.setAlignment(Qt.AlignCenter); self.art.setFixedSize(350, 350)
        self.art.setStyleSheet("background:#181b20;border:1px solid #303640;border-radius:18px;font-size:90px;color:#596270")
        hero.addWidget(self.art, 0, Qt.AlignTop)
        right = QVBoxLayout(); right.setSpacing(8); hero.addLayout(right, 1)
        self.title = QLabel("Nothing playing"); self.title.setWordWrap(True); self.title.setStyleSheet("font-size:34px;font-weight:750")
        self.artist = QLabel(""); self.artist.setWordWrap(True); self.artist.setStyleSheet("font-size:21px;color:#c8ccd2")
        self.album = QLabel(""); self.album.setWordWrap(True); self.album.setStyleSheet("font-size:15px;color:#aab0ba")
        self.facts = QLabel(""); self.facts.setWordWrap(True); self.facts.setStyleSheet("color:#8f96a1")
        self.progress = QLabel(""); self.progress.setWordWrap(True); self.progress.setStyleSheet("color:#7eb4ff;font-size:12px")
        self.links = QLabel(""); self.links.setOpenExternalLinks(True); self.links.setWordWrap(True)
        self.artist_photo_thumb = QLabel(""); self.artist_photo_thumb.setAlignment(Qt.AlignCenter); self.artist_photo_thumb.setFixedSize(160, 160)
        self.artist_photo_thumb.setStyleSheet("background:#15181d;border:1px solid #303640;border-radius:16px;color:#808894")
        self.artist_photo_credit = QLabel(""); self.artist_photo_credit.setOpenExternalLinks(True); self.artist_photo_credit.setWordWrap(True)
        self.artist_photo_credit.setMaximumWidth(330); self.artist_photo_credit.setStyleSheet("color:#8f96a1;font-size:10px")
        right.addWidget(self.title); right.addWidget(self.artist); right.addWidget(self.album); right.addWidget(self.facts)
        right.addWidget(self.progress); right.addWidget(self.links); right.addWidget(self.artist_photo_thumb, 0, Qt.AlignLeft); right.addWidget(self.artist_photo_credit); right.addStretch(1)
        self.art_source = QLabel(""); self.art_source.setWordWrap(True); self.art_source.setStyleSheet("color:#777f8a;font-size:11px"); right.addWidget(self.art_source)

        self.tabs = QTabWidget(); outer.addWidget(self.tabs, 1)

        self.lyrics_page=QWidget()
        lyrics_layout=QVBoxLayout(self.lyrics_page)
        lyrics_layout.setContentsMargins(0,8,0,0)
        lyrics_layout.setSpacing(9)

        self.lyrics_toolbar=QFrame()
        self.lyrics_toolbar.setObjectName("nativeLyricsToolbar")
        self.lyrics_toolbar.setStyleSheet(
            "QFrame#nativeLyricsToolbar{background:#0f1822;border:1px solid #26394e;"
            "border-radius:10px;}"
            "QLabel#lyricsToolbarLabel{color:#8191a5;font-size:10px;font-weight:700;}"
            "QLabel#lyricsStateBadge{background:#182a3d;border:1px solid #31516f;"
            "border-radius:8px;padding:3px 7px;color:#b9d5f1;font-size:9px;font-weight:700;}"
        )
        toolbar=QHBoxLayout(self.lyrics_toolbar)
        toolbar.setContentsMargins(11,8,11,8)
        toolbar.setSpacing(7)

        source_label=QLabel("SOURCE")
        source_label.setObjectName("lyricsToolbarLabel")
        toolbar.addWidget(source_label)

        self.lyrics_source_picker=QComboBox()
        self.lyrics_source_picker.setObjectName("lyricsSourcePicker")
        self.lyrics_source_picker.setMinimumWidth(190)
        self.lyrics_source_picker.setMaximumWidth(310)
        self.lyrics_source_picker.currentIndexChanged.connect(
            self._lyrics_source_selected
        )
        self.lyrics_source_picker.hide()
        toolbar.addWidget(self.lyrics_source_picker)

        self.lyrics_state_badge=QLabel("")
        self.lyrics_state_badge.setObjectName("lyricsStateBadge")
        self.lyrics_state_badge.hide()
        toolbar.addWidget(self.lyrics_state_badge)

        self.lyrics_search=QLineEdit()
        self.lyrics_search.setPlaceholderText("Search lyrics")
        self.lyrics_search.setClearButtonEnabled(True)
        self.lyrics_search.setMaximumWidth(180)
        self.lyrics_search.setToolTip("Type text and press Enter to find the next matching lyric.")
        self.lyrics_search.returnPressed.connect(self._find_lyrics_text)
        toolbar.addWidget(self.lyrics_search)
        toolbar.addStretch(1)

        self.online_lyrics_button=QPushButton("Refresh lyrics")
        self.online_lyrics_button.setObjectName("primaryButton")
        self.online_lyrics_button.clicked.connect(self._refresh_lyrics_native)
        toolbar.addWidget(self.online_lyrics_button)

        self.fullscreen_lyrics_button=QPushButton("Full screen")
        self.fullscreen_lyrics_button.setEnabled(False)
        self.fullscreen_lyrics_button.clicked.connect(self._show_fullscreen_lyrics)
        toolbar.addWidget(self.fullscreen_lyrics_button)

        self.translate_lyrics_button=QPushButton("Translate")
        self.translate_lyrics_button.setEnabled(False)
        self.translate_lyrics_button.clicked.connect(self._request_lyrics_translation)
        toolbar.addWidget(self.translate_lyrics_button)

        self.more_lyrics_button=QPushButton("More")
        self.more_lyrics_button.setObjectName("quietButton")
        self.lyrics_more_menu=QMenu(self.more_lyrics_button)
        self.edit_lyrics_action=self.lyrics_more_menu.addAction("Edit saved lyrics…")
        self.edit_lyrics_action.setEnabled(False)
        self.edit_lyrics_action.triggered.connect(
            lambda _checked=False:self._edit_saved_lyrics()
        )
        self.import_lyrics_action=self.lyrics_more_menu.addAction("Add lyrics file…")
        self.import_lyrics_action.triggered.connect(
            lambda _checked=False:self._import_lyrics_file()
        )
        self.paste_lyrics_action=self.lyrics_more_menu.addAction("Paste lyrics…")
        self.paste_lyrics_action.triggered.connect(
            lambda _checked=False:self._paste_lyrics()
        )
        self.lyrics_more_menu.addSeparator()
        self.auto_online_lyrics_action=self.lyrics_more_menu.addAction("Auto-find online")
        self.auto_online_lyrics_action.setCheckable(True)
        self.auto_online_lyrics_action.setChecked(self._auto_online_lyrics)
        self.manage_lyrics_sources_action=self.lyrics_more_menu.addAction(
            "Manage lyric sources…"
        )
        self.manage_lyrics_sources_action.triggered.connect(
            lambda _checked=False:self.lyricsPluginRequested.emit()
        )
        self.more_lyrics_button.setMenu(self.lyrics_more_menu)
        toolbar.addWidget(self.more_lyrics_button)
        lyrics_layout.addWidget(self.lyrics_toolbar)

        # Compatibility controls remain as hidden stateful helpers for existing
        # tests/integrations; listener-facing actions live in the native menu.
        self.edit_lyrics_button=QPushButton("Edit saved…")
        self.edit_lyrics_button.hide()
        self.import_lyrics_button=QPushButton("Add file…")
        self.import_lyrics_button.hide()
        self.paste_lyrics_button=QPushButton("Paste…")
        self.paste_lyrics_button.hide()
        self.find_lyrics_plugin_button=QPushButton("Manage lyric sources…")
        self.find_lyrics_plugin_button.hide()
        self.edit_lyrics_button.clicked.connect(self._edit_saved_lyrics)
        self.import_lyrics_button.clicked.connect(self._import_lyrics_file)
        self.paste_lyrics_button.clicked.connect(self._paste_lyrics)
        self.find_lyrics_plugin_button.clicked.connect(self.lyricsPluginRequested)

        self.auto_online_lyrics=QCheckBox("Auto-find online")
        self.auto_online_lyrics.setChecked(self._auto_online_lyrics)
        self.auto_online_lyrics.hide()
        self.auto_online_lyrics.toggled.connect(self._online_lyrics_pref_changed)
        self.auto_online_lyrics.toggled.connect(
            self.auto_online_lyrics_action.setChecked
        )
        self.auto_online_lyrics_action.toggled.connect(
            self.auto_online_lyrics.setChecked
        )

        self.fullscreen_lyrics_button.setToolTip(
            "<b>Lyric Flow</b><br>Open the immersive music-reactive lyric presentation. "
            "It uses the same lyrics and timing as this reader."
        )
        self.translate_lyrics_button.setToolTip(
            "<b>Translate lyrics</b><br>Explicitly send the currently displayed lyric text "
            "to your configured LLM for a temporary translation. Nothing is sent automatically."
        )
        self.online_lyrics_button.setToolTip(
            "<b>Refresh lyrics</b><br>Re-check local, embedded and installed lyric sources first; "
            "if none match, Melodex can fall back to the on-demand LRCLIB lookup."
        )

        self.lyrics_source=QLabel("")
        self.lyrics_source.setOpenExternalLinks(True)
        self.lyrics_source.setWordWrap(True)
        self.lyrics_source.setStyleSheet("color:#7f90a5;font-size:10px;padding:0 3px")
        lyrics_layout.addWidget(self.lyrics_source)

        self.lyrics = QTextBrowser()
        self.lyrics.setObjectName("nativeLyricsView")
        self.lyrics.setOpenExternalLinks(False)
        self.lyrics.setOpenLinks(False)
        self.lyrics.anchorClicked.connect(self._lyrics_anchor_clicked)
        self.lyrics.setStyleSheet(
            "QTextBrowser#nativeLyricsView{background:#101923;color:#edf3fa;"
            "border:1px solid #30465e;border-radius:11px;padding:20px;"
            "selection-background-color:#315f8f;selection-color:#ffffff;}"
        )
        # QTextDocument does not consistently resolve CSS `inherit` for links;
        # set a document default as well as explicit per-line colours below.
        self.lyrics.document().setDefaultStyleSheet(
            "body, p, div { color: #edf3fa; } a { color: #edf3fa; }"
        )
        lyrics_layout.addWidget(self.lyrics,1)

        self.artist_info = QTextBrowser(); self.releases = QTextBrowser(); self.credits = QTextBrowser(); self.info = QTextBrowser()
        for browser in (self.artist_info, self.releases, self.credits, self.info):
            browser.setOpenExternalLinks(True)

        self.context_page=QWidget()
        context_layout=QVBoxLayout(self.context_page)
        context_layout.setContentsMargins(0,8,0,0)
        context_layout.setSpacing(8)
        self.context_plugin_presence=FeaturePresenceBar(
            "Context helpers",
            baseline="Melodex core metadata still works without plugins",
            action_text="Add context plugin…",
        )
        self.context_plugin_presence.actionRequested.connect(self.contextPluginRequested)
        context_layout.addWidget(self.context_plugin_presence)
        self.context=QTextBrowser()
        self.context.setOpenExternalLinks(True)
        context_layout.addWidget(self.context,1)

        self.tabs.addTab(self.lyrics_page, "Lyrics")
        self.tabs.addTab(self.artist_info, "Artist")
        self.tabs.addTab(self.releases, "Releases")
        self.tabs.addTab(self.credits, "Credits")
        self.tabs.addTab(self.context_page, "Context")
        self.tabs.addTab(self.info, "Info")
        self._empty_tabs()

    def set_plugin_presence(
        self,
        *,
        lyrics: list[str] | tuple[str, ...] = (),
        context: list[str] | tuple[str, ...] = (),
    ) -> None:
        # Lyrics extensions participate automatically in the native lyrics
        # pipeline; only Context retains a visible helper strip.
        self.context_plugin_presence.set_items(list(context))

    def _empty_tabs(self) -> None:
        self.lyrics_source.setText("Checking saved, embedded and installed lyric sources…")
        self.lyrics.setHtml(
            self._lyrics_message_html(
                "Looking for lyrics…",
                "Melodex is checking saved lyrics, common .lrc/.txt sidecars, "
                "embedded tags and installed lyric sources.",
            )
        )
        self.artist_info.setHtml("<p style='color:#9097a2'>Artist information will load after MusicBrainz identifies the track.</p>")
        self.releases.setHtml("<p style='color:#9097a2'>Release history will load independently after the artist is identified.</p>")
        self.credits.setHtml("<p style='color:#9097a2'>Recording/work credits will load independently after the track is identified.</p>")
        self.context.setHtml("<p style='color:#9097a2'>Context plugins can add liner notes, musical connections, community listening data and other sourced cards here.</p>")
        self.info.setHtml("<p style='color:#9097a2'>Identifying this track with MusicBrainz…</p>")

    # ---------------------------- staged loading
    def set_track(self, track: dict[str, Any]) -> None:
        self.track = dict(track or {})
        request_track = dict(self.track)
        self.bundle = {}
        self._lyric_index = -2
        self._lyrics_document = LyricsDocument.empty()
        self._current_lyrics: dict[str, Any] = {}
        self._local_lyrics = {}
        self._online_lyrics = {}
        self._active_lyrics_source = ""
        self._identity = {}
        self._pending = {"identity"}
        self._context_started = False
        self._online_lyrics_attempted = False
        self.lyricsStateChanged.emit(self._lyrics_document)
        self.lyricsChanged.emit({})
        if hasattr(self,"online_lyrics_button"):
            self.online_lyrics_button.setEnabled(True)
            self.online_lyrics_button.setText("Refresh lyrics")
        self.title.setText(str(self.track.get("title") or "Unknown track"))
        self.artist.setText(str(self.track.get("artist") or "Unknown artist"))
        self.album.setText(str(self.track.get("album") or ""))
        provider = str(self.track.get("provider_id") or self.track.get("source") or "")
        duration = float(self.track.get("duration") or 0)
        duration_text = f"{int(duration)//60}:{int(duration)%60:02d}" if duration > 0 else ""
        self.facts.setText(" · ".join(x for x in (provider, duration_text) if x))
        self.progress.setText("Identifying track and checking capability extensions…")
        self.links.clear(); self.art_source.clear(); self.artist_photo_credit.clear(); self._set_art(""); self._set_artist_photo(""); self._empty_tabs()
        self._restore_related_cache(request_track)
        key = track_key(request_track)
        if not key:
            self.progress.setText("Not enough metadata to identify this track")
            return

        def identify_work() -> None:
            try:
                payload = self.metadata.enrich_identity(request_track)
            except Exception as exc:
                payload = {"track_key": key, "track": request_track, "identity": {}, "lyrics": {}, "errors": [str(exc)]}
            self._signals.stage.emit(key, "identity", payload)

        threading.Thread(target=identify_work, daemon=True).start()

    @staticmethod
    def _normal_cache_part(value: object) -> str:
        return " ".join(str(value or "").casefold().split())

    @classmethod
    def _album_cache_key(cls, track: dict[str, Any]) -> str:
        artist = cls._normal_cache_part(track.get("artist"))
        album = cls._normal_cache_part(track.get("album"))
        return f"{artist}|{album}" if artist and album else ""

    @classmethod
    def _artist_cache_key(cls, track: dict[str, Any]) -> str:
        artist = cls._normal_cache_part(track.get("artist"))
        return artist

    @staticmethod
    def _bounded_cache_put(cache: OrderedDict[str, dict[str, Any]], key: str, value: dict[str, Any]) -> None:
        if not key:
            return
        cache[key] = dict(value)
        cache.move_to_end(key)
        while len(cache) > 64:
            cache.popitem(last=False)

    def _restore_related_cache(self, track: dict[str, Any]) -> None:
        album_key = self._album_cache_key(track)
        artwork = self._album_art_cache.get(album_key) if album_key else None
        if artwork:
            self.bundle["artwork"] = dict(artwork)
            self._apply_artwork(dict(artwork))

        artist_key = self._artist_cache_key(track)
        cached = self._artist_display_cache.get(artist_key) if artist_key else None
        if not cached:
            return
        artist = dict(cached.get("artist") or {})
        photo = dict(cached.get("artist_photo") or {})
        if artist:
            self.bundle["artist"] = artist
            self.bundle["artist_photo"] = photo
            self._apply_artist(artist)
            self._set_artist_photo(str(photo.get("path") or ""))
            self._set_artist_photo_credit(photo)
            self.artist_info.setHtml(self._artist_html(artist, photo))

    def _cache_artist_display(self) -> None:
        key = self._artist_cache_key(self.track)
        if not key:
            return
        previous = self._artist_display_cache.get(key, {})
        artist = self.bundle.get("artist") or previous.get("artist") or {}
        photo = self.bundle.get("artist_photo") or previous.get("artist_photo") or {}
        if artist:
            self._bounded_cache_put(
                self._artist_display_cache,
                key,
                {"artist": dict(artist), "artist_photo": dict(photo)},
            )

    def _run_stage(self, key: str, name: str, fn: Callable[[], object]) -> None:
        self._pending.add(name)

        def work() -> None:
            try:
                payload = fn()
            except Exception as exc:
                payload = {"errors": [str(exc)]}
            self._signals.stage.emit(key, name, payload)

        threading.Thread(target=work, daemon=True).start()

    def _stage_loaded(self, key: str, stage: str, payload: object) -> None:
        if key != track_key(self.track) or not isinstance(payload, dict):
            return
        self._pending.discard(stage)
        errors = [str(x) for x in list(payload.get("errors") or []) if x]
        if errors:
            self.bundle.setdefault("errors", []).extend(errors)

        if stage == "identity":
            self._apply_identity(payload)
            identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
            self._identity = dict(identity)
            request_track = dict(self.track)
            ident = dict(identity)
            # Artwork capability extensions can work from provider identity/hints
            # even when no MusicBrainz match exists.
            self._run_stage(
                key,
                "artwork",
                lambda: self.metadata.enrich_artwork(request_track, ident),
            )
            if identity.get("artist_mbid"):
                self._run_stage(
                    key, "artist", lambda: self.metadata.enrich_artist(ident)
                )
                self._run_stage(
                    key,
                    "discography",
                    lambda: self.metadata.enrich_discography(ident),
                )
            if identity.get("recording_mbid"):
                self._run_stage(
                    key, "credits", lambda: self.metadata.enrich_credits(ident)
                )
            self._maybe_start_context(key)
            if not identity.get("recording_mbid"):
                self.progress.setText(
                    "No MusicBrainz recording match — extension/local enrichment still active"
                )
            self._emit_knowledge()
            self._update_progress()
            return

        if stage == "lyrics refresh":
            refreshed=(
                payload.get("lyrics")
                if isinstance(payload.get("lyrics"),dict)
                else {}
            )
            if self._lyrics_has_content(refreshed):
                self._local_lyrics=dict(refreshed)
                self._active_lyrics_source="local"
                self.bundle["lyrics"]=dict(refreshed)
                self._apply_lyrics(refreshed)
                self.online_lyrics_button.setEnabled(True)
                self.online_lyrics_button.setText("Refresh lyrics")
            else:
                self.lyrics_source.setText(
                    "No saved or installed source matched · checking online…"
                )
                self._find_lyrics_online(force=True)
            self._refresh_info()
            self._update_progress()
            return

        if stage == "community lyrics":
            lyrics=payload.get("lyrics") if isinstance(payload.get("lyrics"),dict) else {}
            self._online_lyrics=dict(lyrics)
            if self._lyrics_has_content(lyrics):
                self.bundle["lyrics"]=dict(lyrics)
                self._active_lyrics_source="online"
                self._apply_lyrics(lyrics)
            elif self._lyrics_has_content(self._local_lyrics):
                self.bundle["lyrics"]=dict(self._local_lyrics)
                self._active_lyrics_source="local"
                self._apply_lyrics(self._local_lyrics)
            else:
                self.bundle["lyrics"]=dict(lyrics)
                self._active_lyrics_source="online"
                self._apply_lyrics(lyrics)
            self.online_lyrics_button.setEnabled(True)
            status=str(lyrics.get("status") or "")
            self.online_lyrics_button.setText(
                "Try again"
                if status in {"not_found","error","missing_metadata"}
                else "Refresh lyrics"
            )

        elif stage == "artwork":
            artwork = payload.get("artwork") if isinstance(payload.get("artwork"), dict) else {}
            self.bundle["artwork"] = artwork
            self._bounded_cache_put(
                self._album_art_cache,
                self._album_cache_key(self.track),
                artwork,
            )
            self._apply_artwork(artwork)

        elif stage == "artist":
            artist = payload.get("artist") if isinstance(payload.get("artist"), dict) else {}
            self.bundle["artist"] = artist
            qid = str(artist.get("wikidata_qid") or "")
            if qid:
                self._identity["wikidata_id"] = qid
            self._apply_artist(artist)
            self._cache_artist_display()
            if artist:
                self._run_stage(key, "artist photo", lambda: self.metadata.enrich_artist_photo(artist))

        elif stage == "artist photo":
            photo = payload.get("artist_photo") if isinstance(payload.get("artist_photo"), dict) else {}
            self.bundle["artist_photo"] = photo
            self._set_artist_photo(str(photo.get("path") or ""))
            self._set_artist_photo_credit(photo)
            artist = self.bundle.get("artist") if isinstance(self.bundle.get("artist"), dict) else {}
            self.artist_info.setHtml(self._artist_html(artist, photo))
            self._cache_artist_display()

        elif stage == "credits":
            credits = [x for x in list(payload.get("credits") or []) if isinstance(x, dict)]
            self.bundle["credits"] = credits
            self.credits.setHtml(self._credits_html(credits))

        elif stage == "context":
            cards = [x for x in list(payload.get("cards") or []) if isinstance(x, dict)]
            self.bundle["context"] = cards
            self.context.setHtml(self._context_html(cards))

        elif stage == "discography":
            releases = [x for x in list(payload.get("discography") or []) if isinstance(x, dict)]
            self.bundle["discography"] = releases
            self.releases.setHtml(self._discography_html(releases))
            if releases:
                self._run_stage(key, "release covers", lambda: {"discography": self.metadata.hydrate_discography_covers(releases, 8), "errors": []})

        elif stage == "release covers":
            releases = [x for x in list(payload.get("discography") or []) if isinstance(x, dict)]
            self.bundle["discography"] = releases
            self.releases.setHtml(self._discography_html(releases))

        self._maybe_start_context(key)
        if stage in {"artist", "credits", "context"}:
            self._emit_knowledge()
        self._refresh_info()
        self._update_progress()

    def _emit_knowledge(self) -> None:
        if not self.track:
            return
        payload: dict[str, Any] = {}
        for key in ("identity", "artist", "credits", "context"):
            if key in self.bundle:
                value = self.bundle.get(key)
                if isinstance(value, dict):
                    payload[key] = dict(value)
                elif isinstance(value, list):
                    payload[key] = [
                        dict(row) for row in value if isinstance(row, dict)
                    ]
        if payload:
            self.knowledgeChanged.emit(dict(self.track), payload)

    def _maybe_start_context(self, key: str) -> None:
        if self._context_started or not self._identity:
            return
        if self._identity.get("artist_mbid") and "artist" in self._pending:
            return
        if self._identity.get("recording_mbid") and "credits" in self._pending:
            return
        self._context_started = True
        request_track = dict(self.track)
        identity = dict(self._identity)
        self._run_stage(
            key,
            "context",
            lambda: self.metadata.enrich_context(request_track, identity),
        )

    def _apply_identity(self, payload: dict[str, Any]) -> None:
        identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
        lyrics = payload.get("lyrics") if isinstance(payload.get("lyrics"), dict) else {}
        self.bundle["identity"] = dict(identity)
        self.bundle["lyrics"] = dict(lyrics)
        self._local_lyrics = dict(lyrics)
        self._active_lyrics_source = "local" if self._lyrics_has_content(lyrics) else ""
        if identity.get("title"):
            self.title.setText(str(identity.get("title")))
        if identity.get("artist"):
            self.artist.setText(str(identity.get("artist")))
        album = str(identity.get("album") or self.track.get("album") or "")
        date = str(identity.get("date") or "")
        self.album.setText(" · ".join(x for x in (album, date[:4] if date else "") if x))
        self._apply_lyrics(lyrics)
        if (
            not str(lyrics.get("text") or "").strip()
            and not list(lyrics.get("synced") or [])
            and self.auto_online_lyrics.isChecked()
            and not self._online_lyrics_attempted
        ):
            self._find_lyrics_online(force=False)
        self._apply_musicbrainz_links(identity)
        self._refresh_info()

    def _apply_lyrics(self, lyrics: dict[str, Any]) -> None:
        self._current_lyrics = dict(lyrics)
        self._lyrics_document = build_lyrics_document(lyrics)
        document = self._lyrics_document
        lyric_text = document.text
        lyric_source = document.source
        provenance = document.provenance_dict
        instrumental = document.instrumental
        status = document.status
        error = document.error
        match = document.match_dict
        if instrumental and not lyric_text and not self.synced:
            self.lyrics.setHtml(
                self._lyrics_message_html(
                    "Instrumental track",
                    "The current lyric source identifies this recording as instrumental.",
                )
            )
        elif self.synced:
            self._lyric_index = -2
            self._render_synced(-1)
        elif lyric_text:
            self.lyrics.setHtml(self._plain_lyrics_html(lyric_text))
        elif status=="not_found":
            self.lyrics.setHtml(
                self._lyrics_message_html(
                    "No confident lyric match",
                    "Melodex checked the available lyric sources but did not find a result "
                    "close enough to this artist, title and recording.",
                    "Try again, correct the track metadata, or add your own lyrics from More.",
                )
            )
        elif status=="missing_metadata":
            self.lyrics.setHtml(
                self._lyrics_message_html(
                    "Artist and title needed",
                    "Lyrics lookup needs usable artist and track-title metadata.",
                    "Edit the track metadata, then refresh lyrics.",
                )
            )
        elif status=="error":
            self.lyrics.setHtml(
                self._lyrics_message_html(
                    "Lyrics lookup could not connect",
                    "A lyric source did not complete this request. Your local music and "
                    "saved lyrics are unaffected.",
                    "Choose Try again when you want to retry.",
                )
            )
        else:
            self.lyrics.setHtml(
                self._lyrics_message_html(
                    "No lyrics yet",
                    "Melodex checked your saved lyrics, sidecars, embedded tags and "
                    "installed lyric sources.",
                    "Choose Refresh lyrics to check again, or use More to add your own lyrics.",
                )
            )

        if lyric_text or self.synced or instrumental:
            source_label=_escape(
                lyric_source or ("Instrumental" if instrumental else "Lyrics available")
            )
            source_url=str(provenance.get("source_url") or "").strip()
            if source_url:
                source_label += f' · <a href="{_escape(source_url)}">source</a>'
            if lyric_source.startswith("LRCLIB"):
                source_label += " · on demand · not saved"
                method=str(match.get("method") or "")
                if method=="cleaned_exact":
                    source_label += " · matched after cleaning metadata"
                elif method=="structured_search":
                    source_label += " · matched by search"
                if document.cache=="memory":
                    source_label += " · reused this session"
            if self.synced:
                source_label += " · synchronized"
            self.lyrics_source.setText(source_label)
        elif status=="not_found":
            self.lyrics_source.setText("LRCLIB checked · no confident match")
        elif status=="missing_metadata":
            self.lyrics_source.setText("Online lookup needs artist + title metadata")
        elif status=="error":
            self.lyrics_source.setText(
                "Lyrics are unavailable right now"
                + (f" · {error[:120]}" if error else "")
            )
        else:
            self.lyrics_source.setText("No lyrics found yet")

        self._refresh_lyrics_source_picker()
        editable=self._current_lyrics_editable()
        self.edit_lyrics_button.setEnabled(editable)
        self.edit_lyrics_action.setEnabled(editable)
        self.translate_lyrics_button.setEnabled(bool(lyric_text.strip()))
        self.fullscreen_lyrics_button.setEnabled(
            bool(lyric_text or self.synced or instrumental)
        )
        states=[]
        if self.synced:
            states.append("Synced")
        if self._active_lyrics_source=="online" or lyric_source.startswith("LRCLIB"):
            states.append("Online")
        elif lyric_text or self.synced:
            states.append("Saved" if editable else "Source")
        if instrumental:
            states=["Instrumental"]
        self.lyrics_state_badge.setText(" · ".join(states))
        self.lyrics_state_badge.setVisible(bool(states))
        self.lyricsStateChanged.emit(document)
        self.lyricsChanged.emit({
            "text": lyric_text,
            "synced": [dict(row) for row in self.synced],
            "source": lyric_source,
        })

    def _online_lyrics_pref_changed(self, enabled: bool) -> None:
        self._auto_online_lyrics=bool(enabled)
        self.onlineLyricsPreferenceChanged.emit(bool(enabled))
        if (
            enabled
            and self.track
            and not self._online_lyrics_attempted
            and not str((self.bundle.get("lyrics") or {}).get("text") or "").strip()
            and not list((self.bundle.get("lyrics") or {}).get("synced") or [])
        ):
            self._find_lyrics_online(force=False)

    def _refresh_lyrics_native(self) -> None:
        """Refresh Melodex's full lyrics pipeline before any online fallback."""
        if not self.track or not track_key(self.track):
            QMessageBox.information(self,"Lyrics","Play or select a track first.")
            return
        if "lyrics refresh" in self._pending or "community lyrics" in self._pending:
            return
        self.online_lyrics_button.setEnabled(False)
        self.online_lyrics_button.setText("Refreshing…")
        self.lyrics_source.setText(
            "Re-checking saved, embedded and installed lyric sources…"
        )
        key=track_key(self.track)
        request_track=dict(self.track)
        self._run_stage(
            key,
            "lyrics refresh",
            lambda:self.metadata.enrich_identity(request_track),
        )

    def _find_lyrics_online(self, *, force: bool = True) -> None:
        if not self.track or not track_key(self.track):
            QMessageBox.information(self,"Lyrics","Play or select a track first.")
            return
        if "community lyrics" in self._pending:
            return
        self._online_lyrics_attempted=True
        self.online_lyrics_button.setEnabled(False)
        self.online_lyrics_button.setText("Looking…")
        self.lyrics_source.setText(
            "No saved or installed source matched · checking LRCLIB on demand…"
        )
        key=track_key(self.track)
        request_track=dict(self.track)
        self._run_stage(
            key,
            "community lyrics",
            lambda: {
                "lyrics":self.metadata.community_lyrics(request_track,force=force),
                "errors":[],
            },
        )

    @staticmethod
    def _lyrics_message_html(
        title: str,
        body: str,
        secondary: str = "",
    ) -> str:
        extra=(
            f"<p style='color:#74869b;font-size:13px;margin-top:14px'>{_escape(secondary)}</p>"
            if secondary else ""
        )
        return (
            "<div style='margin:24px;max-width:720px;color:#dfe8f3'>"
            f"<h3 style='color:#edf4fb;font-size:22px;margin:0 0 10px 0'>{_escape(title)}</h3>"
            f"<p style='color:#9fb0c3;font-size:15px;line-height:1.55'>{_escape(body)}</p>"
            f"{extra}</div>"
        )

    @staticmethod
    def _plain_lyrics_html(text: str, *, full_screen: bool = False) -> str:
        size=34 if full_screen else 24
        line_height=1.78 if full_screen else 1.62
        margin="26px auto" if full_screen else "8px 12px"
        width="900px" if full_screen else "760px"
        lines="<br>".join(_escape(text).splitlines())
        return (
            f"<div style='font-size:{size}px;line-height:{line_height};"
            f"max-width:{width};margin:{margin};color:#edf3fa;font-weight:500'>"
            f"{lines}</div>"
        )

    @staticmethod
    def _lyrics_has_content(lyrics: object) -> bool:
        return lyrics_have_content(lyrics)

    def _current_lyrics_editable(self) -> bool:
        document = self._lyrics_document
        if not document.has_content:
            return False
        if document.source.casefold().startswith("lrclib") or document.provenance_dict.get("source_extension_id"):
            return False
        return bool(document.user_added or document.path or self.track.get("local_path"))

    @staticmethod
    def _lyrics_editor_text(lyrics: dict[str, Any]) -> str:
        synced=[
            dict(row)
            for row in list((lyrics or {}).get("synced") or [])
            if isinstance(row,dict)
        ]
        if not synced:
            return str((lyrics or {}).get("text") or "")
        rows=[]
        for row in synced:
            total=max(0,int(row.get("time_ms") or 0))
            minutes=total//60000
            seconds=(total%60000)//1000
            hundredths=(total%1000)//10
            rows.append(
                f"[{minutes:02d}:{seconds:02d}.{hundredths:02d}]"
                + str(row.get("text") or "")
            )
        return "\n".join(rows)

    def _request_lyrics_translation(self) -> None:
        text = self._lyrics_document.searchable_text.strip()
        if not text:
            QMessageBox.information(
                self,
                "Translate lyrics",
                "There is no lyric text to translate.",
            )
            return
        self.lyricsTranslationRequested.emit({
            "text":text,
            "source":self._lyrics_document.source,
            "artist":str(self.track.get("artist") or ""),
            "title":str(self.track.get("title") or ""),
        })

    def _edit_saved_lyrics(self) -> None:
        if not self._current_lyrics_editable():
            QMessageBox.information(
                self,
                "Edit lyrics",
                "Only local or personal lyrics can be edited here. "
                "Temporary online/plugin lyrics are not persisted by Melodex.",
            )
            return
        initial=self._lyrics_editor_text(self._lyrics_document.as_payload())
        text,ok=QInputDialog.getMultiLineText(
            self,
            "Edit saved lyrics",
            "Edit plain lyrics or timestamped LRC text. "
            "Melodex saves a personal copy and does not change your audio file:",
            initial,
        )
        if not ok:
            return
        result=self.metadata.remember_lyrics_text(
            self.track,
            text,
            source="Edited lyrics",
        )
        if not result:
            QMessageBox.warning(
                self,
                "Could not save lyrics",
                "The edited lyrics were empty.",
            )
            return
        self.bundle["lyrics"]=dict(result)
        self._local_lyrics=dict(result)
        self._active_lyrics_source="local"
        self._apply_lyrics(result)

    def _refresh_lyrics_source_picker(self) -> None:
        options=[]
        if self._lyrics_has_content(self._local_lyrics):
            label=str(self._local_lyrics.get("source") or "Saved lyrics")
            options.append(("local",label))
        if self._lyrics_has_content(self._online_lyrics):
            label=str(self._online_lyrics.get("source") or "LRCLIB")
            options.append(("online",label))

        self.lyrics_source_picker.blockSignals(True)
        self.lyrics_source_picker.clear()
        for value,label in options:
            self.lyrics_source_picker.addItem(label,value)
        active=self._active_lyrics_source
        index=self.lyrics_source_picker.findData(active)
        if index >= 0:
            self.lyrics_source_picker.setCurrentIndex(index)
        self.lyrics_source_picker.setVisible(bool(options))
        self.lyrics_source_picker.blockSignals(False)

    def _lyrics_source_selected(self, _index: int) -> None:
        value=str(self.lyrics_source_picker.currentData() or "")
        if value=="local" and self._lyrics_has_content(self._local_lyrics):
            self._active_lyrics_source="local"
            self.bundle["lyrics"]=dict(self._local_lyrics)
            self._apply_lyrics(self._local_lyrics)
        elif value=="online" and self._lyrics_has_content(self._online_lyrics):
            self._active_lyrics_source="online"
            self.bundle["lyrics"]=dict(self._online_lyrics)
            self._apply_lyrics(self._online_lyrics)

    def _find_lyrics_text(self) -> None:
        term=str(self.lyrics_search.text() or "").strip()
        if not term:
            return
        if self.lyrics.find(term):
            return
        cursor=self.lyrics.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.lyrics.setTextCursor(cursor)
        self.lyrics.find(term)

    def _lyrics_anchor_clicked(self, url: QUrl) -> None:
        if str(url.scheme()).casefold()!="seek":
            return
        raw=str(url.path() or url.host() or "").strip("/")
        if not raw:
            raw=str(url.toString()).split(":",1)[-1]
        try:
            position=max(0,int(raw))
        except Exception:
            return
        self.lyricsSeekRequested.emit(position)

    def _show_fullscreen_lyrics(self) -> None:
        if not self._lyrics_document.has_content:
            QMessageBox.information(
                self,
                "Lyric Flow",
                "Lyrics are not available for this track yet.",
            )
            return
        self.lyricsFullscreenRequested.emit()

    def _import_lyrics_file(self) -> None:
        if not self.track or not track_key(self.track):
            QMessageBox.information(self,"Lyrics","Play or select a track first.")
            return
        path,_=QFileDialog.getOpenFileName(
            self,
            "Add lyrics for this track",
            "",
            "Lyrics (*.lrc *.txt);;LRC lyrics (*.lrc);;Text files (*.txt)",
        )
        if not path:
            return
        result=self.metadata.remember_lyrics_file(self.track,path)
        if not result:
            QMessageBox.warning(
                self,
                "Could not add lyrics",
                "Choose a readable .lrc or .txt file containing lyrics.",
            )
            return
        self.bundle["lyrics"]=dict(result)
        self._local_lyrics=dict(result)
        self._active_lyrics_source="local"
        self._apply_lyrics(result)

    def _paste_lyrics(self) -> None:
        if not self.track or not track_key(self.track):
            QMessageBox.information(self,"Lyrics","Play or select a track first.")
            return
        text,ok=QInputDialog.getMultiLineText(
            self,
            "Paste lyrics",
            "Paste plain lyrics or timestamped LRC text:",
            "",
        )
        if not ok or not str(text).strip():
            return
        result=self.metadata.remember_lyrics_text(
            self.track,
            text,
            source="Pasted lyrics",
        )
        if not result:
            QMessageBox.warning(self,"Could not save lyrics","The pasted text was empty.")
            return
        self.bundle["lyrics"]=dict(result)
        self._local_lyrics=dict(result)
        self._active_lyrics_source="local"
        self._apply_lyrics(result)

    def _apply_musicbrainz_links(self, identity: dict[str, Any]) -> None:
        links = []
        if identity.get("recording_mbid"):
            links.append(f'<a href="https://musicbrainz.org/recording/{_escape(identity.get("recording_mbid"))}">MusicBrainz recording</a>')
        if identity.get("artist_mbid"):
            links.append(f'<a href="https://musicbrainz.org/artist/{_escape(identity.get("artist_mbid"))}">artist</a>')
        if identity.get("release_mbid"):
            links.append(f'<a href="https://musicbrainz.org/release/{_escape(identity.get("release_mbid"))}">release</a>')
        self.links.setText(" · ".join(links))

    def _apply_artwork(self, artwork: dict[str, Any]) -> None:
        self._set_art(str(artwork.get("path") or ""))
        source = str(artwork.get("source") or "")
        self.art_source.setText(("Artwork: " + source) if source else "")

    def _apply_artist(self, artist: dict[str, Any]) -> None:
        facts = []
        if artist.get("type"):
            facts.append(str(artist.get("type")))
        place = str(artist.get("begin_area") or artist.get("area") or artist.get("country") or "")
        if place:
            facts.append(place)
        genres = [str(x) for x in list(artist.get("genres") or []) if x]
        if genres:
            facts.append(" · ".join(genres[:4]))
        if facts:
            self.facts.setText("   |   ".join(facts))
        self.artist_info.setHtml(self._artist_html(artist, self.bundle.get("artist_photo") if isinstance(self.bundle.get("artist_photo"), dict) else {}))

    def _update_progress(self) -> None:
        identity = self._identity
        if not identity.get("recording_mbid"):
            return
        score = float(identity.get("score") or 0.0)
        prefix = f"✓ MusicBrainz match {score:.0%}" if score else "✓ MusicBrainz match"
        if not self._pending:
            self.progress.setText(prefix + " · enrichment complete")
            return
        order = ["artwork", "artist", "credits", "context", "artist photo", "discography", "release covers"]
        names = [x for x in order if x in self._pending]
        pretty = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
        self.progress.setText(prefix + (f" · loading {pretty}" if pretty else ""))

    def _refresh_info(self) -> None:
        identity = self.bundle.get("identity") if isinstance(self.bundle.get("identity"), dict) else {}
        artwork = self.bundle.get("artwork") if isinstance(self.bundle.get("artwork"), dict) else {}
        photo = self.bundle.get("artist_photo") if isinstance(self.bundle.get("artist_photo"), dict) else {}
        self.info.setHtml(self._info_html(identity, artwork, photo, self.bundle.get("errors") or []))

    # ---------------------------- visuals / HTML
    def _set_artist_photo_credit(self, photo: dict[str, Any]) -> None:
        if not photo or not photo.get("path"):
            self.artist_photo_credit.clear()
            return
        attribution = _escape(photo.get("attribution") or "Wikimedia Commons")
        description_url = _escape(photo.get("description_url") or "")
        license_name = _escape(photo.get("license_name") or "")
        license_url = _escape(photo.get("license_url") or "")
        source = f'<a href="{description_url}">Commons file</a>' if description_url else "Wikimedia Commons"
        licence = f'<a href="{license_url}">{license_name}</a>' if license_url and license_name else license_name
        suffix = f" · {licence}" if licence and licence.casefold() not in attribution.casefold() else ""
        self.artist_photo_credit.setText(f"Photo: {attribution} · {source}{suffix}")

    def _set_artist_photo(self, path: str) -> None:
        if path and Path(path).exists():
            pix = QPixmap(path)
            if not pix.isNull():
                self.artist_photo_thumb.setText("")
                self.artist_photo_thumb.setPixmap(pix.scaled(self.artist_photo_thumb.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
                return
        self.artist_photo_thumb.setPixmap(QPixmap())
        self.artist_photo_thumb.setText("artist photo")

    @property
    def accent_color(self) -> QColor:
        return QColor(self._accent_color)

    @staticmethod
    def _fallback_palette(accent: QColor) -> tuple[str, ...]:
        hue = accent.hue() if accent.hue() >= 0 else 210
        return tuple(
            QColor.fromHsv((hue + offset) % 360, saturation, value).name()
            for offset, saturation, value in (
                (0, 175, 238), (38, 165, 232), (205, 150, 222),
                (300, 135, 208), (116, 145, 214), (260, 110, 238),
            )
        )

    def _set_art(self, path: str) -> None:
        if path and Path(path).exists():
            pix = QPixmap(path)
            if not pix.isNull():
                self.art.setText("")
                self.art.setPixmap(pix.scaled(self.art.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self._apply_accent(QImage(path))
                self.artworkChanged.emit(str(path))
                return
        self.art.setPixmap(QPixmap()); self.art.setText("♫")
        self.artworkChanged.emit("")
        self._accent_color = QColor("#7eb4ff")
        self._palette_colors = self._fallback_palette(self._accent_color)
        self.accentChanged.emit(QColor(self._accent_color))
        self.paletteChanged.emit(self._palette_colors)
        self.setStyleSheet("")

    def _apply_accent(self, image: QImage) -> None:
        if image.isNull():
            return
        small = image.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        r = g = b = count = 0
        buckets: dict[tuple[int, int, int], list[int]] = {}
        for y in range(small.height()):
            for x in range(small.width()):
                c = QColor(small.pixel(x, y)); mx, mn = max(c.red(), c.green(), c.blue()), min(c.red(), c.green(), c.blue())
                if mx < 28 or (mx - mn < 8 and mx > 220):
                    continue
                r += c.red(); g += c.green(); b += c.blue(); count += 1
                key = (c.red() // 32, c.green() // 32, c.blue() // 32)
                bucket = buckets.setdefault(key, [0, 0, 0, 0])
                bucket[0] += c.red(); bucket[1] += c.green(); bucket[2] += c.blue(); bucket[3] += 1
        if not count:
            return
        accent = QColor(r // count, g // count, b // count)
        if accent.lightness() < 80:
            accent = accent.lighter(155)
        if accent.lightness() > 200:
            accent = accent.darker(125)
        self._accent_color = QColor(accent)
        sampled: list[QColor] = []
        for bucket in sorted(buckets.values(), key=lambda value: value[3], reverse=True):
            color = QColor(bucket[0] // bucket[3], bucket[1] // bucket[3], bucket[2] // bucket[3])
            if color.lightness() < 70:
                color = color.lighter(150)
            if color.lightness() > 224:
                color = color.darker(132)
            if all(abs(color.hue() - seen.hue()) > 12 or color.saturation() < 35 for seen in sampled):
                sampled.append(color)
            if len(sampled) >= 5:
                break
        fallback = [QColor(value) for value in self._fallback_palette(accent)]
        sampled.append(QColor(accent))
        for color in fallback:
            if len(sampled) >= 6:
                break
            if all(color != existing for existing in sampled):
                sampled.append(color)
        self._palette_colors = tuple(color.name() for color in sampled[:6])
        self.accentChanged.emit(QColor(accent))
        self.paletteChanged.emit(self._palette_colors)
        dark = QColor(accent); dark = dark.darker(420)
        self.title.setStyleSheet(f"font-size:34px;font-weight:750;color:{accent.name()}")
        self.art.setStyleSheet(f"background:#181b20;border:2px solid {accent.name()};border-radius:18px")
        self.setStyleSheet(f"RichNowPlayingWidget{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {dark.name()},stop:0.48 #101114,stop:1 #101114);border-radius:14px}}")

    def _artist_html(self, artist: dict[str, Any], photo: dict[str, Any] | None = None) -> str:
        if not artist:
            return "<p style='color:#9097a2'>No artist information found.</p>"
        parts = [f"<h2>{_escape(artist.get('name'))}</h2>"]
        dis = str(artist.get("disambiguation") or "")
        if dis:
            parts.append(f"<p>{_escape(dis)}</p>")
        details = []
        if artist.get("type"):
            details.append(str(artist.get("type")))
        if artist.get("begin_area"):
            details.append("From " + str(artist.get("begin_area")))
        elif artist.get("area"):
            details.append(str(artist.get("area")))
        if artist.get("begin"):
            details.append("Active from " + str(artist.get("begin")))
        if details:
            parts.append(f"<p>{_escape(' · '.join(details))}</p>")
        genres = [str(x) for x in list(artist.get("genres") or []) if x]
        if genres:
            parts.append("<p><b>Genres / tags:</b> " + _escape(", ".join(genres)) + "</p>")
        photo = photo or {}
        if photo.get("path"):
            uri = Path(str(photo.get("path"))).resolve().as_uri()
            caption = _escape(photo.get("attribution") or photo.get("source") or "")
            description_url = _escape(photo.get("description_url") or "")
            license_name = _escape(photo.get("license_name") or "")
            license_url = _escape(photo.get("license_url") or "")
            parts.append(f'<p><img src="{uri}" width="220"></p>')
            credit_bits = [caption] if caption else []
            if description_url:
                credit_bits.append(f'<a href="{description_url}">Wikimedia Commons file</a>')
            if license_name:
                credit_bits.append(f'<a href="{license_url}">{license_name}</a>' if license_url else license_name)
            if credit_bits:
                parts.append("<p style='color:#9097a2'>Photo: " + " · ".join(credit_bits) + "</p>")
        members = [x for x in list(artist.get("members") or []) if isinstance(x, dict)]
        if members:
            parts.append("<h3>Members / membership</h3><ul>" + "".join(f"<li>{_escape(x.get('name'))} — {_escape(x.get('type'))}{' (former)' if x.get('ended') else ''}</li>" for x in members) + "</ul>")
        related = [x for x in list(artist.get("related") or []) if isinstance(x, dict)]
        if related:
            parts.append("<h3>Related artists / projects</h3><ul>" + "".join(f"<li>{_escape(x.get('name'))} — {_escape(x.get('type'))}</li>" for x in related[:15]) + "</ul>")
        links = [x for x in list(artist.get("links") or []) if isinstance(x, dict) and x.get("url")]
        if links:
            parts.append("<h3>Links</h3><ul>" + "".join(f'<li><a href="{_escape(x.get("url"))}">{_escape(x.get("type") or "website")}</a></li>' for x in links[:12]) + "</ul>")
        return "".join(parts)

    @staticmethod
    def _discography_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<p style='color:#9097a2'>No release groups were returned for this artist.</p>"
        parts = ["<h2>Release timeline</h2><table cellspacing='10'>"]
        for row in rows:
            title = _escape(row.get("title"))
            year = _escape(row.get("year") or row.get("date") or "")
            typ = _escape(row.get("primary_type") or "")
            image = ""
            path = str(row.get("cover_path") or "")
            if path and Path(path).exists():
                image = f'<img src="{Path(path).resolve().as_uri()}" width="58">'
            else:
                image = '<span style="color:#66717f">♪</span>'
            link = f'https://musicbrainz.org/release-group/{_escape(row.get("id"))}' if row.get("id") else ""
            title_html = f'<a href="{link}">{title}</a>' if link else title
            parts.append(f"<tr><td width='72'>{image}</td><td><b>{title_html}</b><br><span style='color:#aab0ba'>{year} {('· ' + typ) if typ else ''}</span></td></tr>")
        parts.append("</table>")
        return "".join(parts)

    @staticmethod
    def _credits_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<p style='color:#9097a2'>No structured credits were returned for this recording. MusicBrainz coverage varies by release.</p>"
        return "<h2>Credits & relationships</h2><ul>" + "".join(f"<li><b>{_escape(x.get('role'))}</b> — {_escape(x.get('name'))}</li>" for x in rows) + "</ul>"

    @staticmethod
    def _context_html(cards: list[dict[str, Any]]) -> str:
        if not cards:
            return "<p style='color:#9097a2'>No context cards were returned. Install or enable context plugins to add musical connections, liner notes and community context.</p>"
        parts: list[str] = []
        for card in cards:
            title = _escape(card.get("title") or "Context")
            kind = str(card.get("kind") or "")
            parts.append(f"<section><h2>{title}</h2>")
            if kind == "text":
                text = _escape(card.get("text") or "").replace("\n", "<br>")
                parts.append(f"<p style='font-size:16px;line-height:1.55'>{text}</p>")
            elif kind == "facts":
                facts = [x for x in list(card.get("facts") or []) if isinstance(x, dict)]
                parts.append("<table cellspacing='7'>")
                for fact in facts:
                    label = _escape(fact.get("label") or "")
                    value = _escape(fact.get("value") or "")
                    url = _escape(fact.get("url") or "")
                    rendered = f'<a href="{url}">{value}</a>' if url else value
                    parts.append(f"<tr><td><b>{label}</b></td><td>{rendered}</td></tr>")
                parts.append("</table>")
            elif kind == "list":
                items = [x for x in list(card.get("items") or []) if isinstance(x, dict)]
                parts.append("<ul>")
                for item in items:
                    item_title = _escape(item.get("title") or "")
                    url = _escape(item.get("url") or "")
                    title_html = f'<a href="{url}">{item_title}</a>' if url else item_title
                    relation = _escape(item.get("relation") or "")
                    badge = _escape(item.get("badge") or "")
                    subtitle = _escape(item.get("subtitle") or "")
                    meta = " · ".join(x for x in (relation, badge, subtitle) if x)
                    parts.append(
                        f"<li><b>{title_html}</b>"
                        + (f"<br><span style='color:#9aa1aa'>{meta}</span>" if meta else "")
                        + "</li>"
                    )
                parts.append("</ul>")

            provenance = card.get("provenance") if isinstance(card.get("provenance"), dict) else {}
            attribution = _escape(provenance.get("attribution") or provenance.get("source_extension_id") or "")
            source_url = _escape(provenance.get("source_url") or "")
            license_name = _escape(provenance.get("license") or "")
            source = f'<a href="{source_url}">{attribution or "source"}</a>' if source_url else attribution
            footer = " · ".join(x for x in (source, license_name) if x)
            if footer:
                parts.append(f"<p style='color:#777f8a;font-size:11px'>Source: {footer}</p>")
            parts.append("</section><hr>")
        return "".join(parts)

    @staticmethod
    def _info_html(identity: dict[str, Any], artwork: dict[str, Any], artist_photo: dict[str, Any], errors: list[Any]) -> str:
        rows = []
        for label, key in (("Recording MBID", "recording_mbid"), ("Artist MBID", "artist_mbid"), ("Release MBID", "release_mbid"), ("Release-group MBID", "release_group_mbid")):
            if identity.get(key):
                rows.append(f"<tr><td><b>{label}</b></td><td>{_escape(identity.get(key))}</td></tr>")
        if identity.get("score") is not None:
            rows.append(f"<tr><td><b>Metadata match</b></td><td>{float(identity.get('score') or 0):.0%}</td></tr>")
        if artwork.get("source"):
            rows.append(f"<tr><td><b>Artwork</b></td><td>{_escape(artwork.get('source'))}</td></tr>")
        if artist_photo.get("source"):
            rows.append(f"<tr><td><b>Artist photo</b></td><td>{_escape(artist_photo.get('source'))}</td></tr>")
        if artist_photo.get("creator"):
            rows.append(f"<tr><td><b>Photo creator</b></td><td>{_escape(artist_photo.get('creator'))}</td></tr>")
        if artist_photo.get("license_name"):
            licence = _escape(artist_photo.get("license_name"))
            licence_url = _escape(artist_photo.get("license_url") or "")
            licence_html = f'<a href="{licence_url}">{licence}</a>' if licence_url else licence
            rows.append(f"<tr><td><b>Photo licence</b></td><td>{licence_html}</td></tr>")
        if artist_photo.get("description_url"):
            rows.append(f'<tr><td><b>Commons source</b></td><td><a href="{_escape(artist_photo.get("description_url"))}">file page</a></td></tr>')
        if artist_photo.get("wikidata_qid"):
            rows.append(f"<tr><td><b>Wikidata</b></td><td>{_escape(artist_photo.get('wikidata_qid'))}</td></tr>")
        body = "<h2>Track identity</h2><table cellspacing='7'>" + "".join(rows) + "</table>" if rows else "<p>No additional track information yet.</p>"
        if errors:
            body += "<h3>Enrichment notes</h3><ul>" + "".join(f"<li>{_escape(x)}</li>" for x in errors) + "</ul>"
        body += "<p style='color:#777'>Online metadata: MusicBrainz. Artist photos: Wikimedia Commons via Wikidata when linked. Cover images: Cover Art Archive or the playback provider. Lyrics: local files/tags and installed plugins first; LRCLIB only when requested or explicitly enabled.</p>"
        return body

    # ---------------------------- synchronized lyrics
    @property
    def synced(self) -> list[dict[str, Any]]:
        return [line.as_payload() for line in self._lyrics_document.lines]

    @property
    def lyrics_document(self) -> LyricsDocument:
        return self._lyrics_document

    def set_position(self, position_ms: int) -> None:
        if not self._lyrics_document.synced:
            return
        idx = self._lyrics_document.current_index(position_ms)
        if idx != self._lyric_index:
            self._lyric_index = idx
            self._render_synced(idx)

    def _synced_lyrics_html(
        self,
        current: int,
        *,
        full_screen: bool = False,
    ) -> str:
        base=34 if full_screen else 24
        active=48 if full_screen else 32
        line_height=1.76 if full_screen else 1.62
        margin=15 if full_screen else 8
        parts=[
            f"<div style='font-size:{base}px;line-height:{line_height};"
            "max-width:980px;margin:0 auto'>"
        ]
        for i,row in enumerate(self.synced):
            line=_escape(row.get("text")) or "&nbsp;"
            stamp=max(0,int(row.get("time_ms") or 0))
            if i==current:
                link_color="#ffffff"
                style=(
                    f"font-size:{active}px;font-weight:750;color:#ffffff;"
                    f"margin:{margin}px 0"
                )
            elif current>=0 and abs(i-current)<=2:
                link_color="#d9e3ee"
                style="color:#d9e3ee;margin:8px 0"
            else:
                link_color="#aab8c8"
                style="color:#aab8c8;margin:7px 0"
            parts.append(
                f"<a name='line-{i}'></a>"
                f"<div style='{style}'>"
                f"<a href='seek:{stamp}' style='color:{link_color};text-decoration:none'>{line}</a>"
                "</div>"
            )
        parts.append("</div>")
        return "".join(parts)

    def _render_synced(self, current: int) -> None:
        self.lyrics.setHtml(self._synced_lyrics_html(current))
        if current >= 0:
            self.lyrics.scrollToAnchor(f"line-{current}")
