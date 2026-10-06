from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget,
    QListWidgetItem, QStackedWidget, QLineEdit, QComboBox, QFileDialog, QMessageBox,
    QSlider, QTextEdit, QInputDialog, QDialog, QFormLayout, QDialogButtonBox, QCheckBox,
    QTabWidget, QApplication, QPlainTextEdit, QFrame, QProgressBar,
)

from .paths import app_data_dir
from .provider_manager import ProviderManager
from .flow import FlowEngine
from .user_state import UserState
from .player import FlowPlayer
from .bridge_server import ProviderBridge
from .responsiveness import UiResponsivenessMonitor
from .background_scheduler import BackgroundScheduler
from .motion import MotionController, FAST_MOTION_MS, STANDARD_MOTION_MS
from .library_scan_controller import LibraryScanController
from .navigation_controller import NavigationController
from .source_policy_controller import SourcePolicyController
from .sources_feature import SourcesFeature
from .chiasm_feature import create_chiasm_feature
from .library_scan_status import (
    idle_scan_session,
    scan_activity_state,
    scan_change_suffix,
    scan_progress_message,
    scan_progress_patch,
    scan_roots_key,
    start_scan_session,
)
from .ux_components import (
    ActionCard,
    CommandPaletteDialog,
    CoverLabel,
    EmptyState,
    FeaturePresenceBar,
    set_help,
)

class _UiCallbackDispatcher(QObject):
    """Long-lived queued bridge from worker threads back to the Qt UI thread.

    Per-task QObject signal bridges are unsafe here: a worker can finish and
    release its final Python reference while Qt still has a queued MetaCall
    event waiting for that wrapper. Keeping one QApplication-owned dispatcher
    alive for the process lifetime removes that use-after-free window.
    """

    invoke = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.invoke.connect(self._invoke, Qt.QueuedConnection)

    @Slot(object)
    def _invoke(self, callback) -> None:
        callback()


def _escape_html(value: Any) -> str:
    import html
    return html.escape(str(value or ""))


def _track_text(t: dict[str, Any]) -> str:
    artist = str(t.get("artist") or "Unknown artist")
    title = str(t.get("title") or "Unknown track")
    source = str(t.get("provider_id") or "")
    return f"{artist} — {title}" + (f"   ·   {source}" if source else "")



class MainWindow(QMainWindow):
    externalCommand = Signal(str, object, object)

    def _startup_mark(self, phase: str) -> None:
        timeline = getattr(self, "_startup_timeline", None)
        if timeline is not None:
            timeline.mark(phase)

    @property
    def mind(self):
        if self._mind is None:
            from .mind import MindEngine

            self._mind = MindEngine(self.state, self.flow)
            self._startup_mark("lazy_service:mind")
        return self._mind

    @property
    def local_intelligence(self):
        if self._local_intelligence is None:
            from .local_intelligence import LocalIntelligenceService

            self._local_intelligence = LocalIntelligenceService(
                self.state,
                self.flow,
                self.providers.capabilities,
            )
            self._startup_mark("lazy_service:local_intelligence")
        return self._local_intelligence

    @property
    def knowledge(self):
        if self._knowledge is None:
            from .music_knowledge import MusicKnowledgeStore

            self._knowledge = MusicKnowledgeStore(
                self.data_dir / "music-knowledge.sqlite3"
            )
            self._startup_mark("lazy_service:music_knowledge")
        return self._knowledge

    @property
    def llm(self):
        if self._llm is None:
            from .llm_bridge import LLMClient

            self._llm = LLMClient()
            self._startup_mark("lazy_service:llm")
        return self._llm

    @property
    def metadata(self):
        if self._metadata is None:
            from .metadata import RichMetadataService

            self._metadata = RichMetadataService(
                self.data_dir,
                capability_broker=self.providers.capabilities,
            )
            self._startup_mark("lazy_service:metadata")
        return self._metadata

    def __init__(self, *, startup_timeline=None):
        super().__init__()
        self._startup_timeline = startup_timeline
        self._startup_mark("main_window_init_enter")
        self.setWindowTitle("Chiasm")
        self.resize(1280, 800)
        self.data_dir = app_data_dir()
        self.providers = ProviderManager(
            self.data_dir,
            startup_timeline=self._startup_timeline,
        )
        self._startup_mark("providers_ready")
        self.source_policy = SourcePolicyController(self.providers)
        self.state = UserState(self.data_dir / "taste.sqlite3")
        self._startup_mark("user_state_ready")
        self.motion = MotionController(
            self,
            reduced=self.state.get_bool("reduce_motion", False),
        )
        self.page_titles: dict[str, QLabel] = {}
        self.flow = FlowEngine(self.data_dir / "flow.sqlite3")
        # Cold launch only constructs services needed to render Home and play
        # audio.  Intelligence, metadata/network enrichment and the optional
        # LLM are instantiated on first real use.
        self._mind = None
        self._local_intelligence = None
        self._knowledge = None
        self._llm = None
        self._metadata = None
        self._startup_mark("core_services_ready")
        self.bridge: ProviderBridge | None = None
        self._bridge_start_pending = False
        self.current_page = "home"
        self._closing = False
        self._local_scan_started_at = 0.0
        self._local_scan_last_progress: dict[str, Any] = {}
        self._local_scan_session: dict[str, Any] = idle_scan_session()
        self.local_scan = LibraryScanController(self.data_dir, self)
        self.local_scan.progress.connect(self._local_scan_progress)
        self.local_scan.done.connect(self._local_scan_done)
        self.local_scan.failed.connect(self._local_scan_failed)
        self.navigation = NavigationController(
            self,
            refresh_delay_ms=16,
            settle_duration_ms=FAST_MOTION_MS,
            schedule=QTimer.singleShot,
        )
        # Compatibility aliases for focused GUI probes. The controller owns
        # these mutable collections and timing values.
        self._page_refresh_delay_ms = self.navigation.refresh_delay_ms
        self._built_lazy_pages = self.navigation.built_lazy_pages
        self.lazy_page_build_metrics = self.navigation.lazy_page_build_metrics
        self._search_sequence = 0
        self._search_pending_sequence = 0
        self._search_loading_delay_ms = 220
        self.background_scheduler = BackgroundScheduler(
            max_workers=4,
            reserved_foreground_slots=1,
        )
        # Parent the dispatcher to QApplication rather than MainWindow so
        # in-flight workers can safely post a final completion after the
        # window has begun closing. The callback itself observes _closing and
        # becomes a no-op.
        self._ui_callback_dispatcher = _UiCallbackDispatcher(
            QApplication.instance()
        )
        self._async_closing_event = threading.Event()
        self._async_generations: dict[str, int] = {}
        self._async_invalidations = 0
        self._async_stale_results_dropped = 0
        self.externalCommand.connect(self._on_external_command)

        self.player = FlowPlayer(
            self.providers.resolve, self._transition_for, self,
            playback_refresher=self.providers.refresh_playback,
        )

        from .playback_feature import PlaybackFeature

        self.playback_feature = PlaybackFeature(
            self.providers,
            self.state,
            self.flow,
            self.data_dir,
            metadata=lambda: self.metadata,
            knowledge=lambda: self.knowledge,
            llm_settings=lambda: self._llm_settings(),
            open_llm_settings=lambda: self._llm_settings_dialog(),
            llm_complete=lambda settings, prompt, context, tools:
                self.llm.complete(settings, prompt, context, tools),
            run_async=lambda *args, **kwargs: self._run_async(*args, **kwargs),
            invalidate_async=lambda scope: self._invalidate_async(scope),
            is_closing=lambda: self._closing,
            scan_active=lambda: self.local_scan.active,
            power_tools_enabled=lambda: self.state.get_bool("power_tools", False),
            motion=self.motion,
            page_titles=self.page_titles,
        )
        self.player.trackChanged.connect(self.playback_feature.on_track_changed)
        self.player.positionChanged.connect(self.playback_feature.on_position)
        self.player.playingChanged.connect(self.playback_feature.on_playing_changed)
        self.player.queueChanged.connect(
            lambda queue: self.playback_feature.on_queue_changed(
                queue, self.player.index
            )
        )
        self.player.error.connect(
            lambda message: self.statusBar().showMessage(message, 7000)
        )
        self.playback_feature.previousRequested.connect(self.player.previous)
        self.playback_feature.nextRequested.connect(self.player.next)
        self.playback_feature.seekRequested.connect(self.player.seek)
        self.playback_feature.setQueueRequested.connect(
            lambda tracks, start, autoplay: self.player.set_queue(
                list(tracks or []), int(start), bool(autoplay)
            )
        )
        self.playback_feature.appendQueueRequested.connect(
            lambda tracks, autoplay: self.player.append_queue(
                list(tracks or []), bool(autoplay)
            )
        )
        self.playback_feature.jumpQueueRequested.connect(
            lambda index: self.player.jump_to(int(index), autoplay=True)
        )
        self.playback_feature.replaceQueueItemRequested.connect(
            lambda index, track, autoplay: self.player.replace_queue_item(
                int(index), dict(track or {}), autoplay=bool(autoplay)
            )
        )
        self.playback_feature.currentTrackChanged.connect(
            self._playback_current_track_changed
        )
        self.playback_feature.knowledgeChanged.connect(
            self._playback_knowledge_changed
        )
        self.playback_feature.statusMessageRequested.connect(
            lambda message, timeout: self.statusBar().showMessage(message, timeout)
        )
        self._startup_mark("player_ready")

        self.responsiveness = UiResponsivenessMonitor(self)
        self._build_ui()
        self._startup_mark("ui_built")
        self.responsiveness.start()
        self.responsiveness.mark_action("startup:home")
        self._show_home()
        self._startup_mark("home_ready")
        # The local AI/control bridge is useful, but it is not part of the
        # first-screen contract. Some platform networking stacks can block
        # socket setup for many seconds, so never bind it on the Qt UI thread.
        self.responsiveness.mark_action("startup:bridge")
        self._startup_mark("bridge_start_scheduled")
        self._start_local_bridge()
        startup_roots=self.providers.local_roots()
        if startup_roots and not self.providers.local_index_ready(startup_roots):
            # One-time migration for existing users who have configured roots
            # but no persistent index yet. Once indexed, later launches load the
            # cache immediately and do not walk the NAS automatically.
            QTimer.singleShot(0, lambda: self._start_local_scan("initial index"))
        # Chiasm is the product in this fork: make the spatial collection the
        # first screen while retaining inherited host pages for setup/support.
        self.open_page("chiasm")
        self._startup_mark("main_window_init_ready")

    def _playback_current_track_changed(self, track: object) -> None:
        row = dict(track or {}) if isinstance(track, dict) else {}
        if not row:
            return
        if hasattr(self, "journey_workspace"):
            self.journey_workspace.on_track_changed(row)
        if hasattr(self, "album_wall"):
            self.album_wall.highlight_track(row)
        if self.current_page == "home":
            self._refresh_home_continue()

    def _playback_knowledge_changed(self) -> None:
        if (
            self.current_page == "music_map"
            and hasattr(self, "journey_workspace")
        ):
            self.journey_workspace.refresh_knowledge_graph()

    # ------------------------------- UI
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        body_l = QHBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(0)
        outer.addWidget(body, 1)

        # ------------------------------------------------------------------
        # Navigation: user goals first. Advanced tools remain reachable
        # contextually and through Power tools rather than owning the sidebar.
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(210)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(15, 18, 15, 14)
        side.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel()
        mark_path = Path(__file__).resolve().parent / "assets" / "chiasm-mark.png"
        pixmap = QPixmap(str(mark_path))
        if not pixmap.isNull():
            mark.setPixmap(
                pixmap.scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        mark.setFixedSize(44, 44)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        logo = QLabel("CHIASM")
        logo.setObjectName("brandName")
        tagline = QLabel("Explore your music.")
        tagline.setObjectName("brandTagline")
        titles.addWidget(logo)
        titles.addWidget(tagline)
        brand.addWidget(mark)
        brand.addLayout(titles, 1)
        side.addLayout(brand)
        side.addSpacing(18)

        self.nav_buttons: dict[str, QPushButton] = {}

        def add_nav(label: str, page: str) -> QPushButton:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("active", False)
            button.clicked.connect(lambda _checked=False, target=page: self.open_page(target))
            self.nav_buttons[page] = button
            side.addWidget(button)
            return button

        add_nav("Home", "home")
        add_nav("My Music", "library")
        add_nav("Explore", "explore")
        add_nav("Journeys", "journeys")
        add_nav("Playlists", "playlists")

        side.addStretch(1)

        sources_nav = add_nav("Sources && plugins", "sources")
        set_help(
            sources_nav,
            "Sources & plugins",
            "Choose where Melodex can find music. Everyday controls stay simple; technical provider controls appear when Power tools are enabled.",
        )

        self.power_toggle = QCheckBox("Power tools")
        self.power_toggle.setObjectName("powerToggle")
        self.power_toggle.setChecked(self.state.get_bool("power_tools", False))
        self.power_toggle.stateChanged.connect(self._power_changed)
        set_help(
            self.power_toggle,
            "Power tools",
            "Reveal provider diagnostics, routing controls and other expert features. Turning this off hides complexity; it does not remove or reset anything.",
        )
        side.addWidget(self.power_toggle)
        body_l.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        body_l.addWidget(self.stack, 1)
        self.pages: dict[str, QWidget] = {}

        from .journey_workspace import JourneyWorkspace

        self.journey_workspace = JourneyWorkspace(
            self.providers,
            self.state,
            self.flow,
            local_intelligence=lambda: self.local_intelligence,
            knowledge=lambda: self.knowledge,
            metadata=lambda: self.metadata,
            run_async=self._run_async,
            current_track=self.playback_feature.current_track,
            page_titles=self.page_titles,
        )
        self.journey_workspace.navigationRequested.connect(self.open_page)
        self.journey_workspace.playTracksRequested.connect(
            lambda tracks: self.player.set_queue(list(tracks or []), 0, True)
        )
        self.journey_workspace.queueTracksRequested.connect(
            lambda tracks: self.player.append_queue(list(tracks or []), autoplay=False)
        )
        self.journey_workspace.replaceUpcomingRequested.connect(
            lambda tracks: self.player.replace_upcoming(list(tracks or []))
        )
        self.journey_workspace.nextTrackRequested.connect(self.player.next)
        self.journey_workspace.sessionFromTrackRequested.connect(
            self._start_session_from_map_track
        )
        self.journey_workspace.statusMessageRequested.connect(
            lambda message, timeout: self.statusBar().showMessage(message, timeout)
        )
        self.player.manualAdvanced.connect(self.journey_workspace.on_manual_advance)
        self.chiasm_feature = create_chiasm_feature(self)
        for name in [
            "home",
            "library",
            "explore",
            "now_playing",
            "for_you",
            "discover",
            "album_wall",
            "music_map",
            "journeys",
            "playlists",
            "moments",
            "ask",
        ]:
            if name == "now_playing":
                page = self.playback_feature.now_playing_page
            elif name in self.journey_workspace.pages:
                page = self.journey_workspace.pages[name]
            else:
                page = QWidget()
            self.pages[name] = page
            self.stack.addWidget(page)

        self.sources_feature = SourcesFeature(
            self.providers,
            self.source_policy,
            self.state,
            run_async=self._run_async,
            diagnostics_metrics=self._diagnostics_ui_metrics,
            is_active=lambda: not self._closing and self.current_page == "sources",
            power_tools_enabled=self.power_toggle.isChecked(),
            parent=self,
        )
        self.sources_feature.musicFolderRequested.connect(self._choose_music_folder)
        self.sources_feature.providerSearchRequested.connect(self._open_provider_search)
        self.sources_feature.extensionUseRequested.connect(self._use_extension)
        self.sources_feature.bridgeRequested.connect(self._bridge_dialog)
        self.sources_feature.pluginPresenceChanged.connect(self._refresh_plugin_presence)
        self.sources_feature.sourceCatalogChanged.connect(self._refresh_source_combo)
        self.sources_feature.actionMarked.connect(self.responsiveness.mark_action)
        self.sources_feature.statusMessageRequested.connect(
            lambda message, timeout: self.statusBar().showMessage(message, timeout)
        )
        self.playback_feature.pluginDirectoryRequested.connect(
            self.sources_feature.open_plugin_directory
        )
        self.pages["sources"] = self.sources_feature
        self.stack.addWidget(self.sources_feature)
        self.page_titles["sources"] = self.sources_feature.title_label

        # Heavy surfaces get only a tiny first-paint shell at startup. Their
        # modules and widgets are constructed on the first navigation to them.
        self.navigation.set_lazy_builders(
            {
                "library": self._build_library,
                "now_playing": self.playback_feature.build_now_playing,
                "album_wall": self._build_album_wall,
                "chiasm": self.chiasm_feature.build,
                "music_map": self.journey_workspace.build_music_map,
            }
        )
        for page, title, subtitle in (
            ("library", "My Music", "Preparing your collection…"),
            ("now_playing", "Now playing", "Preparing lyrics, artwork and visuals…"),
            ("album_wall", "Album Wall", "Preparing your visual collection…"),
            ("music_map", "Music Map", "Preparing your music landscape…"),
        ):
            self._prepare_lazy_page_shell(page, title, subtitle)

        self._build_home()
        self._build_explore()
        self._build_for_you()
        self._build_discover()
        self._build_playlists()
        self._build_moments()
        self._build_ask()

        # Queue is contextual and stays out of the primary navigation.
        body_l.addWidget(self.playback_feature.queue_panel)

        # ------------------------------------------------------------------
        # Long-running background work stays visible without taking over the UI.
        self.background_activity = QFrame()
        self.background_activity.setObjectName("artworkProgressPanel")
        activity_l = QHBoxLayout(self.background_activity)
        activity_l.setContentsMargins(14, 7, 14, 7)
        activity_l.setSpacing(10)

        self.background_activity_label = QLabel("")
        self.background_activity_label.setObjectName("artworkProgressDetail")
        self.background_activity_label.setWordWrap(False)
        activity_l.addWidget(self.background_activity_label, 1)

        self.background_activity_progress = QProgressBar()
        self.background_activity_progress.setFixedWidth(180)
        self.background_activity_progress.setTextVisible(True)
        self.background_activity_progress.setRange(0, 0)
        activity_l.addWidget(self.background_activity_progress)

        self.background_activity_view = QPushButton("View")
        self.background_activity_view.setObjectName("quietButton")
        self.background_activity_view.clicked.connect(
            lambda: self.open_page("library")
        )
        activity_l.addWidget(self.background_activity_view)

        self.background_activity_pause = QPushButton("Pause")
        self.background_activity_pause.setObjectName("quietButton")
        self.background_activity_pause.clicked.connect(
            self._toggle_local_scan_pause
        )
        activity_l.addWidget(self.background_activity_pause)

        self.background_activity_cancel = QPushButton("Cancel")
        self.background_activity_cancel.setObjectName("quietButton")
        self.background_activity_cancel.clicked.connect(
            self._cancel_local_scan
        )
        activity_l.addWidget(self.background_activity_cancel)

        self.background_activity.hide()
        outer.addWidget(self.background_activity)

        self._background_activity_timer = QTimer(self)
        self._background_activity_timer.setInterval(1000)
        self._background_activity_timer.timeout.connect(
            self._refresh_background_scan_activity
        )

        # ------------------------------------------------------------------
        # Persistent playback presentation belongs to PlaybackFeature.
        self.playback_feature.set_open_now_playing_handler(
            lambda: self.open_page("now_playing")
        )
        self.playback_feature.set_power_tools_visible(
            self.power_toggle.isChecked()
        )
        outer.addWidget(self.playback_feature.player_bar)

        # Expert speed: command palette without forcing more controls onto
        # everybody else's screen.
        self.shortcut_palette = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_palette.activated.connect(self._open_command_palette)
        self.shortcut_palette_mac = QShortcut(QKeySequence("Meta+K"), self)
        self.shortcut_palette_mac.activated.connect(self._open_command_palette)

        self.setStyleSheet("""
            QMainWindow,QWidget{
                background:#0f1116;
                color:#f4f6fa;
                font-family:"SF Pro Text","Segoe UI",Arial;
                font-size:13px;
            }
            QLabel{background:transparent}
            QLabel#pageTitle{
                font-size:27px;
                font-weight:720;
            }
            QLabel#pageSubtitle{
                color:#99a4b3;
                font-size:13px;
                margin-bottom:6px;
            }
            QLabel#pageHint{
                color:#758297;
                margin-top:8px;
            }
            QLabel#heroTitle{
                font-size:20px;
                font-weight:720;
            }
            QLabel#sectionTitle{
                font-size:17px;
                font-weight:700;
                margin-top:12px;
            }
            QLabel#sectionTitleCompact{
                font-size:17px;
                font-weight:700;
            }
            QLabel#panelHeading{
                font-size:15px;
                font-weight:700;
            }
            QLabel#mutedText{color:#98a3b3}
            QLabel#subtleText{
                color:#7f8b9b;
                margin-top:6px;
            }
            QLabel#searchStatus{
                color:#98a4b4;
                padding:6px 2px 4px 2px;
                font-size:12px;
            }
            QWidget#sidebar{
                background:#0a0d12;
                border-right:1px solid #202733;
            }
            QLabel#brandName{
                font-size:20px;
                font-weight:760;
                letter-spacing:2px;
            }
            QLabel#brandTagline{
                color:#778397;
                font-size:10px;
            }
            QPushButton#navButton{
                background:transparent;
                border:0;
                border-radius:9px;
                padding:11px 12px;
                text-align:left;
                color:#dfe4ec;
            }
            QPushButton#navButton:hover{background:#151b25}
            QPushButton#navButton[active="true"]{
                background:#1b2739;
                color:#ffffff;
                font-weight:650;
            }
            QCheckBox#powerToggle{
                background:transparent;
                color:#9ca7b8;
                padding:10px 7px;
            }
            QPushButton{
                background:#181e28;
                border:1px solid #2a3443;
                border-radius:9px;
                padding:9px 13px;
            }
            QPushButton:hover{
                background:#222b38;
                border-color:#3a4a60;
            }
            QPushButton#primaryButton{
                background:#1875e8;
                border-color:#2582f2;
                color:white;
                font-weight:700;
                padding:11px 17px;
            }
            QPushButton#secondaryButton{
                background:#151b24;
                border-color:#283443;
                color:#d7dde7;
                font-weight:600;
            }
            QPushButton#quietButton{
                background:transparent;
                border-color:#28313e;
                color:#c7ced9;
            }
            QPushButton#miniButton{
                padding:6px 8px;
                font-size:11px;
            }
            QPushButton#segmentButton{
                background:transparent;
                border-color:#28313e;
                color:#aab3c1;
                padding:8px 12px;
            }
            QPushButton#segmentButton:checked{
                background:#1c2d46;
                border-color:#31527a;
                color:white;
                font-weight:650;
            }
            QPushButton#transportButton{
                min-width:38px;
                min-height:38px;
                max-width:38px;
                border-radius:11px;
            }
            QPushButton#transportButtonWide{
                min-height:38px;
                border-radius:11px;
            }
            QPushButton#playerAction{min-height:36px}
            QPushButton#nowPlayingTitle{
                background:transparent;
                border:0;
                padding:0;
                text-align:left;
                font-weight:700;
                font-size:15px;
            }
            QPushButton#nowPlayingTitle:hover{color:#72aefb}
            QLabel#nowPlayingMeta{color:#9da7b7}
            QWidget#playerBar{
                background:#0c1016;
                border-top:1px solid #202733;
            }
            QWidget#queuePanel{
                background:#0d1118;
                border-left:1px solid #202733;
            }
            QLabel#panelTitle{font-size:17px;font-weight:700}
            QLineEdit,QComboBox,QTextEdit,QPlainTextEdit,QListWidget{
                background:#131923;
                border:1px solid #293443;
                border-radius:10px;
                padding:8px;
                selection-background-color:#274f7a;
            }
            QLineEdit:focus,QComboBox:focus,QTextEdit:focus,QListWidget:focus{
                border-color:#3c78b8;
            }
            QListWidget::item{
                padding:11px;
                border-bottom:1px solid #202733;
            }
            QListWidget::item:selected{background:#1e3552}
            QListWidget#sourcesList{
                background:transparent;
                border:0;
                padding:0;
            }
            QListWidget#sourcesList::item{
                background:transparent;
                border:1px solid transparent;
                border-radius:12px;
                padding:4px;
            }
            QListWidget#sourcesList::item:hover{
                background:#131c28;
                border-color:#26384d;
            }
            QListWidget#sourcesList::item:selected{
                background:#17263a;
                border-color:#31547d;
            }
            QFrame#actionCard{
                background:#141b25;
                border:1px solid #293544;
                border-radius:12px;
            }
            QFrame#actionCard:hover{
                background:#182231;
                border-color:#3d5571;
            }
            QLabel#cardEyebrow{
                color:#6fa9ef;
                font-size:10px;
                font-weight:700;
            }
            QLabel#cardTitle{font-size:18px;font-weight:720}
            QLabel#cardBody{
                color:#929dac;
                font-size:12px;
            }
            QLabel#cardAction{color:#72aefb;font-weight:650}
            QFrame#albumCard{
                background:transparent;
                border:1px solid transparent;
                border-radius:12px;
            }
            QFrame#albumCard:hover{
                background:#151c26;
                border-color:#29384a;
            }
            QLabel#albumCardTitle{font-weight:700;font-size:12px}
            QLabel#albumCardMeta{color:#8995a7;font-size:11px}
            QListView#visualTrackList{
                background:transparent;
                border:0;
                padding:0;
            }
            QListView#visualTrackList::item{
                background:transparent;
                border:0;
                padding:0;
            }
            QListView#visualTrackList::item:selected{
                background:transparent;
            }
            QFrame#trackRow{
                background:#121923;
                border:1px solid #222e3d;
                border-radius:10px;
            }
            QFrame#trackRow:hover{
                background:#161f2b;
                border-color:#33465e;
            }
            QLabel#trackTitle{font-size:14px;font-weight:700}
            QLabel#trackMeta{color:#8f9bad;font-size:12px}
            QLabel#warningPill{
                background:#3a2a16;
                border:1px solid #6e5126;
                border-radius:8px;
                color:#e2bd77;
                padding:4px 7px;
                font-size:10px;
            }
            QLabel#coverArt{
                background:#111722;
                border:1px solid #253040;
                border-radius:8px;
            }
            QFrame#emptyState{
                background:#121821;
                border:1px dashed #313d4e;
                border-radius:12px;
            }
            QLabel#emptyTitle{font-size:20px;font-weight:720}
            QLabel#emptyBody{color:#97a2b2;font-size:13px}
            QFrame#homeHero{
                background:#131c29;
                border:1px solid #2a3d56;
                border-radius:12px;
            }
            QFrame#continueCard{
                background:#121923;
                border:1px solid #273343;
                border-radius:12px;
            }
            QFrame#powerPanel{
                background:#111821;
                border:1px solid #2b3747;
                border-radius:12px;
            }
            QFrame#sourceOverview{
                background:#121b26;
                border:1px solid #2a3a4d;
                border-radius:12px;
            }
            QFrame#sourceFirstRun{
                background:#102033;
                border:1px solid #345a82;
                border-radius:12px;
            }
            QLabel#sourceFirstRunTitle{
                font-size:16px;
                font-weight:740;
                color:#e8f2ff;
            }
            QLabel#sourceFirstRunBody{
                color:#aebed1;
                font-size:11px;
            }

            QFrame#pluginFeaturePicker{
                background:#101720;
                border:1px solid #253346;
                border-radius:12px;
            }
            QFrame#featurePresenceBar{
                background:#101821;
                border:1px solid #26384c;
                border-radius:10px;
            }
            QFrame#artworkProgressPanel{
                background:#101821;
                border:1px solid #2a3d53;
                border-radius:11px;
            }
            QLabel#artworkProgressTitle{
                font-size:12px;
                font-weight:720;
                color:#d8e6f6;
            }
            QLabel#artworkProgressSummary{
                font-size:10px;
                color:#93a7bd;
            }
            QLabel#artworkProgressDetail{
                font-size:10px;
                color:#8492a3;
            }
            QProgressBar{
                min-height:14px;
                max-height:14px;
                border:1px solid #2b3a4c;
                border-radius:7px;
                background:#0c121a;
                text-align:center;
                color:#d6e5f5;
                font-size:9px;
            }
            QProgressBar::chunk{
                border-radius:6px;
                background:#365f8d;
            }

            QFrame#featurePresenceBar[active="true"]{
                background:#111f2c;
                border-color:#315274;
            }
            QLabel#featurePresenceIcon{
                color:#7fb7f1;
                background:#172a3e;
                border:1px solid #2f4e6c;
                border-radius:7px;
                font-size:12px;
                font-weight:800;
            }
            QLabel#featurePresenceText{color:#c7d1de;font-size:11px}
            QPushButton#featurePresenceAction{
                background:transparent;
                border:1px solid #30445b;
                border-radius:8px;
                padding:5px 8px;
                color:#9ebfe4;
                font-size:10px;
                font-weight:650;
            }
            QPushButton#featurePresenceAction:hover{
                background:#182536;
                border-color:#45688e;
                color:#e5f1ff;
            }

            QLabel#pluginFeatureTitle{font-size:13px;font-weight:700}
            QLabel#pluginFeatureSubtitle{color:#7f8b9c;font-size:10px}
            QPushButton#featureChip{
                background:#151f2c;
                border:1px solid #2d4057;
                border-radius:9px;
                padding:7px 10px;
                color:#b9cce2;
                font-weight:650;
            }
            QPushButton#featureChip:hover{
                background:#1b2b3e;
                border-color:#42658c;
                color:#e5f0ff;
            }
            QFrame#sourceSummaryCard{
                background:#0f1620;
                border:1px solid #263547;
                border-radius:11px;
            }
            QLabel#sourceSummaryIcon{
                background:#18283c;
                border:1px solid #2f4c6d;
                border-radius:9px;
                color:#7eb8ff;
                font-size:16px;
                font-weight:800;
            }
            QLabel#sourceSummaryValue{
                color:#8f9bad;
                font-size:11px;
            }
            QLabel#overviewIcon{
                background:#193354;
                border:1px solid #2f5d8f;
                border-radius:12px;
                color:#d8eaff;
                font-size:21px;
                font-weight:700;
            }
            QFrame#sourceCard{
                background:#101720;
                border:1px solid #223045;
                border-radius:10px;
            }
            QLabel#sourceBadge{
                background:#1c2a3e;
                color:#dce9fb;
                border:1px solid #34506f;
                border-radius:10px;
                font-size:17px;
                font-weight:750;
            }
            QLabel#sourceTitle{font-size:15px;font-weight:700}
            QLabel#originPill{
                background:#17202c;
                border:1px solid #2a394b;
                border-radius:7px;
                padding:2px 6px;
                color:#8fa7c3;
                font-size:9px;
                font-weight:650;
            }
            QLabel#sourceDescription{color:#8f9bad}
            QLabel#sourceKind{color:#7d899b;font-size:11px}
            QLabel#statusPill{
                background:#1a2634;
                border:1px solid #30445b;
                border-radius:9px;
                padding:5px 8px;
                color:#bfd4eb;
                font-size:11px;
            }
            QTabWidget::pane{
                border:0;
                background:transparent;
            }
            QTabBar::tab{
                background:transparent;
                color:#aeb7c5;
                border:0;
                border-radius:8px;
                padding:8px 14px;
                margin-right:4px;
            }
            QTabBar::tab:selected{
                background:#1875e8;
                color:white;
            }
            QScrollBar:vertical{
                background:transparent;
                width:10px;
                margin:2px;
            }
            QScrollBar::handle:vertical{
                background:#334154;
                min-height:32px;
                border-radius:5px;
            }
            QScrollBar::handle:vertical:hover{background:#43566f}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{
                height:0;
                background:transparent;
            }
            QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{
                background:transparent;
            }
            QScrollBar:horizontal{
                background:transparent;
                height:10px;
                margin:2px;
            }
            QScrollBar::handle:horizontal{
                background:#334154;
                min-width:32px;
                border-radius:5px;
            }
            QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{
                width:0;
                background:transparent;
            }
            QStatusBar{
                background:#0b0f15;
                color:#7f8b9b;
                border-top:1px solid #202733;
                font-size:11px;
            }
            QToolTip{
                background:#18202c;
                color:#f4f6fa;
                border:1px solid #3a4658;
                padding:7px;
            }
        """)
        self.navigation.update_nav_state("home")
        self._refresh_plugin_presence()

    @staticmethod
    def _clear_layout_items(layout) -> None:
        while layout.count():
            item=layout.takeAt(0)
            child=item.layout()
            if child is not None:
                MainWindow._clear_layout_items(child)
                child.deleteLater()
            widget=item.widget()
            if widget is not None:
                widget.deleteLater()

    def _page_layout(self, page: str, title: str, subtitle: str=""):
        existing=self.pages[page].layout()
        if existing is None:
            lay=QVBoxLayout(self.pages[page])
        else:
            lay=existing
            self._clear_layout_items(lay)
        lay.setContentsMargins(28,24,28,24)
        lay.setSpacing(6)
        t=QLabel(title); t.setObjectName("pageTitle"); lay.addWidget(t)
        self.page_titles[page]=t
        if subtitle:
            subtitle_label=QLabel(subtitle)
            subtitle_label.setWordWrap(True)
            subtitle_label.setObjectName("pageSubtitle")
            lay.addWidget(subtitle_label)
        return lay

    def _prepare_lazy_page_shell(
        self,
        page: str,
        title: str,
        subtitle: str,
    ) -> None:
        lay=self._page_layout(page,title,subtitle)
        hint=QLabel("Opening…")
        hint.setObjectName("pageHint")
        lay.addWidget(hint)
        lay.addStretch(1)

    def _build_home(self):
        l=self._page_layout(
            "home",
            "Home",
            "Pick something to play, or carry on where you left off.",
        )

        hero=QFrame()
        hero.setObjectName("homeHero")
        hero_l=QVBoxLayout(hero)
        hero_l.setContentsMargins(22,20,22,20)
        hero_l.setSpacing(10)
        prompt=QLabel("Start listening")
        prompt.setObjectName("heroTitle")
        hero_l.addWidget(prompt)
        self.home_explanation=QLabel(
            "A session from your library, shaped as you listen."
        )
        self.home_explanation.setWordWrap(True)
        self.home_explanation.setObjectName("mutedText")
        hero_l.addWidget(self.home_explanation)

        self.home_primary_button=QPushButton("▶  Play something")
        self.home_primary_button.setObjectName("primaryButton")
        self.home_primary_button.setMinimumHeight(48)
        self.home_primary_button.clicked.connect(self._home_primary_action)
        set_help(
            self.home_primary_button,
            "Play something",
            "Starts a balanced session from your library. You can steer it later.",
        )
        hero_l.addWidget(self.home_primary_button)

        self.home_moods_widget=QWidget()
        moods=QHBoxLayout(self.home_moods_widget)
        moods.setContentsMargins(0,0,0,0)
        comfort=QPushButton("Comfort")
        explore=QPushButton("Explore")
        rediscover=QPushButton("Rediscover")
        tune=QPushButton("Tune it…")
        comfort.clicked.connect(lambda:self._play_for_me("comfort",60,0.14))
        explore.clicked.connect(lambda:self._play_for_me("explore",60,0.72))
        rediscover.clicked.connect(lambda:self._play_for_me("rediscover",60,0.42))
        tune.clicked.connect(lambda:self.open_page("for_you"))
        set_help(comfort,"Comfort","Stay close to music Melodex already knows you respond well to.")
        set_help(explore,"Explore","Move further from the familiar while keeping the session musically coherent.")
        set_help(rediscover,"Rediscover","Favour music from your library that you once played but have not heard recently.")
        set_help(tune,"Fine-tune listening","Open duration, familiarity and local-intelligence controls.")
        moods.addWidget(comfort)
        moods.addWidget(explore)
        moods.addWidget(rediscover)
        moods.addStretch(1)
        moods.addWidget(tune)
        hero_l.addWidget(self.home_moods_widget)
        l.addWidget(hero)

        self.home_continue_heading=QLabel("Continue listening")
        self.home_continue_heading.setStyleSheet("font-size:18px;font-weight:700;margin-top:10px")
        l.addWidget(self.home_continue_heading)

        self.home_continue=QFrame()
        self.home_continue.setObjectName("continueCard")
        continue_l=QHBoxLayout(self.home_continue)
        continue_l.setContentsMargins(14,14,14,14)
        continue_l.setSpacing(15)
        self.home_continue_cover=CoverLabel(92)
        continue_l.addWidget(self.home_continue_cover)
        continue_text=QVBoxLayout()
        self.home_continue_title=QLabel("Nothing played yet")
        self.home_continue_title.setStyleSheet("font-size:17px;font-weight:700")
        self.home_continue_meta=QLabel("Play something and it will be easy to return here.")
        self.home_continue_meta.setWordWrap(True)
        self.home_continue_meta.setObjectName("mutedText")
        continue_text.addStretch(1)
        continue_text.addWidget(self.home_continue_title)
        continue_text.addWidget(self.home_continue_meta)
        continue_text.addStretch(1)
        continue_l.addLayout(continue_text,1)
        self.home_continue_button=QPushButton("▶ Continue")
        self.home_continue_button.setObjectName("secondaryButton")
        self.home_continue_button.clicked.connect(self._home_continue_play)
        self.home_continue_button.setEnabled(False)
        set_help(
            self.home_continue_button,
            "Continue listening",
            "Starts the most recent track again. Your listening history stays private on this computer.",
        )
        continue_l.addWidget(self.home_continue_button)
        l.addWidget(self.home_continue)

        self.home_explore_heading=QLabel("Explore your music")
        self.home_explore_heading.setStyleSheet("font-size:18px;font-weight:700;margin-top:10px")
        l.addWidget(self.home_explore_heading)
        self.home_explore_widget=QWidget()
        cards=QHBoxLayout(self.home_explore_widget)
        cards.setContentsMargins(0,0,0,0)
        library_card=ActionCard(
            "Browse your collection",
            "Albums, artists and tracks.",
            eyebrow="My Music",
            action_text="Browse",
        )
        library_card.clicked.connect(lambda:self.open_page("library"))
        wall_card=ActionCard(
            "Album Wall",
            "Browse your collection as a wall of covers.",
            eyebrow="Visual",
            action_text="Explore",
        )
        wall_card.clicked.connect(lambda:self.open_page("album_wall"))
        map_card=ActionCard(
            "Music Map",
            "See how tracks in your library connect.",
            eyebrow="Deep explore",
            action_text="Open map",
        )
        map_card.clicked.connect(lambda:self.open_page("music_map"))
        cards.addWidget(library_card,1)
        cards.addWidget(wall_card,1)
        cards.addWidget(map_card,1)
        l.addWidget(self.home_explore_widget)

        self.home_status=QLabel()
        self.home_status.setWordWrap(True)
        self.home_status.setObjectName("subtleText")
        l.addWidget(self.home_status)
        l.addStretch(1)


    def _build_for_you(self):
        l=self._page_layout(
            "for_you",
            "Tune your listening",
            "Choose how long to listen and how adventurous the session should be.",
        )

        row=QHBoxLayout()
        self.mode=QComboBox()
        self.mode.addItem("Balanced","balanced")
        self.mode.addItem("Comfort","comfort")
        self.mode.addItem("Rediscover","rediscover")
        self.mode.addItem("Explore","explore")
        self.minutes=QComboBox()
        self.minutes.addItems(["30","60","90","120"])
        self.adventure=QSlider(Qt.Horizontal)
        self.adventure.setRange(0,100)
        self.adventure.setValue(35)

        set_help(
            self.mode,
            "Listening style",
            "Balanced mixes familiarity and discovery. Comfort stays close to known preferences. Rediscover favours neglected music. Explore moves further away.",
        )
        set_help(
            self.minutes,
            "Session length",
            "Choose approximately how long Melodex should plan for.",
        )
        set_help(
            self.adventure,
            "Familiar to adventurous",
            "Move left to stay close to music Melodex already knows you respond well to; move right to allow more unexpected choices.",
        )

        row.addWidget(QLabel("Style"))
        row.addWidget(self.mode)
        row.addWidget(QLabel("Minutes"))
        row.addWidget(self.minutes)
        row.addWidget(QLabel("Familiar"))
        row.addWidget(self.adventure,1)
        row.addWidget(QLabel("Adventurous"))
        l.addLayout(row)

        go=QPushButton("▶ Build this session")
        go.setObjectName("primaryButton")
        go.clicked.connect(
            lambda:self._play_for_me(
                str(self.mode.currentData() or "balanced"),
                int(self.minutes.currentText()),
                self.adventure.value()/100,
            )
        )
        set_help(
            go,
            "Build this session",
            "Creates a queue from your local library using these preferences. The exact tracks can still change as you listen.",
        )
        l.addWidget(go)

        self.taste_label=QLabel()
        self.taste_label.setWordWrap(True)
        self.taste_label.setObjectName("subtleText")
        l.addWidget(self.taste_label)

        intel_title=QLabel("From your library")
        intel_title.setStyleSheet("font-size:18px;font-weight:650;margin-top:10px")
        l.addWidget(intel_title)

        intel_help=QLabel(
            "Local suggestions based on what you have and what you play."
        )
        intel_help.setWordWrap(True)
        intel_help.setObjectName("mutedText")
        l.addWidget(intel_help)

        self.recommendation_plugin_presence=FeaturePresenceBar(
            "Recommendation helpers",
            baseline="Melodex local intelligence is active",
            action_text="Add recommendation helper…",
        )
        self.recommendation_plugin_presence.actionRequested.connect(
            lambda:self.sources_feature.open_plugin_directory("library_suggestions")
        )
        l.addWidget(self.recommendation_plugin_presence)

        intel_row=QHBoxLayout()
        similar=QPushButton("More like current")
        similar.clicked.connect(lambda:self._run_local_intelligence("similar"))
        rediscover=QPushButton("Forgotten favourites")
        rediscover.clicked.connect(lambda:self._run_local_intelligence("rediscover"))
        bridge=QPushButton("Bridge current → next")
        bridge.clicked.connect(lambda:self._run_local_intelligence("bridge"))
        detour=QPushButton("Find a detour")
        detour.clicked.connect(lambda:self._run_local_intelligence("detour"))
        analyse=QPushButton("Improve suggestions")
        analyse.clicked.connect(self._analyse_library_for_intelligence)

        set_help(similar,"More like current","Find music in your local library that is sonically near the track playing now.")
        set_help(rediscover,"Forgotten favourites","Look for music you once played or kept but have not heard recently.")
        set_help(bridge,"Bridge current to next","Find music that can make the transition between the current track and the next queued track feel more natural.")
        set_help(detour,"Find a detour","Keep part of the current musical character while deliberately changing other qualities.")
        set_help(
            analyse,
            "Improve suggestions",
            "Analyse sonic features locally so similarity, detours and map placement can become more accurate. Your audio is not uploaded.",
        )

        intel_row.addWidget(similar)
        intel_row.addWidget(rediscover)
        intel_row.addWidget(bridge)
        intel_row.addWidget(detour)
        intel_row.addWidget(analyse)
        intel_row.addStretch(1)
        l.addLayout(intel_row)

        self.intelligence_results=QListWidget()
        self.intelligence_results.itemDoubleClicked.connect(self._play_intelligence_result)
        l.addWidget(self.intelligence_results,1)

        intel_actions=QHBoxLayout()
        play_pick=QPushButton("▶ Play selected")
        play_pick.clicked.connect(self._play_selected_intelligence)
        queue_pick=QPushButton("+ Queue selected")
        queue_pick.clicked.connect(self._queue_selected_intelligence)
        intel_actions.addWidget(play_pick)
        intel_actions.addWidget(queue_pick)
        intel_actions.addStretch(1)
        l.addLayout(intel_actions)

    def _build_discover(self):
        l=self._page_layout(
            "discover",
            "Discover",
            "Search your library and connected sources.",
        )
        row=QHBoxLayout()
        self.search_box=QLineEdit()
        self.search_box.setPlaceholderText("Artist, track or album…")
        self.search_source=QComboBox()
        self.search_button=QPushButton("Search")
        self.search_button.clicked.connect(self._search)
        row.addWidget(self.search_box,1)
        row.addWidget(self.search_source)
        row.addWidget(self.search_button)
        l.addLayout(row)
        self.search_box.returnPressed.connect(self._search)

        self.search_plugin_presence=FeaturePresenceBar(
            "Search sources",
            baseline="Your local library is always searchable",
            action_text="Add music source…",
        )
        self.search_plugin_presence.actionRequested.connect(
            lambda:self.sources_feature.open_plugin_directory("search")
        )
        l.addWidget(self.search_plugin_presence)

        self.search_status=QLabel("Ready to search")
        self.search_status.setWordWrap(True)
        self.search_status.setStyleSheet(
            "color:#9aa7b7;padding:6px 2px 4px 2px;font-size:13px"
        )
        l.addWidget(self.search_status)

        self.results=QListWidget()
        self.results.itemDoubleClicked.connect(self._play_result)
        l.addWidget(self.results,1)

        row2=QHBoxLayout()
        addq=QPushButton("Add selected to queue")
        addq.clicked.connect(self._add_selected_to_queue)
        source_btn=QPushButton("Open source page")
        source_btn.clicked.connect(self._open_selected_source)
        row2.addWidget(addq)
        row2.addWidget(source_btn)
        row2.addStretch(1)
        l.addLayout(row2)

    def _build_library(self):
        from .library_browser import LibraryBrowser

        l=self._page_layout(
            "library",
            "My Music",
            "Albums, artists and tracks from your library.",
        )
        self.artwork_plugin_presence=FeaturePresenceBar(
            "Artwork helpers",
            baseline="Built-in artwork matching is active",
            action_text="Add artwork helper…",
        )
        self.artwork_plugin_presence.actionRequested.connect(
            lambda:self.sources_feature.open_plugin_directory("artwork")
        )
        self.artwork_plugin_presence.setVisible(
            bool(self.providers.local_catalog_count())
        )
        l.addWidget(self.artwork_plugin_presence)

        self.library_browser=LibraryBrowser(self)
        self.library_browser.playAlbumRequested.connect(self._play_album_wall_album)
        self.library_browser.queueAlbumRequested.connect(self._queue_album_data)
        self.library_browser.playArtistRequested.connect(self._play_library_artist)
        self.library_browser.playTrackRequested.connect(self._play_library_track)
        self.library_browser.queueTrackRequested.connect(self._queue_library_track)
        self.library_browser.editMetadataRequested.connect(self._edit_local_metadata)
        self.library_browser.addFolderRequested.connect(self._choose_music_folder)
        self.library_browser.rescanRequested.connect(self._rescan)
        self.library_browser.scanPauseRequested.connect(self._toggle_local_scan_pause)
        self.library_browser.scanCancelRequested.connect(self._cancel_local_scan)
        self.library_browser.albumWallRequested.connect(lambda:self.open_page("album_wall"))
        self.library_browser.momentsRequested.connect(lambda:self.open_page("moments"))
        self.library_browser.artworkRequested.connect(self._library_artwork_requested)
        self.library_browser.onlineArtworkRequested.connect(self._library_online_artwork_requested)
        self.library_browser.artistImageRequested.connect(self._library_artist_images_requested)
        self.library_browser.artistImageCacheRequested.connect(self._library_cached_artist_images_requested)
        self.library_browser.artistPhotoFileRequested.connect(self._choose_artist_photo_file)
        l.addWidget(self.library_browser,1)


    def _build_explore(self):
        l=self._page_layout(
            "explore",
            "Explore",
            "Search, browse visually, or follow connections through your music.",
        )

        cards=QHBoxLayout()
        search_card=ActionCard(
            "Search everything",
            "Find artists, albums and tracks.",
            eyebrow="Search",
            action_text="Search",
        )
        search_card.clicked.connect(lambda:self.open_page("discover"))
        self.explore_wall_card=ActionCard(
            "Album Wall",
            "Browse your collection by cover.",
            eyebrow="Browse",
            action_text="Open wall",
        )
        self.explore_wall_card.clicked.connect(lambda:self.open_page("album_wall"))
        self.explore_map_card=ActionCard(
            "Music Map",
            "Follow relationships between tracks.",
            eyebrow="Relationships",
            action_text="Open map",
        )
        self.explore_map_card.clicked.connect(lambda:self.open_page("music_map"))
        cards.addWidget(search_card,1)
        cards.addWidget(self.explore_wall_card,1)
        cards.addWidget(self.explore_map_card,1)
        cards.addWidget(self.chiasm_feature.explore_card(self.open_page),1)
        l.addLayout(cards)

        self.explore_try_section=QWidget()
        try_l=QVBoxLayout(self.explore_try_section)
        try_l.setContentsMargins(0,0,0,0)
        try_l.setSpacing(8)
        help_title=QLabel("Try something")
        help_title.setObjectName("sectionTitle")
        try_l.addWidget(help_title)
        help_row=QHBoxLayout()
        self.explore_similar_button=QPushButton("More like what is playing")
        self.explore_similar_button.clicked.connect(
            lambda:self._run_local_intelligence("similar")
        )
        rediscover=QPushButton("Find a forgotten favourite")
        rediscover.clicked.connect(lambda:self._run_local_intelligence("rediscover"))
        self.explore_ask_button=QPushButton("Ask Melodex…")
        self.explore_ask_button.setObjectName("quietButton")
        self.explore_ask_button.clicked.connect(lambda:self.open_page("ask"))
        set_help(self.explore_similar_button,"More like this","Uses local intelligence to look for nearby music in your own library.")
        set_help(rediscover,"Forgotten favourite","Looks for music you used to play but have not heard for a while.")
        set_help(self.explore_ask_button,"Ask Melodex","Use an optional connected LLM for natural-language listening requests. Melodex still works without one.")
        help_row.addWidget(self.explore_similar_button)
        help_row.addWidget(rediscover)
        help_row.addWidget(self.explore_ask_button)
        help_row.addStretch(1)
        try_l.addLayout(help_row)

        note=QLabel(
            "Album Wall is for browsing. Music Map is for connections and routes."
        )
        note.setWordWrap(True)
        note.setObjectName("subtleText")
        try_l.addWidget(note)
        l.addWidget(self.explore_try_section)
        l.addStretch(1)

        self._refresh_explore_visibility()

    def _build_album_wall(self):
        from .album_wall import AlbumWallWidget

        l=self._page_layout(
            "album_wall",
            "Album Wall",
            "Browse your collection as a visual place. Drag or two-finger scroll to pan, zoom when you need it, and double-click an album to play.",
        )

        actions=QHBoxLayout()
        self.album_wall_options_button=QPushButton("Wall options…")
        self.album_wall_options_button.setObjectName("quietButton")
        self.album_wall_options_button.clicked.connect(self._toggle_album_wall_tools)
        self.album_wall_play_button=QPushButton("▶ Play selected")
        self.album_wall_play_button.clicked.connect(self._play_album_wall_selected)
        self.album_wall_play_button.setEnabled(False)
        self.album_wall_queue_button=QPushButton("+ Queue selected")
        self.album_wall_queue_button.clicked.connect(self._queue_album_wall_selected)
        self.album_wall_queue_button.setEnabled(False)
        set_help(
            self.album_wall_options_button,
            "Wall options",
            "Reveal occasional maintenance actions such as sonic analysis, rebuilding the wall and recovering missing covers.",
        )
        set_help(
            self.album_wall_play_button,
            "Play selected album",
            "Starts the selected album from track one in disc and track order.",
        )
        set_help(
            self.album_wall_queue_button,
            "Queue selected album",
            "Adds every track from the selected album after the music already in your queue.",
        )
        actions.addWidget(self.album_wall_options_button)
        actions.addStretch(1)
        actions.addWidget(self.album_wall_play_button)
        actions.addWidget(self.album_wall_queue_button)
        l.addLayout(actions)

        self.album_wall_power_panel=QFrame()
        self.album_wall_power_panel.setObjectName("powerPanel")
        power=QHBoxLayout(self.album_wall_power_panel)
        power.setContentsMargins(12,8,12,8)
        refresh=QPushButton("Rebuild wall")
        refresh.clicked.connect(self._refresh_album_wall)
        raw_analyse=QPushButton("Improve sonic layout")
        raw_analyse.clicked.connect(self._analyse_library_for_album_wall)
        recover_covers=QPushButton("Find missing covers")
        recover_covers.clicked.connect(
            lambda:self.album_wall.request_missing_covers()
            if hasattr(self,"album_wall") else None
        )
        power.addWidget(QLabel("Wall options"))
        power.addWidget(refresh)
        power.addWidget(raw_analyse)
        power.addWidget(recover_covers)
        power.addStretch(1)
        self.album_wall_power_panel.hide()
        l.addWidget(self.album_wall_power_panel)

        self.album_wall=AlbumWallWidget(self)
        self.album_wall.albumSelected.connect(self._album_wall_selection_changed)
        self.album_wall.albumActivated.connect(self._play_album_wall_album)
        self.album_wall.artworkRequested.connect(self._album_wall_artwork_requested)
        self.album_wall.onlineArtworkRequested.connect(self._album_wall_online_artwork_requested)
        l.addWidget(self.album_wall,1)

    def _album_wall_selection_changed(self, album: object) -> None:
        enabled=isinstance(album,dict) and bool(album)
        self.album_wall_play_button.setEnabled(enabled)
        self.album_wall_queue_button.setEnabled(enabled)


    def _toggle_album_wall_tools(self) -> None:
        visible=not self.album_wall_power_panel.isVisible()
        self.album_wall_power_panel.setVisible(visible)

    def _build_playlists(self):
        l=self._page_layout(
            "playlists",
            "Playlists",
            "Keep playlists here, whether you made them elsewhere or built them in Melodex.",
        )

        top=QHBoxLayout()
        imp=QPushButton("Import playlist…")
        imp.setObjectName("primaryButton")
        imp.clicked.connect(self._import_playlist_file)
        ai=QPushButton("Paste from AI…")
        ai.setObjectName("secondaryButton")
        ai.clicked.connect(self._open_ai_playlist_import)
        set_help(
            imp,
            "Import playlist",
            "Import XSPF, M3U or M3U8. Melodex keeps unmatched requests so they can be resolved later.",
        )
        set_help(
            ai,
            "Paste from AI",
            "Paste a playlist generated in ChatGPT, Claude, Gemini or another AI. No AI account is connected and the pasted text is not sent back to an AI service.",
        )
        top.addWidget(imp)
        top.addWidget(ai)
        top.addStretch(1)
        l.addLayout(top)

        self.playlists_stack=QStackedWidget()
        self.playlists_list=QListWidget()
        self.playlists_list.itemDoubleClicked.connect(self._play_saved_playlist)
        self.playlists_list.itemSelectionChanged.connect(self._playlist_selection_changed)
        self.playlists_empty=EmptyState(
            "No playlists yet",
            "Import a playlist, or save music from your current queue.",
            "Import playlist",
        )
        self.playlists_empty.actionRequested.connect(self._import_playlist_file)
        self.playlists_stack.addWidget(self.playlists_empty)
        self.playlists_stack.addWidget(self.playlists_list)
        l.addWidget(self.playlists_stack,1)

        row=QHBoxLayout()
        self.playlist_export_button=QPushButton("Export selected…")
        self.playlist_export_button.clicked.connect(self._export_selected_playlist)
        self.playlist_export_button.setEnabled(False)
        expq=QPushButton("Export current queue…")
        expq.clicked.connect(self._export_queue)
        row.addWidget(self.playlist_export_button)
        row.addWidget(expq)
        row.addStretch(1)
        l.addLayout(row)

    def _playlist_selection_changed(self) -> None:
        item=self.playlists_list.currentItem() if hasattr(self,"playlists_list") else None
        record=item.data(Qt.UserRole) if item else None
        if hasattr(self,"playlist_export_button"):
            self.playlist_export_button.setEnabled(isinstance(record,dict))


    def _build_moments(self):
        l=self._page_layout(
            "moments",
            "Moments",
            "Bookmarks inside songs — the exact musical moments you wanted to remember, not just a list of favourite tracks.",
        )
        note=QLabel(
            "While something is playing, use the current-track actions to remember a moment. Double-click a saved moment to play from that point."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#8f9bad")
        l.addWidget(note)
        self.moments_stack=QStackedWidget()
        self.moments_list=QListWidget()
        self.moments_list.itemDoubleClicked.connect(self._play_saved_moment)
        self.moments_empty=EmptyState(
            "No moments saved yet",
            "When a song reaches a part you want to remember, save that exact point and it will appear here.",
            "Open Now Playing",
        )
        self.moments_empty.actionRequested.connect(lambda:self.open_page("now_playing"))
        self.moments_stack.addWidget(self.moments_list)
        self.moments_stack.addWidget(self.moments_empty)
        l.addWidget(self.moments_stack,1)


    def _build_ask(self):
        l=self._page_layout("ask","Ask Melodex","Optional. Connect OpenWebUI, Ollama or another compatible model. The player still works without any LLM.")
        self.chat=QTextEdit(); self.chat.setReadOnly(True); l.addWidget(self.chat,1)
        row=QHBoxLayout(); self.ask_box=QLineEdit(); self.ask_box.setPlaceholderText("e.g. Keep this mood but make the next hour stranger"); self.ask_box.returnPressed.connect(self._ask); ask=QPushButton("Ask"); ask.clicked.connect(self._ask); cfg=QPushButton("Connect LLM…"); cfg.clicked.connect(self._llm_settings_dialog); row.addWidget(self.ask_box,1); row.addWidget(ask); row.addWidget(cfg); l.addLayout(row)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self.playback_feature.set_window_minimized(self.isMinimized())

    def open_page(self, name: str):
        self.navigation.open_page(name)

    def enter_chiasm_mode(self) -> None:
        """Show Chiasm as the app surface while retaining host services privately."""
        self.navigation.ensure_lazy_page_built("chiasm")
        page = self.chiasm_feature.page
        self.stack.removeWidget(page)
        inherited_shell = self.takeCentralWidget()
        self._inherited_shell_widget = inherited_shell
        if inherited_shell is not None:
            inherited_shell.hide()
        self.menuBar().hide()
        for action in self.findChildren(QAction):
            action.setEnabled(False)
        for shortcut in self.findChildren(QShortcut):
            shortcut.setEnabled(False)
        self.setCentralWidget(page)
        page.show()
        self.setWindowTitle("Chiasm")
        self.statusBar().hide()
        self.shortcut_palette.setEnabled(False)
        self.shortcut_palette_mac.setEnabled(False)
        self.resize(1440, 900)

    def _refresh_explore_visibility(self) -> None:
        has_library=bool(self.providers.local_catalog_count())
        if hasattr(self,"explore_wall_card"):
            self.explore_wall_card.setVisible(has_library)
        if hasattr(self,"explore_map_card"):
            self.explore_map_card.setVisible(has_library)
        if hasattr(self,"explore_try_section"):
            self.explore_try_section.setVisible(has_library)
        if hasattr(self,"explore_similar_button"):
            self.explore_similar_button.setEnabled(
                bool(self.playback_feature.current_track())
            )
        if hasattr(self,"explore_ask_button"):
            self.explore_ask_button.setVisible(
                has_library and self.power_toggle.isChecked()
            )

    def _show_home(self):
        self._refresh_taste()
        count=self.providers.local_catalog_count()
        has_library=bool(count)
        if hasattr(self,"home_explanation"):
            self.home_explanation.setText(
                "A session from your library, shaped as you listen."
                if has_library
                else "Add a folder of music. Your files stay where they are."
            )
        if hasattr(self,"home_moods_widget"):
            self.home_moods_widget.setVisible(has_library)
        if hasattr(self,"home_explore_heading"):
            self.home_explore_heading.setVisible(has_library)
        if hasattr(self,"home_explore_widget"):
            self.home_explore_widget.setVisible(has_library)
        if hasattr(self,"home_status"):
            self.home_status.setVisible(has_library)
            if has_library:
                self.home_status.setText(
                    f"{count:,} track{'s' if count != 1 else ''} in your library"
                )
        if hasattr(self,"home_primary_button"):
            if count:
                self.home_primary_button.setText("▶  Play something")
                set_help(
                    self.home_primary_button,
                    "Play something",
                    "Builds a balanced one-hour session from your local library using your listening history and Flow when available.",
                )
            else:
                self.home_primary_button.setText("+  Add my music")
                set_help(
                    self.home_primary_button,
                    "Add your music",
                    "Choose a folder of music on this computer. Melodex indexes it locally and does not upload your audio.",
                )
        self._refresh_home_continue()

    def _home_primary_action(self) -> None:
        if self.providers.local_catalog_count():
            self._play_for_me("balanced",60,0.35)
        else:
            self._choose_music_folder()

    def _refresh_home_continue(self) -> None:
        if not hasattr(self,"home_continue_cover"):
            return
        recent = self.state.recent_tracks(1)
        track = dict(
            self.playback_feature.current_track()
            or (recent[0] if recent else {})
        )
        self.home_recent_track = track
        if not track:
            if hasattr(self,"home_continue_heading"):
                self.home_continue_heading.hide()
            self.home_continue.hide()
            self.home_continue_cover.set_cover("",title="Your music",key="empty-home")
            self.home_continue_title.setText("Nothing played yet")
            self.home_continue_meta.setText(
                "Choose Play something or browse My Music. Your recent listening will appear here."
            )
            self.home_continue_button.setEnabled(False)
            return
        if hasattr(self,"home_continue_heading"):
            self.home_continue_heading.show()
        self.home_continue.show()
        title=str(track.get("title") or "Unknown track")
        artist=str(track.get("artist") or "Unknown artist")
        album=str(track.get("album") or "")
        self.home_continue_title.setText(title)
        self.home_continue_meta.setText(artist + (f"  ·  {album}" if album else ""))
        self.home_continue_button.setEnabled(True)
        self.home_continue_cover.set_cover("",title=album or title,key=UserState.track_key(track))
        token=UserState.track_key(track)
        self._run_async(
            lambda:self.metadata.local_artwork(track),
            lambda result:self._home_continue_art_loaded(token,result),
        priority="visible", task_name="home-artwork", replace_key="home-artwork")

    def _home_continue_art_loaded(self, token: str, result: object) -> None:
        current=UserState.track_key(dict(getattr(self,"home_recent_track",{}) or {}))
        if token!=current or not isinstance(result,dict):
            return
        path=str(result.get("path") or "")
        self.home_continue_cover.set_cover(
            path,
            title=str(self.home_recent_track.get("album") or self.home_recent_track.get("title") or ""),
            key=token,
        )
        current=dict(self.playback_feature.current_track() or {})
        if current and token==UserState.track_key(current):
            self.playback_feature.apply_cached_artwork(token, path)

    def _home_continue_play(self) -> None:
        track=dict(getattr(self,"home_recent_track",{}) or {})
        if track:
            self.player.set_queue([track],0,True)

    def _power_changed(self, _, announce: bool = True):
        enabled = self.power_toggle.isChecked()
        self.state.set_bool("power_tools",enabled)
        if hasattr(self, "sources_feature"):
            self.sources_feature.set_power_tools_visible(enabled)
        if hasattr(self, "explore_ask_button"):
            self.explore_ask_button.setVisible(
                enabled and bool(self.providers.local_catalog_count())
            )
        if hasattr(self, "playback_feature"):
            self.playback_feature.set_power_tools_visible(enabled)
        # Spatial browsing uses its own progressive disclosures. Global Power
        # tools must not cover Album Wall or Music Map with controls.
        if announce:
            self.statusBar().showMessage(
                "Power tools enabled" if enabled else "Power tools hidden",
                2500,
            )

    def _open_command_palette(self) -> None:
        actions=[
            ("Home","Start listening and see recent music.",lambda:self.open_page("home")),
            ("My Music","Browse albums, artists and tracks.",lambda:self.open_page("library")),
            ("Explore","Search, Album Wall and Music Map.",lambda:self.open_page("explore")),
            ("Search everything","Search all connected music sources.",lambda:self.open_page("discover")),
            ("Album Wall","Browse your collection spatially.",lambda:self.open_page("album_wall")),
            ("Chiasm","Listen from the spatial field.",lambda:self.open_page("chiasm")),
            ("Music Map","Explore track relationships and routes.",lambda:self.open_page("music_map")),
            ("Now Playing","Open artwork, lyrics and visuals.",lambda:self.open_page("now_playing")),
            ("Journeys","Open saved listening journeys.",lambda:self.open_page("journeys")),
            ("Playlists","Open saved and imported playlists.",lambda:self.open_page("playlists")),
            ("Sources & plugins","Manage where Melodex finds music.",lambda:self.open_page("sources")),
            ("Ask Melodex","Open optional natural-language control.",lambda:self.open_page("ask")),
            ("Add music folder","Choose a local music folder.",self._choose_music_folder),
            ("Analyse local library","Analyse sonic features locally for Flow and maps.",self._analyse_library_for_intelligence),
        ]
        CommandPaletteDialog(actions,self).exec()

    def _refresh_source_combo(self):
        current=self.search_source.currentData(); self.search_source.clear(); self.search_source.addItem("All sources","all")
        for pid in self.providers.searchable_provider_ids():
            p=self.providers.providers[pid]
            self.search_source.addItem(p.info.name,pid)
        idx=self.search_source.findData(current); self.search_source.setCurrentIndex(idx if idx>=0 else 0)

    def _open_provider_search(self, provider_id: str) -> None:
        self.open_page("discover")
        self._refresh_source_combo()
        index=self.search_source.findData(str(provider_id or ""))
        if index >= 0:
            self.search_source.setCurrentIndex(index)
        self.search_box.setFocus()
        provider=self.providers.providers.get(provider_id)
        name=provider.info.name if provider is not None else provider_id
        self.statusBar().showMessage(
            f"Search ready · results will come from {name}",
            4500,
        )

    def _use_extension(self, extension_id: str) -> None:
        row=self.source_policy.extension_record(extension_id)
        capabilities=[str(x) for x in list(row.get("capabilities") or []) if x]
        name=str(row.get("name") or extension_id)

        if "library_suggestions" in capabilities:
            self.open_page("for_you")
            self.statusBar().showMessage(
                f"{name} participates here · use More like current, Forgotten favourites, Bridge current → next or Find a detour",
                7000,
            )
            return
        if "artwork" in capabilities:
            self.open_page("library")
            self.statusBar().showMessage(
                f"{name} is used by artwork enrichment · choose Find missing artwork in My Music",
                6500,
            )
            return
        if any(cap in capabilities for cap in ("lyrics","context","metadata","identity")):
            self.open_page("now_playing")
            labels=", ".join(self.source_policy.capability_label(x) for x in capabilities)
            self.statusBar().showMessage(
                f"{name} provides {labels} automatically for the current track",
                6500,
            )
            return

        QMessageBox.information(
            self,
            "Plugin is active",
            f"{name} is enabled. It does not declare a separate user-facing action; Melodex will call it when one of its capabilities is needed.",
        )

    def _refresh_library(self):
        catalog=self.providers.local_catalog()
        if hasattr(self,"artwork_plugin_presence"):
            self.artwork_plugin_presence.setVisible(bool(catalog))
        if hasattr(self,"library_browser"):
            self.library_browser.set_catalog(
                catalog,
                revision=self.providers.local_catalog_revision(),
            )

    def _play_library_track(self, track: object) -> None:
        if not isinstance(track,dict):
            return
        tracks=self.providers.local_catalog()
        tid=str(track.get("track_id") or "")
        index=next(
            (i for i,item in enumerate(tracks) if str(item.get("track_id") or "")==tid),
            0,
        )
        self.player.set_queue(tracks,index,True)

    def _play_library_artist(self, artist: object) -> None:
        if not isinstance(artist,dict):
            return
        tracks=[dict(x) for x in list(artist.get("tracks") or []) if isinstance(x,dict)]
        if tracks:
            self.player.set_queue(tracks,0,True)

    def _queue_library_track(self, track: object) -> None:
        if not isinstance(track,dict):
            return
        if not self.player.queue:
            self.player.set_queue([dict(track)],0,False)
        else:
            self.player.append_queue([dict(track)],autoplay=False)
        self.statusBar().showMessage(
            f"Queued {track.get('title') or 'track'}",
            3000,
        )

    def _edit_local_metadata(self, track: object) -> None:
        if not isinstance(track,dict) or not str(track.get("local_path") or "").strip():
            QMessageBox.information(
                self,
                "Local music only",
                "Metadata corrections are currently available for music stored on this computer.",
            )
            return

        original=dict(track)
        dialog=QDialog(self)
        dialog.setWindowTitle("Correct track details")
        dialog.resize(520,360)
        layout=QVBoxLayout(dialog)
        layout.setContentsMargins(22,20,22,18)
        title=QLabel("Correct track details")
        title.setStyleSheet("font-size:20px;font-weight:700")
        layout.addWidget(title)
        note=QLabel(
            "These corrections are stored by Melodex and survive rescans. "
            "Your original audio file and its embedded tags are not changed."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9aa4b8")
        layout.addWidget(note)

        form=QFormLayout()
        fields={}
        for key,label in (
            ("artist","Artist"),
            ("title","Track title"),
            ("album","Album"),
            ("album_artist","Album artist"),
            ("year","Year"),
            ("genre","Genre"),
        ):
            edit=QLineEdit()
            value=str(original.get(key) or "")
            if key=="artist" and value.casefold().strip()=="unknown artist":
                value=""
            edit.setText(value)
            fields[key]=edit
            form.addRow(label+":",edit)
        layout.addLayout(form)

        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        reset=buttons.addButton("Use file tags again",QDialogButtonBox.ResetRole)
        set_help(
            reset,
            "Remove Melodex correction",
            "Forget the local correction for this file and use its embedded/file metadata again.",
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        reset.clicked.connect(lambda:self._reset_local_metadata_dialog(dialog,original))
        layout.addWidget(buttons)

        if dialog.exec()!=QDialog.Accepted:
            return

        changes={key:edit.text().strip() for key,edit in fields.items()}
        try:
            updated=self.providers.update_local_metadata(original,changes)
        except Exception as exc:
            QMessageBox.warning(self,"Could not save correction",str(exc))
            return
        self._apply_local_metadata_update(original,updated)
        self.statusBar().showMessage(
            f"Saved Melodex metadata correction for {updated.get('title') or original.get('title') or 'track'}",
            4500,
        )

    def _reset_local_metadata_dialog(self, dialog: QDialog, track: dict[str,Any]) -> None:
        if self.providers.clear_local_metadata_correction(track):
            self.statusBar().showMessage(
                "Removed Melodex metadata correction · refreshing tags in the background…"
            )
            self._start_local_scan("metadata reset")
        dialog.reject()

    def _apply_local_metadata_update(
        self,
        original: dict[str,Any],
        updated: dict[str,Any],
    ) -> None:
        path=str(original.get("local_path") or "")
        self.player.merge_queue_items(
            lambda item: str(item.get("local_path") or "")==path,
            updated,
        )

        current=dict(self.playback_feature.current_track() or {})
        if str(current.get("local_path") or "")==path:
            self.playback_feature.merge_current_track(updated)
        self._refresh_library()

    def _queue_album_data(self, album: object) -> None:
        if not isinstance(album,dict):
            return
        tracks=[dict(x) for x in list(album.get("tracks") or []) if isinstance(x,dict)]
        if not tracks:
            return
        if not self.player.queue:
            self.player.set_queue(tracks,0,False)
        else:
            self.player.append_queue(tracks,autoplay=False)
        self.statusBar().showMessage(
            f"Queued {len(tracks)} tracks from {album.get('title') or 'album'}",
            3500,
        )

    def _library_artwork_requested(self, requests: object) -> None:
        rows=[dict(x) for x in list(requests or []) if isinstance(x,dict)]
        if not rows:
            return
        keys=[str(row.get("key") or "") for row in rows if str(row.get("key") or "")]
        def load():
            result={}
            for row in rows:
                key=str(row.get("key") or "")
                track=dict(row.get("track") or {})
                if key and track:
                    info=self.metadata.local_artwork(track)
                    result[key]=str(info.get("path") or "")
            return result
        def failed(error: str) -> None:
            self.library_browser.cached_artwork_batch_failed("albums",keys)
            self.statusBar().showMessage(
                f"Cached artwork refresh paused · {error}",
                3500,
            )
        self._run_async(load,self.library_browser.set_artwork,failed, priority="visible", task_name="library-cached-artwork")

    def _library_online_artwork_requested(self, requests: object) -> None:
        rows=[dict(x) for x in list(requests or []) if isinstance(x,dict)]
        if not rows:
            return

        self.statusBar().showMessage(
            f"Finding album artwork · {len(rows)} at a time"
        )

        def lookup_one(row: dict[str,Any]) -> dict[str,Any]:
            key=str(row.get("key") or "")
            track=dict(row.get("track") or {})
            if not key or not track:
                return {"key":key,"path":"","status":"error","error":"Missing album lookup data"}
            try:
                local=self.metadata.local_artwork(track)
                path=str(local.get("path") or "")
                artwork_info=dict(local)
                if not path:
                    identity=self.metadata.identify(track)
                    artwork_info=self.metadata.artwork(track,identity)
                    path=str(artwork_info.get("path") or "")
                if path:
                    match_info=(
                        dict(artwork_info.get("match") or {})
                        if isinstance(artwork_info.get("match"),dict)
                        else {}
                    )
                    for sibling in list(row.get("tracks") or []):
                        if not isinstance(sibling,dict):
                            continue
                        self.metadata.remember_artwork(
                            sibling,
                            path,
                            source=str(artwork_info.get("source") or ""),
                            source_url=str(artwork_info.get("source_url") or ""),
                            attribution=str(artwork_info.get("attribution") or ""),
                            license_name=str(
                                artwork_info.get("license_name")
                                or artwork_info.get("license")
                                or ""
                            ),
                            match_method=str(match_info.get("method") or ""),
                            match_confidence=(
                                float(match_info.get("confidence"))
                                if match_info.get("confidence") is not None
                                else None
                            ),
                        )
                    return {
                        "key":key,
                        "path":path,
                        "status":"found",
                        "source":str(artwork_info.get("source") or ""),
                    }
                return {"key":key,"path":"","status":"no_match","error":""}
            except Exception as exc:
                return {"key":key,"path":"","status":"error","error":str(exc)}

        def load():
            workers=max(1,min(4,len(rows)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                return list(pool.map(lookup_one,rows))

        def apply(result):
            outcomes=[dict(x) for x in list(result or []) if isinstance(x,dict)]
            self.library_browser.set_artwork({
                str(row.get("key") or ""):str(row.get("path") or "")
                for row in outcomes
                if str(row.get("path") or "")
            })
            self.library_browser.finish_album_artwork_lookup_batch(outcomes)
            snapshot=self.library_browser.artwork_lookup_snapshot()
            self.statusBar().showMessage(
                "Album artwork · "
                f"{snapshot.get('completed',0)}/{snapshot.get('total',0)} · "
                f"found {snapshot.get('found',0)} · "
                f"no match {snapshot.get('skipped',0)} · "
                f"failed {snapshot.get('failed',0)}",
                5000 if not snapshot.get("active") else 0,
            )

        def failed(error):
            outcomes=[
                {
                    "key":str(row.get("key") or ""),
                    "path":"",
                    "status":"error",
                    "error":str(error),
                }
                for row in rows
            ]
            self.library_browser.finish_album_artwork_lookup_batch(outcomes)
            self.statusBar().showMessage(
                f"Album artwork batch failed · {error}",
                5000,
            )

        self._run_async(load,apply,failed, priority="background", task_name="library-online-artwork")

    def _choose_artist_photo_file(self, artist: object) -> None:
        if not isinstance(artist,dict):
            return
        name=str(artist.get("name") or "Artist").strip() or "Artist"
        path,_ = QFileDialog.getOpenFileName(
            self,
            f"Choose photo for {name}",
            "",
            "Images (*.jpg *.jpeg *.png *.webp);;All files (*)",
        )
        if not path:
            return
        remembered=self.metadata.remember_artist_photo_file(
            {"name":name},
            path,
        )
        saved=str(remembered.get("path") or "")
        if not saved:
            QMessageBox.warning(
                self,
                "Could not use image",
                "Melodex could not copy that image into its artwork cache.",
            )
            return
        key=str(artist.get("key") or "")
        if key:
            self.library_browser.set_artist_images({key:saved})
        self.statusBar().showMessage(
            f"Saved artist photo for {name}",
            4500,
        )

    def _library_cached_artist_images_requested(self, requests: object) -> None:
        rows=[dict(x) for x in list(requests or []) if isinstance(x,dict)]
        if not rows:
            return

        keys=[str(row.get("key") or "") for row in rows if str(row.get("key") or "")]
        def load():
            result={}
            for row in rows:
                key=str(row.get("key") or "")
                artist_name=str(row.get("artist") or "")
                if key and artist_name:
                    cached=self.metadata.cached_artist_photo({"name":artist_name})
                    result[key]=str(cached.get("path") or "")
            return result

        def failed(error: str) -> None:
            self.library_browser.cached_artwork_batch_failed("artists",keys)
            self.statusBar().showMessage(
                f"Cached artist-photo refresh paused · {error}",
                3500,
            )

        self._run_async(load,self.library_browser.set_artist_images,failed, priority="visible", task_name="library-cached-artist-photo")

    def _library_artist_images_requested(self, requests: object) -> None:
        rows=[dict(x) for x in list(requests or []) if isinstance(x,dict)]
        if not rows:
            return

        self.statusBar().showMessage(
            f"Finding artist photos · {len(rows)} at a time"
        )

        def lookup_one(row: dict[str,Any]) -> dict[str,Any]:
            key=str(row.get("key") or "")
            artist_name=str(row.get("artist") or "")
            track=dict(row.get("track") or {})
            if not key or not artist_name or not track:
                return {"key":key,"path":"","status":"error","error":"Missing artist lookup data"}
            try:
                cached=self.metadata.cached_artist_photo({"name":artist_name})
                path=str(cached.get("path") or "")
                if not path:
                    artist_mbid=str(
                        track.get("musicbrainz_artist_id")
                        or track.get("artist_mbid")
                        or ""
                    ).strip()
                    if artist_mbid:
                        info=self.metadata.artist_info(artist_mbid)
                    else:
                        info=self.metadata.resolve_artist(artist_name)
                    if info:
                        if not info.get("name"):
                            info["name"]=artist_name
                        photo=self.metadata.artist_photo(info)
                        path=str(photo.get("path") or "")
                return {
                    "key":key,
                    "path":path,
                    "status":"found" if path else "no_match",
                    "error":"",
                }
            except Exception as exc:
                return {"key":key,"path":"","status":"error","error":str(exc)}

        def load():
            workers=max(1,min(4,len(rows)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                return list(pool.map(lookup_one,rows))

        def apply(result):
            outcomes=[dict(x) for x in list(result or []) if isinstance(x,dict)]
            self.library_browser.set_artist_images({
                str(row.get("key") or ""):str(row.get("path") or "")
                for row in outcomes
                if str(row.get("path") or "")
            })
            self.library_browser.finish_artist_image_lookup_batch(outcomes)
            snapshot=self.library_browser.artwork_lookup_snapshot()
            self.statusBar().showMessage(
                "Artist photos · "
                f"{snapshot.get('completed',0)}/{snapshot.get('total',0)} · "
                f"found {snapshot.get('found',0)} · "
                f"no match {snapshot.get('skipped',0)} · "
                f"failed {snapshot.get('failed',0)}",
                5000 if not snapshot.get("active") else 0,
            )

        def failed(error):
            outcomes=[
                {
                    "key":str(row.get("key") or ""),
                    "path":"",
                    "status":"error",
                    "error":str(error),
                }
                for row in rows
            ]
            self.library_browser.finish_artist_image_lookup_batch(outcomes)
            self.statusBar().showMessage(
                f"Artist photo batch failed · {error}",
                5000,
            )

        self._run_async(load,apply,failed, priority="background", task_name="library-online-artist-photo")

    def _refresh_playlists(self):
        self.playlists_list.clear()
        records=self.state.playlists()
        for p in records:
            name=str(p.get("name") or "Playlist")
            description=str(p.get("description") or "").strip()
            count=int(p.get("track_count") or 0)
            source=str(p.get("source") or "")
            subtitle=f"{count} track{'s' if count!=1 else ''}"
            if source:
                subtitle+=f" · {source.replace('import:','imported ')}"
            if description:
                subtitle+=f"\n{description}"
            item=QListWidgetItem(f"{name}\n{subtitle}")
            item.setData(Qt.UserRole,p)
            self.playlists_list.addItem(item)
        if hasattr(self,"playlists_stack"):
            self.playlists_stack.setCurrentWidget(
                self.playlists_list if records else self.playlists_empty
            )
        self._playlist_selection_changed()

    @staticmethod
    def _playlist_tracks(record):
        payload=dict(record.get("payload") or {})
        requested=payload.get("requested_tracks")
        if isinstance(requested,list):return [dict(x) for x in requested if isinstance(x,dict)]
        return [dict(x) for x in list(payload.get("tracks") or payload.get("rows") or []) if isinstance(x,dict)]

    def _play_saved_playlist(self,item):
        record=dict(item.data(Qt.UserRole) or {}); tracks=self._playlist_tracks(record)
        if not tracks:
            self.statusBar().showMessage("This playlist has no tracks",3000); return
        self.statusBar().showMessage("Resolving playlist across connected sources…")
        self._run_async(lambda:self.providers.resolve_playlist(tracks),self._start_resolved_playlist, priority="foreground", task_name="playlist-resolve")

    def _start_resolved_playlist(self,result):
        tracks=list(result.get("tracks") or []); unresolved=list(result.get("unresolved") or [])
        if tracks:self.player.set_queue(tracks,0,True)
        msg=f"Playing {len(tracks)} matched tracks"
        if unresolved:msg+=f" · {len(unresolved)} could not be matched"
        self.statusBar().showMessage(msg,6000)

    def _import_playlist_file(self):
        from .playlist_io import load_playlist
        filename,_=QFileDialog.getOpenFileName(self,"Import playlist",filter="Playlists (*.xspf *.m3u *.m3u8);;XSPF (*.xspf);;M3U/M3U8 (*.m3u *.m3u8)")
        if not filename:return
        try:data=load_playlist(Path(filename))
        except Exception as exc:QMessageBox.warning(self,"Could not import playlist",str(exc)); return
        requested=[dict(x) for x in list(data.get("tracks") or []) if isinstance(x,dict)]
        if not requested:QMessageBox.information(self,"Empty playlist","No tracks were found in this playlist."); return
        playlist_id=str(uuid.uuid4()); name=str(data.get("name") or Path(filename).stem); description=str(data.get("description") or "")
        self.statusBar().showMessage(f"Importing and matching {len(requested)} tracks…")
        self._run_async(lambda:self.providers.resolve_playlist(requested),lambda result:self._finish_playlist_file_import(playlist_id,name,description,str(data.get("format") or "playlist"),requested,result), priority="foreground", task_name="playlist-import-resolve")

    def _finish_playlist_file_import(self,playlist_id,name,description,fmt,requested,result):
        from .playlist_io import save_playlist
        tracks=list(result.get("tracks") or []); unresolved=list(result.get("unresolved") or [])
        payload={"tracks":tracks,"unresolved":unresolved,"requested_tracks":requested,"format":fmt}
        self.state.save_playlist(playlist_id,name,description,f"import:{fmt}",payload); self._refresh_playlists()
        msg=f"Imported {name}: {len(tracks)} playable"
        if unresolved:msg+=f" · {len(unresolved)} unresolved (kept for future matching)"
        self.statusBar().showMessage(msg,7000)

    def _open_ai_playlist_import(self):
        from .playlist_io import load_playlist, parse_playlist_text
        dialog=QDialog(self); dialog.setWindowTitle("Import an AI playlist"); dialog.resize(900,650)
        layout=QVBoxLayout(dialog); layout.setContentsMargins(24,22,24,20); layout.setSpacing(14)
        title=QLabel("Import an AI playlist"); title.setStyleSheet("font-size: 25px; font-weight: 700;")
        subtitle=QLabel("Paste a playlist from ChatGPT, Claude, Gemini or another AI. JSON, Markdown lists or tables, TXT, CSV and M3U/M3U8 are supported.")
        subtitle.setWordWrap(True); subtitle.setStyleSheet("color: #9aa4b8; font-size: 14px;")
        layout.addWidget(title); layout.addWidget(subtitle)
        editor=QPlainTextEdit(); editor.setPlaceholderText("Paste the playlist here…"); editor.setMinimumHeight(300); layout.addWidget(editor,1)
        actions=QHBoxLayout()
        copy_prompt=QPushButton("Copy ChatGPT Prompt")
        import_file=QPushButton("Import File…")
        paste_clipboard=QPushButton("Paste Clipboard")
        actions.addWidget(copy_prompt); actions.addWidget(import_file); actions.addWidget(paste_clipboard); actions.addStretch(1)
        layout.insertLayout(2,actions)
        privacy=QLabel("No AI connection is needed, and Melodex does not send this text to an AI service. Track matching uses your connected music sources.")
        privacy.setWordWrap(True); privacy.setStyleSheet("color: #9aa4b8;")
        layout.addWidget(privacy)
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel)
        analyze=buttons.addButton("Analyse Playlist",QDialogButtonBox.AcceptRole)
        layout.addWidget(buttons)

        prompt=("Create a playlist of real, released tracks. Return valid JSON only, using this structure:\n"
                '{\n  "melodex_playlist": 1,\n  "name": "Playlist name",\n'
                '  "description": "Short description",\n  "tracks": [\n'
                '    {"artist": "Artist name", "title": "Exact track title", "album": "Album when known", "year": 2006, "reason": "Optional short reason"}\n'
                '  ]\n}\nUse canonical artist and track names, and keep the tracks in the intended listening order. Do not add commentary outside the JSON.')

        def do_copy_prompt():
            QApplication.clipboard().setText(prompt)
            self.statusBar().showMessage("Playlist prompt copied. Paste it into your AI chat.",5000)

        def do_paste_clipboard():
            value=QApplication.clipboard().text()
            if not value.strip():
                QMessageBox.information(dialog,"Clipboard is empty","Copy a playlist from your AI chat first, then choose Paste Clipboard.")
                return
            editor.setPlainText(value)

        def do_import_file():
            filename,_=QFileDialog.getOpenFileName(dialog,"Import playlist",filter="Playlist/text files (*.json *.txt *.csv *.tsv *.xspf *.m3u *.m3u8);;All files (*)")
            if not filename:return
            path=Path(filename)
            try:
                if path.suffix.lower() in {".xspf",".m3u",".m3u8"}:
                    data=load_playlist(path)
                else:
                    data=parse_playlist_text(path.read_text("utf-8-sig",errors="replace"))
                    if data.get("name") in {"Pasted playlist","AI playlist"}:
                        data["name"]=path.stem
                editor.setPlainText(json.dumps(data,ensure_ascii=False,indent=2))
            except Exception as exc:
                QMessageBox.warning(dialog,"Could not import playlist",str(exc))

        def do_analyze():
            try:
                data=parse_playlist_text(editor.toPlainText())
            except Exception as exc:
                QMessageBox.warning(dialog,"Could not read playlist",str(exc)); return
            dialog.accept()
            self._import_ai_playlist(data,source="ai-paste")

        copy_prompt.clicked.connect(do_copy_prompt)
        import_file.clicked.connect(do_import_file)
        paste_clipboard.clicked.connect(do_paste_clipboard)
        buttons.rejected.connect(dialog.reject)
        analyze.clicked.connect(do_analyze)
        dialog.exec()

    def _playlist_export_path(self,title):
        path,chosen=QFileDialog.getSaveFileName(self,title,filter="XSPF Playlist (*.xspf);;M3U8 Playlist (*.m3u8);;M3U Playlist (*.m3u)")
        if not path:return None
        p=Path(path)
        if not p.suffix:
            suffix=".m3u8" if "M3U8" in chosen else ".m3u" if "M3U Playlist" in chosen else ".xspf"
            p=p.with_suffix(suffix)
        return p

    def _export_selected_playlist(self):
        from .playlist_io import save_playlist
        item=self.playlists_list.currentItem()
        if not item:self.statusBar().showMessage("Select a playlist first",3000); return
        record=dict(item.data(Qt.UserRole) or {}); tracks=self._playlist_tracks(record)
        if not tracks:self.statusBar().showMessage("This playlist has no tracks",3000); return
        path=self._playlist_export_path("Export playlist")
        if not path:return
        try:save_playlist(path,tracks,str(record.get("name") or "Melodex playlist"),str(record.get("description") or "")); self.statusBar().showMessage(f"Exported {path.name}",5000)
        except Exception as exc:QMessageBox.warning(self,"Could not export playlist",str(exc))

    def _export_queue(self):
        from .playlist_io import save_playlist
        tracks=[dict(x) for x in self.player.queue if isinstance(x,dict)]
        if not tracks:self.statusBar().showMessage("The queue is empty",3000); return
        path=self._playlist_export_path("Export queue")
        if not path:return
        try:save_playlist(path,tracks,"Melodex queue",""); self.statusBar().showMessage(f"Exported {path.name}",5000)
        except Exception as exc:QMessageBox.warning(self,"Could not export queue",str(exc))

    def _refresh_moments(self):
        self.moments_list.clear()
        records=self.state.moments()
        for m in records:
            t=m.get("track") if isinstance(m.get("track"),dict) else {}
            if not t:
                try:
                    t=json.loads(m.get("track_json") or "{}")
                except Exception:
                    t={}
            sec=int(m.get("position_ms",0))//1000
            label=str(m.get("label") or "").strip()
            title=f"{t.get('title') or 'Unknown track'} — {t.get('artist') or 'Unknown artist'}"
            subtitle=f"{sec//60}:{sec%60:02d}" + (f" · {label}" if label else "")
            item=QListWidgetItem(f"{title}\n{subtitle}")
            item.setData(Qt.UserRole,dict(m))
            self.moments_list.addItem(item)
        if hasattr(self,"moments_stack"):
            self.moments_stack.setCurrentWidget(
                self.moments_list if records else self.moments_empty
            )

    def _play_saved_moment(self, item: QListWidgetItem) -> None:
        data=item.data(Qt.UserRole)
        if not isinstance(data,dict):
            return
        track=data.get("track") if isinstance(data.get("track"),dict) else {}
        if not track:
            return
        position=max(0,int(data.get("position_ms") or 0))
        self.player.set_queue([dict(track)],0,True)
        if position:
            QTimer.singleShot(700,lambda:self.player.seek(position))

    def _refresh_taste(self):
        if not hasattr(self,"taste_label"):
            return
        s=self.state.taste_summary(); self.taste_label.setText(f"Taste memory: {s.get('tracks',0)} tracks learned · {s.get('artists',0)} artists · completion rate {float(s.get('completion_rate',0))*100:.0f}%")

    # ------------------------------- sources/search
    def _choose_music_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Choose a music folder")
        if not folder:
            return
        roots=self.providers.local_roots()
        p=Path(folder)
        if p not in roots:
            roots.append(p)
        self.providers.configure_local_roots(roots)
        if self.current_page == "chiasm":
            self.chiasm_feature._status("Indexing collection…")
        came_from_home = self.current_page == "home"
        self._start_local_scan("folder added")
        if came_from_home:
            self.open_page("library")

    def _rescan(self):
        self._start_local_scan("rescan")

    def _refresh_background_scan_activity(self) -> None:
        if not self.local_scan.active:
            self.background_activity.hide()
            self._background_activity_timer.stop()
            return

        runner=self.local_scan.runner
        view=scan_activity_state(
            self._local_scan_last_progress,
            elapsed_seconds=(
                time.monotonic() - self._local_scan_started_at
                if self._local_scan_started_at
                else 0.0
            ),
            paused=bool(runner is not None and runner.paused),
        )
        self.background_activity_progress.setRange(view.progress_min,view.progress_max)
        self.background_activity_progress.setValue(view.progress_value)
        self.background_activity_progress.setFormat(view.progress_format)
        self.background_activity_label.setText(view.label)
        self.background_activity_pause.setText(view.pause_text)
        self.background_activity_pause.setEnabled(runner is not None)
        self.background_activity_cancel.setEnabled(runner is not None)
        self.background_activity.show()

    def _local_scan_progress(self, sequence: int, payload: object) -> None:
        if (
            self._closing
            or not self.local_scan.is_current(sequence)
            or not isinstance(payload,dict)
            or not self.local_scan.active
        ):
            return
        self._local_scan_last_progress=dict(payload)
        self._local_scan_session.update(
            scan_progress_patch(
                payload,
                elapsed_seconds=time.monotonic()-self._local_scan_started_at,
                pending_rescan=self.local_scan.pending,
            )
        )
        self._refresh_background_scan_activity()
        if hasattr(self,"library_browser"):
            self.library_browser.set_scan_progress(payload)
        message=scan_progress_message(payload)
        if message:
            self.statusBar().showMessage(message)
            if hasattr(self,"home_status"):
                self.home_status.setText(message)

    def _toggle_local_scan_pause(self) -> None:
        paused=self.local_scan.toggle_pause()
        if paused is None:
            return
        self._local_scan_session["paused"]=paused
        if hasattr(self,"library_browser"):
            self.library_browser.set_scan_paused(paused)
        self._refresh_background_scan_activity()
        self.statusBar().showMessage(
            "Music indexing paused" if paused else "Music indexing resumed",
            3000,
        )

    def _cancel_local_scan(self) -> None:
        if not self.local_scan.cancel(clear_pending=True):
            return
        self._local_scan_session.update(
            {
                "status": "cancelling",
                "running": True,
                "paused": False,
                "pending_rescan": False,
            }
        )
        if hasattr(self,"library_browser"):
            self.library_browser.set_scan_cancelling()
        self.background_activity_pause.setEnabled(False)
        self.background_activity_cancel.setEnabled(False)
        self.background_activity_label.setText(
            "Indexing music · Stopping safely… · existing library remains usable"
        )
        self.statusBar().showMessage(
            "Stopping music indexing… a stuck NAS scanner will be terminated automatically"
        )

    def _start_local_scan(self, reason: str = "scan") -> None:
        if self.current_page == "chiasm":
            self.chiasm_feature._status("Indexing collection…", 0)
        roots=self.providers.local_roots()
        if not roots:
            self.statusBar().showMessage("Add a music folder first",3000)
            return

        if self.local_scan.active:
            self._local_scan_session["pending_rescan"]=True
            roots_changed=self.local_scan.queue_rescan(roots)
            if roots_changed:
                self.statusBar().showMessage(
                    "Music folders changed · stopping the old indexer and restarting…",
                    5000,
                )
            else:
                self.statusBar().showMessage(
                    "Music indexing is already running · a fresh rescan is queued",
                    4000,
                )
            return

        self._local_scan_started_at=time.monotonic()
        self._local_scan_last_progress={"phase":"discovering","audio_files_seen":0}
        self._local_scan_session=start_scan_session(reason,len(roots))
        roots_snapshot=[Path(root) for root in roots]
        if hasattr(self,"library_browser"):
            self.library_browser.begin_scan(reason)
        self._refresh_background_scan_activity()
        self._background_activity_timer.start()
        self.statusBar().showMessage(
            "Indexing your music in an isolated background scanner…"
        )
        if hasattr(self,"home_status"):
            self.home_status.setText(
                "Indexing your music in an isolated background scanner…"
            )

        try:
            self.local_scan.start(roots_snapshot)
        except Exception as exc:
            self._local_scan_failed(self.local_scan.sequence,str(exc))
            return
        self._refresh_background_scan_activity()

    def _local_scan_done(self, sequence: int, snapshot: object) -> None:
        if self._closing or not self.local_scan.is_current(sequence):
            return
        scanned_roots_key=self.local_scan.roots_key
        if not self.local_scan.finish(sequence):
            return
        self._background_activity_timer.stop()
        self.background_activity.hide()
        current_key=scan_roots_key(self.providers.local_roots())
        result=dict(snapshot or {})

        if bool(result.get("cancelled")):
            elapsed=max(0.0,time.monotonic()-self._local_scan_started_at)
            self._local_scan_session.update(
                {
                    "status": "cancelled",
                    "running": False,
                    "paused": False,
                    "pending_rescan": bool(self.local_scan.pending),
                    "elapsed_seconds": round(elapsed, 3),
                    "hard_cancelled": bool(result.get("hard_cancelled")),
                }
            )
            if hasattr(self,"library_browser"):
                self.library_browser.finish_scan("cancelled")
                QTimer.singleShot(3500,self.library_browser.clear_scan_status)
            self._show_home()
            if bool(result.get("hard_cancelled")):
                self.statusBar().showMessage(
                    "Music indexing stopped · unresponsive scanner terminated · existing library kept",
                    6500,
                )
            else:
                self.statusBar().showMessage(
                    "Music indexing cancelled · existing library kept",
                    5000,
                )
            if self.local_scan.take_pending():
                QTimer.singleShot(
                    0,
                    lambda:self._start_local_scan("queued rescan"),
                )
            return

        # If roots changed while the disposable worker was scanning, its
        # catalog is not applied. A fresh scan immediately rebuilds the
        # current root set.
        if current_key != scanned_roots_key:
            self.local_scan.clear_pending()
            QTimer.singleShot(
                0,
                lambda:self._start_local_scan("queued change"),
            )
            return

        from .scan_outcome import scan_storage_message, scan_storage_outcome

        count=self.providers.apply_local_scan_snapshot(result)
        changes=dict(result.get("changes") or {})
        outcome=scan_storage_outcome(result)
        elapsed=max(0.0,time.monotonic()-self._local_scan_started_at)
        self._local_scan_session.update(
            {
                "status": "degraded" if outcome["degraded"] else "complete",
                "running": False,
                "paused": False,
                "pending_rescan": bool(self.local_scan.pending),
                "elapsed_seconds": round(elapsed, 3),
                "phase": "complete",
                "completed": count,
                "total": count,
                "storage_state": str(outcome["state"]),
                "root_count": int(outcome["root_count"]),
                "roots_unavailable": int(outcome["roots_unavailable"]),
                "roots_incomplete": int(outcome["roots_incomplete"]),
                "io_retries": int(outcome["io_retries"]),
            }
        )
        self._refresh_library()
        self._show_home()
        if self.current_page == "chiasm":
            self.chiasm_feature.refresh()
        storage_message=scan_storage_message(outcome)
        if hasattr(self,"library_browser"):
            self.library_browser.finish_scan(
                "degraded" if outcome["degraded"] else "complete",
                count=count,
                changes=changes,
                storage_outcome=outcome,
            )
            # Keep degraded NAS status visible until the next scan/user
            # action; clean completion can fade away as before.
            if not outcome["degraded"]:
                QTimer.singleShot(3500,self.library_browser.clear_scan_status)
        if outcome["degraded"]:
            message=f"NAS/library warning · {storage_message}"
            self.statusBar().showMessage(message,12000)
            if hasattr(self,"home_status"):
                self.home_status.setText(storage_message)
        else:
            suffix=scan_change_suffix(changes)
            self.statusBar().showMessage(
                f"Music indexing complete · {count:,} tracks{suffix}",
                6500,
            )
        if self.local_scan.take_pending():
            QTimer.singleShot(
                0,
                lambda:self._start_local_scan("queued rescan"),
            )

    def _local_scan_failed(self, sequence: int, error: str) -> None:
        if self._closing or not self.local_scan.finish(sequence):
            return
        self._background_activity_timer.stop()
        self.background_activity.hide()
        elapsed=max(0.0,time.monotonic()-self._local_scan_started_at)
        error_text=str(error or "")
        error_type=(error_text.split(":",1)[0].strip() or "scan_error")[:80]
        self._local_scan_session.update(
            {
                "status": "error",
                "running": False,
                "paused": False,
                "pending_rescan": bool(self.local_scan.pending),
                "elapsed_seconds": round(elapsed, 3),
                "error_type": error_type,
            }
        )
        if hasattr(self,"library_browser"):
            self.library_browser.finish_scan("error",error=error_type)
        self._show_home()
        message=(
            "Music indexing stopped — your existing library was kept. "
            "Export redacted diagnostics from Sources & plugins if this repeats."
        )
        self.statusBar().showMessage(message,10000)
        if hasattr(self,"home_status"):
            self.home_status.setText(message)
        if self.local_scan.take_pending():
            QTimer.singleShot(
                0,
                lambda:self._start_local_scan("queued rescan"),
            )

    def _diagnostics_ui_metrics(self) -> dict[str, Any]:
        ui_metrics: dict[str, Any] = {}
        if hasattr(self, "library_browser"):
            ui_metrics["library_catalog"] = dict(
                getattr(self.library_browser, "last_catalog_metrics", {}) or {}
            )
            ui_metrics["library_filter"] = dict(
                getattr(self.library_browser, "last_filter_metrics", {}) or {}
            )
            ui_metrics["library_view"] = dict(
                getattr(self.library_browser, "last_view_metrics", {}) or {}
            )
            ui_metrics["track_virtualization"] = dict(
                getattr(
                    self.library_browser,
                    "last_track_virtualization_metrics",
                    {},
                ) or {}
            )
            ui_metrics["artwork_priority"] = dict(
                getattr(
                    self.library_browser,
                    "last_artwork_priority_metrics",
                    {},
                ) or {}
            )
        ui_metrics["local_scan_session"] = dict(self._local_scan_session or {})
        if hasattr(self, "background_scheduler"):
            scheduler_metrics = self.background_scheduler.snapshot()
            scheduler_metrics["async_invalidations"] = self._async_invalidations
            scheduler_metrics["stale_results_dropped"] = (
                self._async_stale_results_dropped
            )
            ui_metrics["background_scheduler"] = scheduler_metrics
        if hasattr(self, "responsiveness"):
            ui_metrics["responsiveness"] = self.responsiveness.summary()
        return ui_metrics

    def _refresh_plugin_presence(self) -> None:
        if hasattr(self,"search_plugin_presence"):
            self.search_plugin_presence.set_items(self.source_policy.searchable_source_names())
        if hasattr(self,"artwork_plugin_presence"):
            self.artwork_plugin_presence.set_items(
                self.source_policy.active_extension_names("artwork")
            )
        if hasattr(self,"recommendation_plugin_presence"):
            self.recommendation_plugin_presence.set_items(
                self.source_policy.active_extension_names("library_suggestions","recommendations")
            )
        if hasattr(self, "playback_feature"):
            self.playback_feature.set_plugin_presence(
                lyrics=self.source_policy.active_extension_names("lyrics"),
                context=self.source_policy.active_extension_names(
                    "context", "metadata", "identity"
                ),
            )

    def _search_has_useful_results(self) -> bool:
        if not hasattr(self, "results"):
            return False
        for index in range(self.results.count()):
            data=self.results.item(index).data(Qt.UserRole)
            if isinstance(data,dict) and data:
                return True
        return False

    def _show_delayed_search_loading(self, sequence: int, target: str) -> None:
        if (
            sequence != self._search_sequence
            or sequence != self._search_pending_sequence
            or self._closing
        ):
            return
        # Preserve stale-but-useful results while revalidating.
        if self._search_has_useful_results():
            return
        self.results.clear()
        item=QListWidgetItem(f"Searching {target}…")
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        item.setForeground(QColor("#8793a4"))
        self.results.addItem(item)

    def _search(self):
        q=self.search_box.text().strip()
        pid=str(self.search_source.currentData() or "all")
        if not q:
            return

        interaction = (
            self.responsiveness.begin_interaction("discover:search")
            if hasattr(self, "responsiveness")
            else None
        )
        self._search_sequence += 1
        sequence=self._search_sequence
        self._search_pending_sequence=sequence
        had_results=self._search_has_useful_results()

        target=(
            self.search_source.currentText()
            if pid!="all"
            else "your connected sources"
        )
        if hasattr(self,"search_button"):
            self.search_button.setText("Searching…")
            self.search_button.setEnabled(False)
        if hasattr(self,"search_status"):
            if had_results:
                self.search_status.setText(
                    f"Updating {target}… · showing previous results"
                )
            else:
                self.search_status.setText(f"Searching {target}…")
            self.search_status.setToolTip("")

        # Avoid a loading-state flash for fast searches. If useful results are
        # already visible, keep them in place throughout the refresh.
        QTimer.singleShot(
            self._search_loading_delay_ms,
            lambda token=sequence, label=target: self._show_delayed_search_loading(
                token,
                label,
            ),
        )

        if interaction is not None:
            self.responsiveness.end_interaction(interaction)

        self._run_async(
            lambda:self.providers.search_report(q,pid,100),
            lambda report, token=sequence: self._show_search_report(
                report,
                token,
            ),
            lambda error, token=sequence: self._search_report_failed(
                error,
                token,
            ),
        priority="foreground", task_name="search", replace_key="search")

    def _search_report_failed(
        self,
        error: str,
        sequence: int | None = None,
    ) -> None:
        if sequence is not None and sequence != self._search_sequence:
            return
        if sequence is not None and self._search_pending_sequence == sequence:
            self._search_pending_sequence=0
        if hasattr(self,"search_button"):
            self.search_button.setText("Search")
            self.search_button.setEnabled(True)

        if self._search_has_useful_results():
            if hasattr(self,"search_status"):
                self.search_status.setText(
                    "Search refresh failed · showing previous results"
                )
                self.search_status.setToolTip(str(error or ""))
            return

        self.results.clear()
        item=QListWidgetItem("Search could not be completed. Try again in a moment.")
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        item.setForeground(QColor("#d9a441"))
        self.results.addItem(item)
        if hasattr(self,"search_status"):
            self.search_status.setText("Search temporarily unavailable")
            self.search_status.setToolTip(str(error or ""))

    def _show_search_report(
        self,
        report,
        sequence: int | None = None,
    ):
        if sequence is not None and sequence != self._search_sequence:
            return
        if sequence is not None and self._search_pending_sequence == sequence:
            self._search_pending_sequence=0
        if hasattr(self,"search_button"):
            self.search_button.setText("Search")
            self.search_button.setEnabled(True)

        data=dict(report or {})
        tracks=[dict(x) for x in list(data.get("items") or []) if isinstance(x,dict)]
        failures=[dict(x) for x in list(data.get("failures") or []) if isinstance(x,dict)]
        searched=int(data.get("searched") or 0)
        available=int(data.get("available") or 0)

        self.results.clear()
        for t in tracks:
            it=QListWidgetItem(_track_text(t))
            it.setData(Qt.UserRole,t)
            self.results.addItem(it)

        failure_labels=[
            f"{row.get('name') or row.get('provider_id')}: {row.get('reason') or 'Unavailable'}"
            for row in failures
        ]
        technical="\n".join(
            f"{row.get('name') or row.get('provider_id')}: {row.get('error') or row.get('reason') or 'Unavailable'}"
            for row in failures
        )

        if failures:
            shown=failure_labels[:3]
            suffix=f" · +{len(failure_labels)-3} more" if len(failure_labels)>3 else ""
            note=QListWidgetItem(
                "Some sources were unavailable · " + " · ".join(shown) + suffix
            )
            note.setFlags(note.flags() & ~Qt.ItemIsSelectable)
            note.setForeground(QColor("#d9a441"))
            note.setToolTip(technical)
            self.results.addItem(note)

        if not tracks and not failures:
            empty=QListWidgetItem("No matches found. Try a broader search.")
            empty.setFlags(empty.flags() & ~Qt.ItemIsSelectable)
            empty.setForeground(QColor("#8793a4"))
            self.results.addItem(empty)

        if hasattr(self,"search_status"):
            if failures and tracks:
                self.search_status.setText(
                    f"{len(tracks)} results · {available} of {searched} sources responded · "
                    f"{len(failures)} temporarily unavailable"
                )
            elif failures:
                names=", ".join(
                    str(row.get("name") or row.get("provider_id") or "Source")
                    for row in failures[:3]
                )
                more=f" and {len(failures)-3} more" if len(failures)>3 else ""
                self.search_status.setText(
                    f"No results yet · {names}{more} unavailable"
                )
            else:
                source_word="source" if searched==1 else "sources"
                self.search_status.setText(
                    f"{len(tracks)} results · {searched} {source_word} searched"
                )
            self.search_status.setToolTip(technical)

    def _show_results(self, tracks):
        # Kept for older call sites; search itself now uses _show_search_report.
        self._show_search_report(
            {
                "items": list(tracks or []),
                "failures": [],
                "searched": 1,
                "available": 1,
            }
        )

    def _play_result(self,item):
        if hasattr(self, "responsiveness"):
            self.responsiveness.mark_action("discover:play-result")
        t=dict(item.data(Qt.UserRole) or {}); self.player.set_queue([t],0,True)

    def _open_selected_source(self):
        item=self.results.currentItem()
        if not item:return
        t=dict(item.data(Qt.UserRole) or {})
        url=str(t.get("source_page") or "")
        if url: QDesktopServices.openUrl(url)
        else: self.statusBar().showMessage("This source did not provide a content page",3000)

    def _play_library(self,item):
        t=dict(item.data(Qt.UserRole) or {}); tracks=self.providers.local_catalog(); idx=next((i for i,x in enumerate(tracks) if x.get('track_id')==t.get('track_id')),0); self.player.set_queue(tracks,idx,True)

    def _add_selected_to_queue(self):
        item=self.results.currentItem()
        if not item:return
        t=dict(item.data(Qt.UserRole) or {})
        self.player.append_queue([t],autoplay=False)

    # ------------------------------- local intelligence
    def _intelligence_seeds(self, intent: str) -> list[dict[str, Any]]:
        if intent == "rediscover":
            return []
        current = dict(self.playback_feature.current_track() or {})
        if not current or not current.get("local_path"):
            return []
        if intent in {"similar", "detour"}:
            return [current]
        if intent == "bridge":
            idx = self.playback_feature.queue_index()
            queue = self.playback_feature.queue_snapshot()
            if idx < 0 or idx + 1 >= len(queue):
                return []
            nxt = dict(queue[idx + 1] or {})
            if not nxt.get("local_path"):
                return []
            return [current, nxt]
        return []

    def _run_local_intelligence(self, intent: str) -> None:
        catalog = self.providers.local_catalog()
        if not catalog:
            QMessageBox.information(
                self, "Add music first",
                "Local intelligence needs your local library. Add a folder, then try again."
            )
            return
        seeds = self._intelligence_seeds(intent)
        if intent in {"similar", "detour"} and len(seeds) != 1:
            message = (
                "Find a detour needs the current track to be local."
                if intent == "detour"
                else "More like current needs a local track as the seed."
            )
            QMessageBox.information(self, "Play a local track first", message)
            return
        if intent == "bridge" and len(seeds) != 2:
            QMessageBox.information(
                self, "Queue two local tracks",
                "Bridge current → next needs the current track and the next queued track to be local."
            )
            return
        self.intelligence_results.clear()
        self.statusBar().showMessage("Asking local intelligence plugins…")
        adventure = self.adventure.value() / 100.0
        self._run_async(
            lambda: self.local_intelligence.suggest(
                intent, catalog, seeds, limit=16, adventure=adventure
            ),
            self._show_intelligence_results,
        priority="foreground", task_name="local-intelligence", replace_key="local-intelligence")

    def _show_intelligence_results(self, result: dict[str, Any]) -> None:
        self.intelligence_results.clear()
        tracks = [dict(x) for x in list(result.get("tracks") or []) if isinstance(x, dict)]
        for track in tracks:
            reason = str(track.get("_intelligence_reason") or "")
            score = float(track.get("_intelligence_score") or 0.0)
            badges = ", ".join(str(x) for x in list(track.get("_intelligence_badges") or []) if x)
            suffix = " · ".join(x for x in (reason, badges, f"{score:.0%}") if x)
            item = QListWidgetItem(_track_text(track) + (f"\n{suffix}" if suffix else ""))
            item.setData(Qt.UserRole, track)
            self.intelligence_results.addItem(item)
        if tracks:
            self.statusBar().showMessage(
                f"{len(tracks)} local suggestions · {int(result.get('analysed') or 0)} of {int(result.get('profiles') or 0)} profiles have Flow analysis",
                7000,
            )
            return
        errors = [str(x) for x in list(result.get("errors") or []) if x]
        analysed = int(result.get("analysed") or 0)
        if errors:
            message = errors[0]
        elif analysed == 0 and result.get("intent") in {"similar", "bridge", "detour"}:
            message = "No analysed comparison tracks yet. Use ‘Analyse my library’, then try again."
        else:
            message = "No local-intelligence plugin returned suggestions. Install one from Explore plugins."
        self.intelligence_results.addItem(message)
        self.statusBar().showMessage(message, 7000)

    def _selected_intelligence_track(self) -> dict[str, Any]:
        item = self.intelligence_results.currentItem()
        data = item.data(Qt.UserRole) if item else None
        return dict(data) if isinstance(data, dict) else {}

    def _play_intelligence_result(self, item) -> None:
        data = item.data(Qt.UserRole)
        if isinstance(data, dict):
            self.player.set_queue([dict(data)], 0, True)

    def _play_selected_intelligence(self) -> None:
        track = self._selected_intelligence_track()
        if track:
            self.player.set_queue([track], 0, True)

    def _queue_selected_intelligence(self) -> None:
        track = self._selected_intelligence_track()
        if not track:
            return
        self.player.append_queue([track],autoplay=False)
        self.statusBar().showMessage("Added local-intelligence suggestion to queue", 3000)

    def _analyse_library_for_intelligence(self) -> None:
        catalog = self.providers.local_catalog()
        if not catalog:
            QMessageBox.information(
                self, "Add music first",
                "Add a local music folder before analysing your library."
            )
            return
        if not self.flow.analysis_available:
            QMessageBox.information(
                self, "Audio analysis unavailable",
                "Deep local analysis needs ffmpeg and NumPy. Melodex can still use taste-only rediscovery."
            )
            return
        self.statusBar().showMessage("Analysing local library for Flow and local intelligence…")
        self._run_async(
            lambda: self.local_intelligence.analyse_catalog(catalog),
            self._library_analysis_finished,
        priority="background", task_name="library-analysis")

    def _library_analysis_finished(self, result: dict[str, Any]) -> None:
        self.statusBar().showMessage(
            f"Library analysis ready · {int(result.get('analysed') or 0)}/{int(result.get('total') or 0)} analysed · {int(result.get('newly_analysed') or 0)} new",
            8000,
        )

    # ------------------------------- Music Map
    def _build_album_wall_payload(self):
        from .album_wall_model import build_album_wall
        from .music_map_model import build_music_map

        catalog=self.providers.local_catalog()
        profiles, _seed_refs, ref_map, _analysed = self.local_intelligence.build_snapshot(
            catalog,
            [],
            max_tracks=5000,
            analyse_seeds=False,
        )
        projection=build_music_map(profiles,max_nodes=5000,neighbours=0)
        projected_refs={
            str(node.get("ref") or "")
            for node in list(projection.get("nodes") or [])
            if isinstance(node,dict) and str(node.get("ref") or "")
        }
        projected_ref_map={
            ref:dict(track)
            for ref,track in ref_map.items()
            if ref in projected_refs
        }
        return build_album_wall(
            catalog,
            projection,
            projected_ref_map,
            max_albums=1200,
        )

    def _refresh_album_wall(self):
        catalog=self.providers.local_catalog()
        if not catalog:
            self.album_wall.set_model(
                {}, self.playback_feature.current_track()
            )
            self.statusBar().showMessage("Add local music to build an Album Wall",4000)
            return
        self.statusBar().showMessage("Building Album Wall from local metadata and cached Flow analysis…")
        self._run_async(self._build_album_wall_payload,self._apply_album_wall_payload, priority="visible", task_name="album-wall-model", replace_key="page:album-wall-model")

    def _apply_album_wall_payload(self,payload):
        payload=dict(payload or {})
        self.album_wall.set_model(
            payload, self.playback_feature.current_track()
        )
        albums=int(payload.get("album_count") or 0)
        analysed=int(payload.get("analysed_albums") or 0)
        if analysed:
            message=f"Album Wall ready · {albums} albums · {analysed} positioned from Flow analysis"
        else:
            message=f"Album Wall ready · {albums} albums · analyse your library for sonic neighbourhoods"
        self.statusBar().showMessage(message,6000)

    def _analyse_library_for_album_wall(self):
        catalog=self.providers.local_catalog()
        if not catalog:
            QMessageBox.information(self,"Add music first","Add a local music folder before analysing your Album Wall.")
            return
        if not self.flow.analysis_available:
            QMessageBox.information(
                self,
                "Audio analysis unavailable",
                "Album Wall sonic layout needs ffmpeg and NumPy. The wall still works in metadata mode; install/enable them for sonic neighbourhoods.",
            )
            return
        self.statusBar().showMessage("Analysing local library for Album Wall…")
        self._run_async(
            lambda:self.local_intelligence.analyse_catalog(catalog),
            self._album_wall_analysis_finished,
        priority="background", task_name="album-wall-analysis")

    def _album_wall_analysis_finished(self,result):
        self.statusBar().showMessage(
            f"Album Wall analysis ready · {int(result.get('analysed') or 0)}/{int(result.get('total') or 0)} analysed",
            5000,
        )
        self._refresh_album_wall()

    def _album_wall_selected(self):
        return self.album_wall.selected_album() if hasattr(self,"album_wall") else {}

    def _play_album_wall_album(self,album):
        tracks=[dict(x) for x in list((album or {}).get("tracks") or []) if isinstance(x,dict)]
        if tracks:
            self.player.set_queue(tracks,0,True)
            self.statusBar().showMessage(
                f"Playing {album.get('artist') or 'Unknown artist'} — {album.get('title') or 'Unknown album'}",
                4500,
            )

    def _play_album_wall_selected(self):
        album=self._album_wall_selected()
        if album:
            self._play_album_wall_album(album)

    def _queue_album_wall_selected(self):
        album=self._album_wall_selected()
        tracks=[dict(x) for x in list(album.get("tracks") or []) if isinstance(x,dict)] if album else []
        if not tracks:
            self.statusBar().showMessage("Select an album on the wall first",3000)
            return
        if not self.player.queue:
            self.player.set_queue(tracks,0,False)
        else:
            self.player.append_queue(tracks,autoplay=False)
        self.statusBar().showMessage(f"Queued {len(tracks)} tracks from {album.get('title') or 'album'}",4000)

    def _album_wall_artwork_requested(self,requests):
        rows=[dict(x) for x in list(requests or []) if isinstance(x,dict)]
        if not rows:
            return
        def load():
            result={}
            for row in rows:
                key=str(row.get("key") or "")
                track=dict(row.get("track") or {})
                if not key or not track:
                    continue
                info=self.metadata.local_artwork(track)
                result[key]=str(info.get("path") or "")
            return result
        self._run_async(load,self.album_wall.set_artwork, priority="visible", task_name="album-wall-cached-artwork")

    def _album_wall_online_artwork_requested(self,requests):
        rows=[dict(x) for x in list(requests or []) if isinstance(x,dict)]
        if not rows:
            return

        def load():
            result={}
            for row in rows:
                key=str(row.get("key") or "")
                track=dict(row.get("track") or {})
                if not key or not track:
                    continue
                path=""
                try:
                    local=self.metadata.local_artwork(track)
                    path=str(local.get("path") or "")
                    if not path:
                        identity=self.metadata.identify(track)
                        artwork=self.metadata.artwork(track,identity)
                        path=str(artwork.get("path") or "")
                except Exception:
                    path=""
                result[key]=path
            return result

        self._run_async(load,self.album_wall.set_artwork, priority="background", task_name="album-wall-online-artwork")

    def _start_session_from_map_track(self, track: object) -> None:
        seed = dict(track or {}) if isinstance(track, dict) else {}
        if not seed:
            return
        catalog = self.providers.local_catalog()
        self.statusBar().showMessage("Building a journey from this part of your map…")
        self._run_async(
            lambda: self.mind.build_session(
                catalog,
                self._path_for,
                minutes=int(self.minutes.currentText()),
                adventure=self.adventure.value() / 100,
                mode=str(self.mode.currentData() or "balanced"),
                start_track=seed,
            ),
            lambda plan: self._apply_mind(plan),
            priority="foreground",
            task_name="journey-build",
            replace_key="journey-build",
        )

    # ------------------------------- Flow / Mind
    def _path_for(self,t):
        p=str(t.get("local_path") or ""); return Path(p) if p else None

    def _transition_for(self,a,b):
        aa=self.flow.cached_analysis_for(self._path_for(a)); bb=self.flow.cached_analysis_for(self._path_for(b)); return self.flow.transition(aa,bb).as_dict()

    def _play_for_me(self,mode,minutes,adventure):
        catalog=self.providers.local_catalog()
        if not catalog:
            QMessageBox.information(self,"Add music first","Play for Me needs at least some local music. Add a folder, then try again."); return
        self.statusBar().showMessage("Building your journey…")
        self._run_async(lambda:self.mind.build_session(catalog,self._path_for,minutes=minutes,adventure=adventure,mode=mode),lambda plan:self._apply_mind(plan), priority="foreground", task_name="play-for-me", replace_key="play-for-me")

    def _apply_mind(self,plan):
        tracks=list(plan.get("tracks",[]));
        if tracks:self.player.set_queue(tracks,0,True)
        self.statusBar().showMessage(f"Journey ready · {len(tracks)} tracks · {plan.get('new_to_you',0)} new to you",6000)

    def _llm_settings(self):
        from .llm_bridge import LLMClient, LLMSettings
        return LLMSettings(
            provider=self.state.get_text("llm_provider","openwebui"),
            endpoint=self.state.get_text("llm_endpoint",LLMClient.default_endpoint(self.state.get_text("llm_provider","openwebui"))),
            model=self.state.get_text("llm_model",""), api_key=self.state.get_text("llm_api_key","")
        )

    def _llm_settings_dialog(self):
        from .llm_bridge import LLMClient
        d=QDialog(self); d.setWindowTitle("Connect an LLM"); f=QFormLayout(d)
        provider=QComboBox(); provider.addItems(["openwebui","ollama","openai","custom"]); provider.setCurrentText(self.state.get_text("llm_provider","openwebui"))
        endpoint=QLineEdit(self.state.get_text("llm_endpoint",LLMClient.default_endpoint(provider.currentText()))); model=QLineEdit(self.state.get_text("llm_model","")); key=QLineEdit(self.state.get_text("llm_api_key","")); key.setEchoMode(QLineEdit.Password)
        provider.currentTextChanged.connect(lambda p:endpoint.setText(LLMClient.default_endpoint(p)))
        f.addRow("Provider",provider); f.addRow("Endpoint",endpoint); f.addRow("Model",model); f.addRow("API key",key)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); buttons.accepted.connect(d.accept); buttons.rejected.connect(d.reject); f.addRow(buttons)
        if d.exec():
            self.state.set_text("llm_provider",provider.currentText()); self.state.set_text("llm_endpoint",endpoint.text().strip()); self.state.set_text("llm_model",model.text().strip()); self.state.set_text("llm_api_key",key.text().strip())

    def _llm_context(self):
        from .llm_bridge import llm_track_summary
        queue = (
            self.player.queue[self.player.index:self.player.index + 12]
            if self.player.index >= 0
            else []
        )
        return {
            "current_track": llm_track_summary(
                self.playback_feature.current_track()
            ),
            "queue": [llm_track_summary(track) for track in queue],
            "current_page": self.current_page,
            "taste": self.state.taste_summary(),
            "recent": [
                llm_track_summary(track)
                for track in self.state.recent_tracks(15)
            ],
            "vibes": self.state.vibes(10),
        }

    def _ask(self):
        prompt=self.ask_box.text().strip();
        if not prompt:return
        self.ask_box.clear(); self.chat.append(f"You: {prompt}")
        settings=self._llm_settings(); self._run_async(lambda:self.llm.complete(settings,prompt,self._llm_context(),[]),lambda text:self._handle_llm(text), priority="foreground", task_name="llm-ask")

    def _handle_llm(self,text):
        reply,actions=self.llm.parse_action_response(str(text)); self.chat.append(f"Melodex: {reply}")
        for a in actions:self._execute_action(a)

    def _execute_action(self,a):
        typ=str(a.get("type") or ""); args=dict(a.get("args") or {})
        if typ=="play_for_me":self._play_for_me(args.get("mode","balanced"),int(args.get("minutes",60)),float(args.get("adventure",0.35)))
        elif typ=="search": self.open_page("discover"); self.search_box.setText(str(args.get("query", ""))); self._search()
        elif typ=="play_pause":self.player.play_pause()
        elif typ=="next":self.player.next()
        elif typ=="previous":self.player.previous()
        elif typ=="flow_queue":self.playback_feature.refine_queue()
        elif typ=="save_moment":
            current=self.playback_feature.current_track()
            if current:
                self.state.save_moment(
                    current,
                    self.playback_feature.current_position_ms(),
                    str(args.get("label", "")),
                )
        elif typ=="open_view":self.open_page(str(args.get("view","home")) if str(args.get("view","home")) in self.pages else "home")
        elif typ=="import_playlist":self._import_ai_playlist(args)

    def _import_ai_playlist(self,args,source="llm"):
        requested=[dict(x) for x in list(args.get("tracks") or []) if isinstance(x,dict)]
        if not requested:
            self.statusBar().showMessage("The AI playlist did not contain any tracks",4000); return
        playlist_id=str(uuid.uuid4()); name=str(args.get("name","AI playlist")); description=str(args.get("description",""))
        self.statusBar().showMessage(f"Matching {len(requested)} playlist tracks across your sources…")
        self._run_async(
            lambda:self.providers.resolve_playlist(requested),
            lambda result:self._finish_ai_playlist(playlist_id,name,description,result,requested,source),
        priority="foreground", task_name="ai-playlist-resolve")

    def _finish_ai_playlist(self,playlist_id,name,description,result,requested=None,source="llm"):
        from .playlist_io import save_playlist
        tracks=list(result.get("tracks") or []); unresolved=list(result.get("unresolved") or [])
        payload={"tracks":tracks,"unresolved":unresolved,"requested":int(result.get("requested") or len(tracks)+len(unresolved))}
        if requested is not None:payload["requested_tracks"]=[dict(x) for x in requested]
        self.state.save_playlist(playlist_id,name,description,source,payload); self._refresh_playlists()
        if tracks:self.player.set_queue(tracks,0,True)
        msg=f"{name}: matched {len(tracks)} track{'s' if len(tracks)!=1 else ''}"
        if unresolved:msg+=f" · {len(unresolved)} unresolved"
        self.statusBar().showMessage(msg,7000)

    # ------------------------------- bridge / external control
    def _control_request(self, action, args):
        event=threading.Event(); box={}
        self.externalCommand.emit(str(action),dict(args or {}),(event,box))
        if not event.wait(12):raise RuntimeError("Melodex GUI did not answer the control request")
        if box.get("error"):raise RuntimeError(str(box["error"]))
        return box.get("result")

    def _on_external_command(self,action,args,reply):
        event,box=reply
        try:
            action=str(action or ""); args=dict(args or {})
            if action=="status":
                result=self.player.status(); result["page"]=self.current_page; result["taste"]=self.state.taste_summary()
            elif action=="set_queue":
                tracks=[dict(x) for x in list(args.get("tracks") or []) if isinstance(x,dict)]; self.player.set_queue(tracks,int(args.get("start",0)),bool(args.get("autoplay",True))); result=self.player.status()
            elif action=="append_queue":
                tracks=[dict(x) for x in list(args.get("tracks") or []) if isinstance(x,dict)]; self.player.append_queue(tracks,bool(args.get("autoplay",False))); result=self.player.status()
            elif action=="play_pause":self.player.play_pause(); result=self.player.status()
            elif action=="next":self.player.next(); result=self.player.status()
            elif action=="previous":self.player.previous(); result=self.player.status()
            elif action=="stop":self.player.stop(); result=self.player.status()
            elif action=="clear_queue":self.player.clear_queue(); result=self.player.status()
            elif action=="seek_ms":self.player.seek(int(args.get("value",0))); result=self.player.status()
            elif action=="set_volume":self.player.set_volume(float(args.get("value",1.0))); result=self.player.status()
            elif action=="flow_queue":
                self.playback_feature.refine_queue()
                result={"started":True,"queue_length":len(self.player.queue)}
            elif action=="love_current":
                current=self.playback_feature.current_track()
                self.playback_feature.record_feedback(True)
                result={"recorded":bool(current)}
            elif action=="dislike_current":
                current=self.playback_feature.current_track()
                self.playback_feature.record_feedback(False)
                result={"recorded":bool(current)}
            elif action=="keep_current":
                current=self.playback_feature.current_track()
                self.playback_feature.keep_current()
                result={"recorded":bool(current)}
            elif action=="save_moment":
                current=self.playback_feature.current_track()
                if current:
                    moment_id=self.state.save_moment(
                        current,
                        self.playback_feature.current_position_ms(),
                        str(args.get("label", "")),
                    )
                    result={"saved":True,"id":moment_id}
                else:
                    result={"saved":False,"reason":"nothing playing"}
            elif action=="open_view":
                view=str(args.get("view","home")); self.open_page(view if view in self.pages else "home"); result={"page":self.current_page}
            else:raise RuntimeError(f"Unsupported control action: {action}")
            box["result"]=result
        except Exception as exc:box["error"]=str(exc)
        finally:event.set()

    def _start_local_bridge(self):
        if self.bridge or self._bridge_start_pending or self._closing:
            return
        self._bridge_start_pending = True

        def create_bridge():
            bridge = ProviderBridge(
                self.providers,
                "127.0.0.1",
                0,
                controller=self._control_request,
                state_path=self.data_dir / "bridge.json",
            )
            bridge.start()
            if self._closing:
                bridge.stop()
                return None
            return bridge

        def bridge_ready(result):
            self._bridge_start_pending = False
            if result is None or self._closing:
                return
            self.bridge = result
            self._startup_mark("bridge_ready")

        def bridge_failed(error: str):
            self._bridge_start_pending = False
            if self._closing:
                return
            self.statusBar().showMessage(
                f"AI control bridge could not start: {error}",
                7000,
            )

        self._run_async(
            create_bridge,
            bridge_ready,
            bridge_failed,
            priority="background",
            task_name="local-control-bridge",
            replace_key="local-control-bridge",
        )

    def _restart_bridge(self,host):
        token=self.bridge.token if self.bridge else ""; port=self.bridge.port if self.bridge else 0
        if self.bridge:self.bridge.stop()
        self.bridge=ProviderBridge(self.providers,host,port,token=token,controller=self._control_request,state_path=self.data_dir/"bridge.json"); self.bridge.start()

    def _bridge_dialog(self):
        if not self.bridge:
            self._start_local_bridge()
            if self._bridge_start_pending:
                self.statusBar().showMessage(
                    "AI control bridge is starting in the background…",
                    3000,
                )
            return
        if self.bridge.host=="127.0.0.1":
            choice=QMessageBox.question(self,"Provider Bridge",f"The private AI control bridge is running locally on port {self.bridge.port}.\n\nAllow phones/computers on your LAN to use the provider bridge too?\n\nChoose No to keep it local-only.",QMessageBox.Yes|QMessageBox.No)
            if choice==QMessageBox.Yes:
                try:self._restart_bridge("0.0.0.0"); QMessageBox.information(self,"Provider Bridge",f"LAN bridge enabled on port {self.bridge.port}.\n\nBearer token:\n{self.bridge.token}\n\nKeep this token private.")
                except Exception as exc:self.statusBar().showMessage(str(exc),7000)
        else:
            choice=QMessageBox.question(self,"Provider Bridge",f"The bridge currently accepts LAN connections on port {self.bridge.port}.\n\nRestrict it to this computer only?",QMessageBox.Yes|QMessageBox.No)
            if choice==QMessageBox.Yes:
                try:self._restart_bridge("127.0.0.1"); self.statusBar().showMessage("Provider bridge restricted to this computer",4000)
                except Exception as exc:self.statusBar().showMessage(str(exc),7000)

    # ------------------------------- helpers
    def _invalidate_async(self, replace_key: str) -> int:
        key = str(replace_key or "").strip()
        if not key:
            return 0
        self._async_generations[key] = self._async_generations.get(key, 0) + 1
        self._async_invalidations += 1
        return self.background_scheduler.cancel_pending(key)

    def _run_async(
        self,
        fn,
        done,
        on_error=None,
        *,
        priority: str = "foreground",
        task_name: str = "",
        replace_key: str = "",
    ):
        scope = str(replace_key or "").strip()
        generation = 0
        if scope:
            generation = self._async_generations.get(scope, 0) + 1
            self._async_generations[scope] = generation

        def is_current() -> bool:
            return (
                not scope
                or self._async_generations.get(scope, 0) == generation
            )

        dispatcher = self._ui_callback_dispatcher
        closing_event = self._async_closing_event

        def deliver_done(result: object) -> None:
            # This check deliberately touches no QObject-backed wrapper. A
            # completion can arrive after Qt has destroyed MainWindow's C++
            # object but while Python closures still retain the wrapper.
            if closing_event.is_set():
                return
            if not is_current():
                self._async_stale_results_dropped += 1
                return
            done(result)

        def deliver_error(error: str) -> None:
            if closing_event.is_set():
                return
            if not is_current():
                self._async_stale_results_dropped += 1
                return
            if on_error is None:
                QMessageBox.warning(self,"Melodex",error)
            else:
                on_error(error)

        def post_to_ui(callback) -> None:
            # A single process-lived QObject owns all queued MetaCall events.
            # Do not create a temporary QObject per task: on macOS/PySide that
            # can leave a posted event pointing at a wrapper that Python has
            # already collected.
            dispatcher.invoke.emit(callback)

        def work():
            try:
                result=fn()
            except Exception as exc:
                error=str(exc)
                post_to_ui(
                    lambda message=error: deliver_error(message)
                )
                raise
            else:
                post_to_ui(
                    lambda value=result: deliver_done(value)
                )

        submitted=self.background_scheduler.submit(
            work,
            priority=priority,
            name=task_name,
            replace_key=scope,
        )
        if not submitted and not closing_event.is_set():
            post_to_ui(
                lambda: deliver_error("Background work is shutting down")
            )

    def closeEvent(self,event):
        # Set the plain-Python gate before any Qt-owned children are torn down.
        if hasattr(self, "_async_closing_event"):
            self._async_closing_event.set()
        if hasattr(self, "journey_workspace"):
            self.journey_workspace.shutdown()
        if hasattr(self, "responsiveness"):
            self.responsiveness.stop()
        self._closing = True
        if hasattr(self, "background_scheduler"):
            self.background_scheduler.shutdown(wait=False)
        self.local_scan.shutdown()
        if self.bridge:self.bridge.stop()
        self.player.close()
        if self._metadata is not None:
            self._metadata.close()
        self.providers.close()
        self.flow.close()
        if self._knowledge is not None:
            self._knowledge.close()
        self.state.close()
        super().closeEvent(event)
