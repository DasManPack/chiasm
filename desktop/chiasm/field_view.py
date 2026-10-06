"""Full-window, single-field PySide6 view for the Chiasm spatial-field prototype."""

from __future__ import annotations

from collections import OrderedDict
from math import atan2, hypot, pi
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAccessible,
    QAccessibleEvent,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QInputDevice,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

from .field_model import (
    Album,
    DEMO_COLLECTION,
    FieldCamera,
    album_depth_cue,
    album_hit_radius,
    semantic_zoom_level,
    SemanticLevel,
)
from .relationship_model import album_horizon


_PALETTES = (
    ("#d99a63", "#632f38", "#f4d3a1"),
    ("#82b8a5", "#1d5361", "#e2c77a"),
    ("#d47d66", "#65364a", "#e8bf9b"),
    ("#96a6cb", "#353f73", "#e0cb96"),
    ("#d9b75e", "#415d61", "#efdca4"),
    ("#a786b8", "#453653", "#edc89f"),
    ("#7fa9bf", "#293f5d", "#f0c37c"),
    ("#cf866f", "#453650", "#dbbb88"),
)


class FieldCanvas(QWidget):
    """Navigable album field with host playback requests and standalone mock play."""

    mockPlayed = Signal(str)
    albumFocused = Signal(str)
    findRequested = Signal()
    interactionMeasured = Signal(str, float)
    playRequested = Signal(str)
    playPauseRequested = Signal()
    nextRequested = Signal()
    arcRequested = Signal(str)
    arcSteerRequested = Signal(str)
    arcPauseRequested = Signal()
    arcTakeControlRequested = Signal()
    artworkRequested = Signal(object)

    _INTERACTION_EVENT_LABELS = {
        QEvent.Type.MouseButtonPress: "chiasm:pointer-press",
        QEvent.Type.MouseButtonRelease: "chiasm:pointer-release",
        QEvent.Type.MouseButtonDblClick: "chiasm:pointer-double-click",
        QEvent.Type.Wheel: "chiasm:wheel",
        QEvent.Type.KeyPress: "chiasm:key",
        QEvent.Type.NativeGesture: "chiasm:gesture",
    }

    def __init__(
        self,
        albums: tuple[Album, ...] = DEMO_COLLECTION,
        parent: QWidget | None = None,
        *,
        live_playback: bool = False,
    ):
        super().__init__(parent)
        self.albums = albums
        self.live_playback = bool(live_playback)
        self.camera = FieldCamera()
        self.focused_id: str | None = None
        self.hovered_id: str | None = None
        self._current_track: dict | None = None
        self._playing_album_id: str | None = None
        self._playing = False
        self._position_ms = 0
        self._duration_ms = 0
        self._can_next = False
        self._arc_active = False
        self._arc_paused = False
        self._arc_next_album: Album | None = None
        self._arc_reason = ""
        self._hover_position: QPointF | None = None
        self._pressed_at: QPointF | None = None
        self._last_pointer: QPointF | None = None
        self._dragging = False
        self._visible_ids: tuple[str, ...] = ()
        self._artwork_generation = 0
        self._artwork_cache: OrderedDict[str, QImage] = OrderedDict()
        self._artwork_missing: set[str] = set()
        self._artwork_resolved: set[str] = set()
        self._artwork_pending: set[str] = set()
        self._artwork_cache_limit = 48
        self._artwork_batch_limit = 24
        self._artwork_view_key: tuple[object, ...] | None = None
        self._artwork_view_budget = self._artwork_batch_limit
        self._artwork_request_timer = QTimer(self)
        self._artwork_request_timer.setSingleShot(True)
        self._artwork_request_timer.timeout.connect(self._request_visible_artwork)
        self._play_toast = ""
        self._home_cue_rect = QRectF()
        self._home_cue_hovered = False
        self._lens_open = False
        self._lens_panel = "horizon"
        self._lens_rect = QRectF()
        self._lens_close_rect = QRectF()
        self._lens_play_rect = QRectF()
        self._lens_arc_rect = QRectF()
        self._lens_horizon_tab_rect = QRectF()
        self._lens_trace_tab_rect = QRectF()
        self._lens_trace_entries: list[dict] = []
        self._lens_trace_offset = 0
        self._lens_trace_page_size = 2
        self._lens_trace_rects: tuple[QRectF, ...] = ()
        self._lens_trace_play_rects: tuple[QRectF, ...] = ()
        self._lens_trace_targets: tuple[str, ...] = ()
        self._lens_trace_older_rect = QRectF()
        self._lens_trace_newer_rect = QRectF()
        self._lens_close_hovered = False
        self._lens_play_hovered = False
        self._lens_arc_hovered = False
        self._lens_trace_tab_hovered = False
        self._lens_horizon_tab_hovered = False
        self._lens_horizon_rects: tuple[QRectF, ...] = ()
        self._lens_horizon_targets: tuple[str, ...] = ()
        self._lens_horizon_hover_index = -1
        self._lens_trace_hover_index = -1
        self._lens_anchor = QPointF()
        self._lens_click_position: QPointF | None = None
        self._transport_rect = QRectF()
        self._transport_play_rect = QRectF()
        self._transport_next_rect = QRectF()
        self._arc_status_rect = QRectF()
        self._arc_toggle_rect = QRectF()
        self._arc_take_control_rect = QRectF()
        self._transport_hover = ""
        self._arc_control_hover = ""
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.OpenHandCursor)
        self.setAccessibleName("Chiasm spatial music field")
        self._refresh_accessible_description()
        self.setMinimumSize(480, 320)

    def _refresh_accessible_description(self) -> None:
        controls = (
            "Drag or use arrow keys to pan; Shift with an arrow uses a shorter step. "
            "Use the mouse wheel or plus and minus keys to zoom. Trackpad scrolling pans "
            "and pinching zooms. Click an album to focus it; double-click plays it when "
            "playback is available. Enter opens or closes the focused album lens. Escape "
            "closes an open lens, or clears focus when the lens is closed. In an open lens, "
            "The left and right bracket keys focus the previous or next album in collection order. "
            "Ctrl+F opens the in-field album finder. "
            "Ctrl+Tab switches between Horizon and Trace; Ctrl+Shift+Tab switches back. "
            "In Trace, PageUp and PageDown browse older and newer stops. "
            "Select a displayed entry or press 1 to 3 to follow it. "
            "H or Home returns to the starting view."
        )
        if self.live_playback:
            controls += (
                " Ctrl+Enter plays the focused album. Space pauses or resumes playback; "
                "N advances to the next track. In Melodex, A starts or steers Arc from "
                "the focused album, and T takes control "
                "from an active Arc."
            )

        album = self.album_by_id(self.focused_id)
        if album is None:
            state = "No album is focused."
        else:
            artist = f" by {album.artist}" if album.artist else ""
            state = f"Focused album: {album.title}{artist}."
            if self._lens_open:
                panel = "Trace" if self._lens_panel == "trace" else "Horizon"
                state += f" Its {panel} lens is open."
            else:
                state += " Its lens is closed; press Enter to open it."

        if self._lens_open and self._lens_panel == "trace":
            page_size = max(1, self._lens_trace_page_size)
            start = min(self._lens_trace_offset, max(0, len(self._lens_trace_entries) - 1))
            stops = self._lens_trace_entries[start : start + page_size]
            if stops:
                labels = [
                    f"{entry['title']} by {entry['artist']}"
                    if entry["artist"]
                    else entry["title"]
                    for entry in stops
                ]
                state += " Trace stops shown: " + "; ".join(labels) + "."
                if start > 0:
                    state += " Newer stops are available with PageDown."
                if start + len(stops) < len(self._lens_trace_entries):
                    state += " Earlier stops are available with PageUp."
            else:
                state += " Trace has no recorded stops."

        if self._current_track is not None:
            title = str(self._current_track.get("title") or "Unknown track")
            artist = str(self._current_track.get("artist") or "Unknown artist")
            playback = "playing" if self._playing else "paused or stopped"
            state += f" Current track: {title} by {artist}; playback is {playback}."
        if self._arc_active:
            arc_state = "paused" if self._arc_paused else "active"
            state += f" Arc is {arc_state}."
            if self._arc_next_album is not None:
                reason = f" Reason: {self._arc_reason}." if self._arc_reason else ""
                state += f" Next album: {self._arc_next_album.title}.{reason}"

        description = f"{controls} {state}"
        if description == self.accessibleDescription():
            return
        self.setAccessibleDescription(description)
        event = QAccessibleEvent(self, QAccessible.Event.DescriptionChanged)
        QAccessible.updateAccessibility(event)

    def album_by_id(self, album_id: str | None) -> Album | None:
        if album_id is None:
            return None
        return next((album for album in self.albums if album.id == album_id), None)

    def screen_point_for(self, album: Album) -> QPointF:
        x, y = self.camera.world_to_screen(album.x, album.y, self.width(), self.height())
        return QPointF(x, y)

    def set_albums(self, albums: tuple[Album, ...]) -> None:
        self.albums = tuple(albums)
        self._artwork_generation += 1
        self._artwork_cache.clear()
        self._artwork_missing.clear()
        self._artwork_resolved.clear()
        self._artwork_pending.clear()
        self._artwork_view_key = None
        self._artwork_view_budget = self._artwork_batch_limit
        self._artwork_request_timer.stop()
        if self.focused_id and self.album_by_id(self.focused_id) is None:
            self.focused_id = None
            self._lens_open = False
        if self._playing_album_id and self.album_by_id(self._playing_album_id) is None:
            self._playing_album_id = None
        self._visible_ids = ()
        self._refresh_accessible_description()
        self.update()

    def set_trace(self, entries: list[dict] | tuple[dict, ...]) -> None:
        """Update the bounded local route shown by the attached album lens."""
        self._lens_trace_entries = [
            {
                "album_id": str(item.get("album_id") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "artist": str(item.get("artist") or "").strip(),
                "activity": str(item.get("activity") or "explore"),
                "recorded_at": float(item.get("recorded_at") or 0.0),
                "playable": bool(item.get("playable")),
            }
            for item in entries
            if isinstance(item, dict) and str(item.get("album_id") or "").strip()
        ][:48]
        max_offset = max(0, len(self._lens_trace_entries) - 1)
        self._lens_trace_offset = min(self._lens_trace_offset, max_offset)
        self._refresh_accessible_description()
        self.update()

    def set_playback_state(
        self,
        track: dict | None,
        *,
        playing: bool,
        position_ms: int = 0,
        duration_ms: int = 0,
        album_id: str | None = None,
        can_next: bool = False,
    ) -> None:
        self._current_track = dict(track) if isinstance(track, dict) else None
        self._playing_album_id = album_id
        self._playing = bool(playing and self._current_track)
        self._position_ms = max(0, int(position_ms))
        self._duration_ms = max(0, int(duration_ms))
        self._can_next = bool(can_next)
        self._refresh_accessible_description()
        self.update()

    def set_arc_state(
        self,
        *,
        active: bool,
        paused: bool = False,
        next_album: Album | None = None,
        reason: str = "",
    ) -> None:
        self._arc_active = bool(active)
        self._arc_paused = bool(active and paused)
        self._arc_next_album = next_album if active else None
        self._arc_reason = str(reason or "") if active else ""
        self._refresh_accessible_description()
        self.update()

    def _request_album_play(self, album: Album) -> None:
        if self.live_playback:
            self.playRequested.emit(album.id)
        else:
            self.mock_play_album(album)

    def focus_album(self, album: Album | None) -> None:
        next_id = album.id if album else None
        if next_id != self.focused_id:
            self._lens_open = False
            self._lens_panel = "horizon"
        self.focused_id = next_id
        if album is None:
            self.setFocus(Qt.OtherFocusReason)
        elif next_id:
            self.albumFocused.emit(next_id)
        self._refresh_accessible_description()
        self.update()

    def open_lens(self) -> bool:
        if self.album_by_id(self.focused_id) is None:
            return False
        self._lens_open = True
        self._refresh_accessible_description()
        self.update()
        return True

    def _focus_adjacent_album(self, direction: int) -> bool:
        if not self.albums:
            return False
        step = 1 if direction >= 0 else -1
        ids = tuple(album.id for album in self.albums)
        try:
            current_index = ids.index(self.focused_id)
        except ValueError:
            current_index = -1 if step > 0 else 0
        target = self.albums[(current_index + step) % len(self.albums)]
        lens_was_open = self._lens_open
        self.camera.center_x = target.x
        self.camera.center_y = target.y
        self.hovered_id = None
        self._hover_position = None
        self.focus_album(target)
        if lens_was_open:
            self.open_lens()
        self.update()
        return True

    def _follow_horizon_link(self, index: int) -> bool:
        if index < 0 or index >= len(self._lens_horizon_targets):
            return False
        target = self.album_by_id(self._lens_horizon_targets[index])
        if target is None:
            return False
        self.camera.center_x = target.x
        self.camera.center_y = target.y
        self.focus_album(target)
        self.open_lens()
        self.hovered_id = None
        self._hover_position = None
        self._lens_horizon_hover_index = -1
        self._refresh_accessible_description()
        self.update()
        return True

    def _page_trace(self, direction: int) -> bool:
        step = max(1, self._lens_trace_page_size)
        if direction > 0:
            if self._lens_trace_offset + step >= len(self._lens_trace_entries):
                return False
            self._lens_trace_offset = min(
                len(self._lens_trace_entries) - 1,
                self._lens_trace_offset + step,
            )
        else:
            if self._lens_trace_offset <= 0:
                return False
            self._lens_trace_offset = max(0, self._lens_trace_offset - step)
        self._refresh_accessible_description()
        self.update()
        return True

    def _follow_trace_entry(self, index: int) -> bool:
        if index < 0 or index >= len(self._lens_trace_targets):
            return False
        target = self.album_by_id(self._lens_trace_targets[index])
        if target is None:
            return False
        self.camera.center_x = target.x
        self.camera.center_y = target.y
        self.focus_album(target)
        self._lens_panel = "horizon"
        self.open_lens()
        self.hovered_id = None
        self._hover_position = None
        self._lens_trace_hover_index = -1
        self.update()
        return True

    def _lens_tabs_for(self, rect: QRectF) -> tuple[QRectF, QRectF]:
        left = rect.left() + 12.0
        top = rect.top() + 119.0
        width = max(1.0, (rect.width() - 24.0) / 2.0)
        return (
            QRectF(left, top, width - 2.0, 19.0),
            QRectF(left + width + 2.0, top, width - 2.0, 19.0),
        )

    def _lens_trace_layout(
        self, rect: QRectF
    ) -> tuple[tuple[QRectF, ...], tuple[QRectF, ...], tuple[str, ...], QRectF, QRectF]:
        end_y = (
            self._lens_arc_rect.top() - 15.0
            if self.live_playback
            else rect.bottom() - 28.0
        )
        start_y = rect.top() + 143.0
        older = QRectF()
        newer = QRectF()
        needs_paging = len(self._lens_trace_entries) > 2
        if needs_paging:
            older = QRectF(rect.left() + 14.0, end_y - 16.0, 76.0, 14.0)
            newer = QRectF(rect.right() - 90.0, end_y - 16.0, 76.0, 14.0)
            end_y -= 19.0
        row_height = 34.0
        row_count = max(0, min(2, int((end_y - start_y) // row_height)))
        self._lens_trace_page_size = max(1, row_count)
        if row_count == 0:
            return (), (), (), QRectF(), QRectF()
        offset = min(self._lens_trace_offset, max(0, len(self._lens_trace_entries) - 1))
        visible = self._lens_trace_entries[offset : offset + row_count]
        row_rects: list[QRectF] = []
        play_rects: list[QRectF] = []
        targets: list[str] = []
        for index, item in enumerate(visible):
            y = start_y + index * row_height
            row_rects.append(QRectF(rect.left() + 11.0, y, rect.width() - 22.0, 31.0))
            play_rects.append(QRectF(rect.right() - 38.0, y + 6.0, 20.0, 20.0))
            targets.append(str(item.get("album_id") or ""))
        return tuple(row_rects), tuple(play_rects), tuple(targets), older, newer

    def close_lens(self) -> bool:
        if not self._lens_open:
            return False
        self._lens_open = False
        self._lens_close_hovered = False
        self._lens_horizon_hover_index = -1
        self.update()
        return True

    def mock_play_album(self, album: Album) -> None:
        self.focus_album(album)
        self._play_toast = f"Mock play · {album.title}"
        self._toast_timer.start(2400)
        self.mockPlayed.emit(album.id)
        self.update()

    def release_focus(self) -> None:
        self.focus_album(None)

    def return_home(self) -> None:
        self.camera.home()
        self.release_focus()
        self.hovered_id = None
        self._home_cue_hovered = False
        self.update()

    def reveal_album(self, album_id: str, *, open_lens: bool = True) -> bool:
        """Bring a known collection album into view without leaving the field."""
        album = self.album_by_id(str(album_id or ""))
        if album is None:
            return False
        self.camera.center_x = album.x
        self.camera.center_y = album.y
        self.hovered_id = None
        self._hover_position = None
        self.focus_album(album)
        if open_lens:
            self.open_lens()
        self.update()
        return True

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt virtual method
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self._draw_background(painter)
        self._draw_regions(painter)
        self._draw_horizon_links(painter)
        self._draw_albums(painter)
        self._draw_overlays(painter)
        painter.end()

    def _draw_background(self, painter: QPainter) -> None:
        bounds = self.rect()
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor("#111a20"))
        gradient.setColorAt(0.48, QColor("#0b1218"))
        gradient.setColorAt(1.0, QColor("#11191e"))
        painter.fillRect(bounds, gradient)

        for x, y, color in ((0.22, 0.28, "#38574f"), (0.78, 0.70, "#453858"), (0.72, 0.24, "#5a4935")):
            haze = QRadialGradient(QPointF(self.width() * x, self.height() * y), self.width() * 0.52)
            tint = QColor(color)
            tint.setAlpha(32)
            haze.setColorAt(0.0, tint)
            tint.setAlpha(0)
            haze.setColorAt(1.0, tint)
            painter.fillRect(bounds, haze)

        vignette = QRadialGradient(
            QPointF(self.width() / 2, self.height() / 2), max(self.width(), self.height()) * 0.76
        )
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 95))
        painter.fillRect(bounds, vignette)

    def _draw_regions(self, painter: QPainter) -> None:
        if semantic_zoom_level(self.camera.zoom) is SemanticLevel.DETAIL:
            return
        regions: dict[str, tuple[float, float, int]] = {}
        for album in self.albums:
            if not album.region:
                continue
            total_x, total_y, count = regions.get(album.region, (0.0, 0.0, 0))
            regions[album.region] = (total_x + album.x, total_y + album.y, count + 1)
        painter.save()
        font = QFont("Sans Serif", 9)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        for region, (total_x, total_y, count) in regions.items():
            x, y = total_x / count, total_y / count
            sx, sy = self.camera.world_to_screen(x, y, self.width(), self.height())
            painter.setPen(QColor(208, 221, 211, 70))
            painter.drawText(QPointF(sx - 74, sy - 76), region)
        painter.restore()

    def _draw_horizon_links(self, painter: QPainter) -> None:
        album = self.album_by_id(self.focused_id) if self._lens_open else None
        if album is None:
            return
        horizon = album_horizon(self.albums, album, max_links=3)
        source_point = self.screen_point_for(album)
        source = QPointF(
            min(max(source_point.x(), 12.0), self.width() - 12.0),
            min(max(source_point.y(), 46.0), self.height() - 46.0),
        )
        painter.save()
        for link in horizon.links:
            target = self.album_by_id(link.album_id)
            if target is None:
                continue
            point = self.screen_point_for(target)
            if (
                point.x() < -100
                or point.y() < -100
                or point.x() > self.width() + 100
                or point.y() > self.height() + 100
            ):
                continue
            if "sound" in link.kinds and ("artist" in link.kinds or "genre" in link.kinds):
                color, style = QColor("#c8a9d5"), Qt.DashDotLine
            elif "sound" in link.kinds:
                color, style = QColor("#75d9d1"), Qt.DashLine
            else:
                color, style = QColor("#e9c77c"), Qt.SolidLine
            color.setAlpha(142)
            painter.setPen(QPen(color, 1.35, style))
            painter.drawLine(source, point)
        painter.restore()

    def _draw_albums(self, painter: QPainter) -> None:
        view_margin = 120.0 + 62.0 * self.camera.zoom
        focus = self.album_by_id(self.focused_id)
        draw_items: list[tuple[Album, float, float, float]] = []
        for album in self.albums:
            sx, sy = self.camera.world_to_screen(album.x, album.y, self.width(), self.height())
            cue = album_depth_cue(album, focus, self.hovered_id)
            if sx < -view_margin or sy < -view_margin or sx > self.width() + view_margin or sy > self.height() + view_margin:
                continue
            opacity = cue.opacity
            draw_items.append((album, sx, sy, opacity))

        self._visible_ids = tuple(album.id for album, *_rest in draw_items)
        currently_visible = set(self._visible_ids)
        if self._lens_open and self.focused_id:
            currently_visible.add(self.focused_id)
        self._artwork_resolved.intersection_update(currently_visible)
        if self.live_playback and semantic_zoom_level(self.camera.zoom) is not SemanticLevel.OVERVIEW:
            view_key = (
                tuple(sorted(currently_visible)),
                self.focused_id,
                self._lens_open,
                semantic_zoom_level(self.camera.zoom).value,
            )
            if view_key != self._artwork_view_key:
                self._artwork_view_key = view_key
                self._artwork_view_budget = self._artwork_batch_limit
        else:
            self._artwork_view_key = None
            self._artwork_view_budget = self._artwork_batch_limit
        self._schedule_visible_artwork()
        horizon_target_ids: set[str] = set()
        if focus is not None and self._lens_open:
            horizon_target_ids = {
                link.album_id
                for link in album_horizon(self.albums, focus, max_links=3).links
            }
        if focus:
            draw_items.sort(key=lambda item: item[0].id == focus.id)
        for album, sx, sy, opacity in draw_items:
            focused = album.id == self.focused_id
            hovered = album.id == self.hovered_id
            playing = album.id == self._playing_album_id
            arc_target = (
                self._arc_active
                and self._arc_next_album is not None
                and album.id == self._arc_next_album.id
            )
            self._draw_album(
                painter,
                album,
                sx,
                sy,
                opacity,
                focused,
                hovered,
                playing,
                arc_target,
                album.id in horizon_target_ids,
            )

        if semantic_zoom_level(self.camera.zoom) is SemanticLevel.DETAIL:
            for album, sx, sy, _opacity in draw_items:
                if album.id in (self.focused_id, self.hovered_id):
                    continue
                painter.save()
                painter.setPen(QColor(225, 229, 218, 185))
                painter.setFont(QFont("Sans Serif", 8))
                painter.drawText(QRectF(sx - 82, sy + 54, 164, 18), Qt.AlignHCenter, album.title)
                painter.restore()

    def _draw_album(
        self,
        painter: QPainter,
        album: Album,
        sx: float,
        sy: float,
        opacity: float,
        focused: bool,
        hovered: bool,
        playing: bool,
        arc_target: bool,
        horizon_target: bool,
    ) -> None:
        focus = self.album_by_id(self.focused_id)
        cue = album_depth_cue(album, focus, self.hovered_id)
        size = 98.0 * self.camera.zoom * cue.scale

        painter.save()
        painter.setOpacity(opacity)
        painter.translate(sx, sy)
        painter.scale(size / 100.0, size / 100.0)

        if focused or hovered or (focus is not None and cue.focus_strength > 0.16):
            glow = QRadialGradient(QPointF(0, 0), 76)
            glow_alpha = 82 if focused else 58 if hovered else int(12 + 30 * cue.focus_strength)
            glow.setColorAt(0.0, QColor(241, 208, 154, glow_alpha))
            glow.setColorAt(1.0, QColor(241, 208, 154, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(-76, -76, 152, 152))

        shadow = QColor(0, 0, 0, 116 if focused else 84)
        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(QRectF(-49, -43, 98, 98), 10, 10)

        palette = _PALETTES[album.motif]
        cover = QRectF(-48, -50, 96, 96)
        path = QPainterPath()
        path.addRoundedRect(cover, 8, 8)
        painter.setClipPath(path)
        artwork = self._cached_artwork(album.id)
        if artwork is not None:
            painter.drawImage(cover, artwork)
        else:
            self._draw_motif(painter, album, palette, cover)
        painter.setClipping(False)

        border = QColor("#f3e8d3")
        border.setAlpha(208 if focused else 150 if hovered else 92)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(border, 1.4 if focused else 0.8))
        painter.drawRoundedRect(cover, 8, 8)

        if horizon_target:
            painter.setPen(QPen(QColor("#d9c594"), 1.45, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(-66, -68, 132, 132), 15, 15)
        if playing:
            painter.setPen(QPen(QColor("#75d9d1"), 2.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(-54, -56, 108, 108), 11, 11)
        if arc_target:
            painter.setPen(QPen(QColor("#e9c77c"), 2.0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(-61, -63, 122, 122), 14, 14)

        if focused or hovered:
            label_color = QColor("#f4ecdd")
            painter.setPen(label_color)
            title_font = QFont("Sans Serif", 9)
            title_font.setWeight(QFont.DemiBold)
            painter.setFont(title_font)
            painter.drawText(QRectF(-84, 52, 168, 15), Qt.AlignHCenter, album.title)
            if focused:
                painter.setPen(QColor(205, 212, 201, 180))
                painter.setFont(QFont("Sans Serif", 8))
                painter.drawText(QRectF(-84, 68, 168, 14), Qt.AlignHCenter, album.artist)
        painter.restore()

    @staticmethod
    def _draw_motif(painter: QPainter, album: Album, palette: tuple[str, str, str], rect: QRectF) -> None:
        light, dark, accent = (QColor(value) for value in palette)
        background = QLinearGradient(rect.topLeft(), rect.bottomRight())
        background.setColorAt(0.0, light)
        background.setColorAt(1.0, dark)
        painter.fillRect(rect, background)

        painter.setPen(Qt.NoPen)
        mode = album.motif
        if mode == 0:
            painter.setBrush(QColor(accent))
            painter.drawEllipse(QRectF(-26, -29, 58, 58))
            painter.setBrush(QColor(dark))
            painter.drawEllipse(QRectF(-7, -10, 37, 37))
            painter.setBrush(QColor(247, 224, 177, 210))
            painter.drawEllipse(QRectF(-18, -19, 9, 9))
        elif mode == 1:
            painter.setBrush(QColor(accent))
            painter.drawRoundedRect(QRectF(-52, -14, 104, 24), 12, 12)
            painter.setBrush(QColor(dark))
            painter.drawRoundedRect(QRectF(-42, 10, 92, 18), 9, 9)
            painter.setBrush(QColor(light))
            painter.drawRoundedRect(QRectF(-32, -38, 72, 15), 7, 7)
        elif mode == 2:
            painter.setBrush(QColor(dark))
            painter.drawEllipse(QRectF(-33, -35, 74, 74))
            painter.setBrush(QColor(accent))
            painter.drawEllipse(QRectF(-21, -23, 50, 50))
            painter.setBrush(QColor(light))
            painter.drawEllipse(QRectF(-5, -7, 18, 18))
        elif mode == 3:
            for index in range(5):
                painter.setBrush(QColor(accent if index % 2 else dark))
                painter.drawRect(QRectF(-50 + index * 23, -50, 13, 100))
            painter.setBrush(QColor(light))
            painter.drawEllipse(QRectF(-14, -14, 28, 28))
        elif mode == 4:
            painter.setBrush(QColor(dark))
            painter.drawRoundedRect(QRectF(-44, -39, 88, 76), 44, 44)
            painter.setBrush(QColor(accent))
            painter.drawRoundedRect(QRectF(-29, -26, 58, 54), 29, 29)
            painter.setBrush(QColor(light))
            painter.drawEllipse(QRectF(-8, -8, 16, 16))
        elif mode == 5:
            painter.setBrush(QColor(accent))
            triangle = QPainterPath()
            triangle.moveTo(-46, 38)
            triangle.lineTo(0, -42)
            triangle.lineTo(46, 38)
            triangle.closeSubpath()
            painter.drawPath(triangle)
            painter.setBrush(QColor(dark))
            painter.drawEllipse(QRectF(-18, -14, 36, 36))
        elif mode == 6:
            for index in range(5):
                painter.setBrush(QColor(accent if index == 2 else dark))
                painter.drawEllipse(QRectF(-35 + index * 15, -9 + (index % 2) * 10, 18, 18))
            painter.setBrush(QColor(light))
            painter.drawEllipse(QRectF(-7, -35, 14, 14))
        else:
            painter.setBrush(QColor(dark))
            painter.drawRect(QRectF(-50, 8, 100, 42))
            painter.setBrush(QColor(accent))
            painter.drawEllipse(QRectF(-32, -35, 64, 64))
            painter.setBrush(QColor(light))
            painter.drawRect(QRectF(-50, 22, 100, 5))

        painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
        painter.drawLine(QPointF(-42, -40), QPointF(38, -40))

    def _cached_artwork(self, album_id: str) -> QImage | None:
        image = self._artwork_cache.get(album_id)
        if image is not None:
            self._artwork_cache.move_to_end(album_id)
        return image

    def _schedule_visible_artwork(self) -> None:
        if (
            not self.live_playback
            or semantic_zoom_level(self.camera.zoom) is SemanticLevel.OVERVIEW
            or self._artwork_view_budget <= 0
            or self._artwork_pending
            or self._artwork_request_timer.isActive()
        ):
            return
        self._artwork_request_timer.start(90)

    def _request_visible_artwork(self) -> None:
        if (
            not self.live_playback
            or not self.isVisible()
            or semantic_zoom_level(self.camera.zoom) is SemanticLevel.OVERVIEW
            or self._artwork_view_budget <= 0
            or self._artwork_pending
        ):
            return

        candidates: list[str] = []
        if self._lens_open and self.focused_id and self.album_by_id(self.focused_id):
            candidates.append(self.focused_id)
        candidates.extend(
            album_id
            for album_id in self._visible_ids
            if album_id not in candidates
        )
        center_x, center_y = self.width() / 2, self.height() / 2
        albums_by_id = {album.id: album for album in self.albums}

        def priority(album_id: str) -> tuple[int, float]:
            album = albums_by_id.get(album_id)
            if album is None:
                distance = float("inf")
            else:
                sx, sy = self.camera.world_to_screen(
                    album.x, album.y, self.width(), self.height()
                )
                distance = hypot(sx - center_x, sy - center_y)
            return (
                0 if album_id == self.focused_id else 1,
                distance,
            )

        candidates.sort(key=priority)
        batch = [
            album_id
            for album_id in candidates
            if album_id not in self._artwork_cache
            and album_id not in self._artwork_missing
            and album_id not in self._artwork_resolved
            and album_id not in self._artwork_pending
        ][: min(self._artwork_batch_limit, self._artwork_view_budget)]
        if not batch:
            return
        self._artwork_view_budget -= len(batch)
        self._artwork_pending.update(batch)
        self.artworkRequested.emit(
            {
                "generation": self._artwork_generation,
                "album_ids": tuple(batch),
            }
        )

    def set_artwork_batch(self, result: object) -> None:
        """Apply one bounded worker result, discarding stale collection replies."""
        if not isinstance(result, dict):
            return
        try:
            generation = int(result.get("generation", -1))
        except (TypeError, ValueError):
            return
        if generation != self._artwork_generation:
            return
        requested = tuple(
            str(album_id)
            for album_id in result.get("album_ids", ())
            if str(album_id)
        )
        images = result.get("images")
        images = images if isinstance(images, dict) else {}
        for album_id in requested:
            self._artwork_pending.discard(album_id)
            image = images.get(album_id)
            if isinstance(image, QImage) and not image.isNull():
                self._artwork_cache[album_id] = image
                self._artwork_cache.move_to_end(album_id)
                self._artwork_missing.discard(album_id)
                while len(self._artwork_cache) > self._artwork_cache_limit:
                    self._artwork_cache.popitem(last=False)
            else:
                self._artwork_missing.add(album_id)
            self._artwork_resolved.add(album_id)
        self.update()
        self._schedule_visible_artwork()

    def _draw_overlays(self, painter: QPainter) -> None:
        painter.save()
        painter.setPen(QColor(225, 233, 226, 158))
        title_font = QFont("Sans Serif", 9)
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.drawText(QPointF(26, 32), "CHIASM  /  FIELD")

        status = QRectF(max(18, self.width() - 204), 14, 186, 28)
        painter.setPen(QColor(194, 211, 204, 72))
        painter.setBrush(QColor(13, 21, 24, 164))
        painter.drawRoundedRect(status, 14, 14)
        painter.setPen(QColor(221, 231, 222, 196))
        painter.setFont(QFont("Sans Serif", 8, QFont.DemiBold))
        level = semantic_zoom_level(self.camera.zoom).value.upper()
        painter.drawText(status, Qt.AlignCenter, f"{level}  ·  {self.camera.zoom:.2f}×")

        self._home_cue_rect = QRectF()
        if not self.camera.is_at_home:
            self._home_cue_rect = QRectF(max(18, self.width() - 118), 50, 100, 32)
            painter.setPen(QColor(224, 212, 181, 130))
            painter.setBrush(
                QColor(58, 54, 43, 230 if self._home_cue_hovered else 176)
            )
            painter.drawRoundedRect(self._home_cue_rect, 16, 16)
            painter.setPen(QColor("#f2dfb9"))
            painter.setFont(QFont("Sans Serif", 8, QFont.DemiBold))
            painter.drawText(
                self._home_cue_rect, Qt.AlignCenter, f"{self._home_arrow_glyph()}  HOME"
            )
        else:
            self._home_cue_hovered = False

        hint = ""
        if self.live_playback:
            hint = ""
        elif self._lens_open:
            hint = "ESC CLOSE LENS  ·  DRAG / ARROWS STILL MOVE THE FIELD"
        elif self.focused_id is not None:
            hint = "ENTER LENS  ·  ESC RELEASE FOCUS"
        elif self.hovered_id is None:
            hint = (
                "DRAG / ARROWS PAN  ·  WHEEL / PINCH ZOOM  ·  TRACKPAD SCROLL PAN  ·  "
                "+/- ZOOM  ·  CLICK FOCUS  ·  DOUBLE-CLICK PLAY  ·  H HOME  ·  ESC RELEASE"
            )
        if hint:
            painter.setPen(QColor(210, 220, 215, 112))
            painter.setFont(QFont("Sans Serif", 8))
            painter.drawText(
                QRectF(0, self.height() - 34, self.width(), 18),
                Qt.AlignHCenter,
                hint,
            )

        if self._play_toast:
            toast_width = min(340, max(220, self.width() - 40))
            toast = QRectF((self.width() - toast_width) / 2, self.height() - 70, toast_width, 38)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 22, 26, 220))
            painter.drawRoundedRect(toast, 18, 18)
            painter.setPen(QColor("#f2d7a1"))
            painter.setFont(QFont("Sans Serif", 9, QFont.DemiBold))
            painter.drawText(toast, Qt.AlignCenter, self._play_toast)

        self._draw_album_lens(painter)
        self._draw_transport(painter)
        if self.live_playback and not self.albums:
            painter.setPen(QColor(224, 231, 224, 175))
            painter.setFont(QFont("Sans Serif", 11, QFont.DemiBold))
            painter.drawText(
                QRectF(48, self.height() / 2 - 18, self.width() - 96, 36),
                Qt.AlignCenter,
                "Add a music folder to begin exploring",
            )
        painter.restore()

    def _lens_layout_for(
        self, album: Album
    ) -> tuple[QPointF, QRectF, QRectF, bool]:
        screen = self.screen_point_for(album)
        anchor_x = min(max(screen.x(), 12.0), self.width() - 12.0)
        anchor_y = min(max(screen.y(), 46.0), self.height() - 46.0)
        anchor = QPointF(anchor_x, anchor_y)

        focus_scale = album_depth_cue(album, album, self.hovered_id).scale
        offset = 49.0 * self.camera.zoom * focus_scale + 20.0
        left_space = anchor_x - offset - 16.0
        right_space = self.width() - 16.0 - anchor_x - offset
        place_right = right_space >= left_space
        available = max(left_space, right_space)
        lens_width = min(
            320.0,
            self.width() - 32.0,
            max(168.0, available - 12.0),
        )
        bottom_reserved = (
            118.0 if self.live_playback and self._arc_active else
            80.0 if self.live_playback else
            48.0
        )
        available_lens_height = max(132.0, self.height() - 46.0 - bottom_reserved)
        lens_height = min(280.0, available_lens_height)
        desired_x = anchor_x + offset if place_right else anchor_x - offset - lens_width
        desired_y = anchor_y - lens_height / 2
        left = min(max(desired_x, 16.0), self.width() - lens_width - 16.0)
        max_top = max(46.0, self.height() - bottom_reserved - lens_height)
        top = min(max(desired_y, 46.0), max_top)
        rect = QRectF(left, top, lens_width, lens_height)
        close_rect = QRectF(rect.right() - 29.0, rect.top() + 8.0, 20.0, 20.0)
        return anchor, rect, close_rect, place_right

    def _draw_album_lens(self, painter: QPainter) -> None:
        album = self.album_by_id(self.focused_id) if self._lens_open else None
        if album is None:
            self._lens_rect = QRectF()
            self._lens_close_rect = QRectF()
            self._lens_play_rect = QRectF()
            self._lens_arc_rect = QRectF()
            self._lens_horizon_tab_rect = QRectF()
            self._lens_trace_tab_rect = QRectF()
            self._lens_trace_rects = ()
            self._lens_trace_play_rects = ()
            self._lens_trace_targets = ()
            self._lens_trace_older_rect = QRectF()
            self._lens_trace_newer_rect = QRectF()
            self._lens_close_hovered = False
            self._lens_play_hovered = False
            self._lens_arc_hovered = False
            self._lens_trace_tab_hovered = False
            self._lens_horizon_tab_hovered = False
            self._lens_horizon_rects = ()
            self._lens_horizon_targets = ()
            self._lens_horizon_hover_index = -1
            self._lens_trace_hover_index = -1
            return

        anchor, rect, close_rect, place_right = self._lens_layout_for(album)
        self._lens_anchor = anchor
        self._lens_rect = rect
        self._lens_close_rect = close_rect
        self._lens_play_rect = QRectF(rect.right() - 54.0, rect.top() + 8.0, 20.0, 20.0)
        self._lens_arc_rect = QRectF(
            rect.left() + 15.0,
            rect.bottom() - 28.0,
            rect.width() - 30.0,
            20.0,
        )
        self._lens_horizon_rects = ()
        self._lens_horizon_targets = ()
        self._lens_horizon_tab_rect, self._lens_trace_tab_rect = self._lens_tabs_for(rect)

        attach_x = rect.left() if place_right else rect.right()
        attach_y = min(max(anchor.y(), rect.top() + 18.0), rect.bottom() - 18.0)
        painter.save()
        painter.setPen(QPen(QColor(237, 211, 157, 145), 1.2))
        painter.drawLine(anchor, QPointF(attach_x, attach_y))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(245, 218, 163, 215))
        painter.drawEllipse(anchor, 3.5, 3.5)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 118))
        painter.drawRoundedRect(rect.translated(0, 5), 14, 14)
        card_gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        card_gradient.setColorAt(0.0, QColor(31, 43, 43, 247))
        card_gradient.setColorAt(1.0, QColor(17, 25, 30, 247))
        painter.setBrush(card_gradient)
        painter.setPen(QPen(QColor(232, 210, 166, 112), 1.0))
        painter.drawRoundedRect(rect, 14, 14)

        painter.setPen(QColor(224, 214, 188, 176))
        painter.setFont(QFont("Sans Serif", 8, QFont.DemiBold))
        painter.drawText(
            QRectF(rect.left() + 15, rect.top() + 10, rect.width() - 90, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            "ALBUM LENS  /  HORIZON",
        )
        painter.setPen(QPen(QColor(235, 226, 206, 185 if self._lens_play_hovered else 105), 1.0))
        painter.setBrush(QColor(255, 255, 255, 34 if self._lens_play_hovered else 14))
        painter.drawEllipse(self._lens_play_rect)
        painter.setPen(QColor("#f3ead8"))
        painter.setFont(QFont("Sans Serif", 8, QFont.DemiBold))
        painter.drawText(self._lens_play_rect, Qt.AlignCenter, "▶")
        painter.setPen(QPen(QColor(235, 226, 206, 185 if self._lens_close_hovered else 105), 1.1))
        painter.setBrush(QColor(255, 255, 255, 22 if self._lens_close_hovered else 8))
        painter.drawEllipse(close_rect)
        painter.drawLine(
            QPointF(close_rect.left() + 6, close_rect.top() + 6),
            QPointF(close_rect.right() - 6, close_rect.bottom() - 6),
        )
        painter.drawLine(
            QPointF(close_rect.right() - 6, close_rect.top() + 6),
            QPointF(close_rect.left() + 6, close_rect.bottom() - 6),
        )

        cover = QRectF(rect.left() + 15, rect.top() + 38, 64, 64)
        cover_path = QPainterPath()
        cover_path.addRoundedRect(cover, 7, 7)
        painter.save()
        painter.setClipPath(cover_path)
        artwork = self._cached_artwork(album.id)
        if artwork is not None:
            painter.drawImage(cover, artwork)
        else:
            painter.translate(cover.center())
            painter.scale(0.64, 0.64)
            self._draw_motif(painter, album, _PALETTES[album.motif], QRectF(-50, -50, 100, 100))
        painter.restore()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(240, 230, 209, 132), 0.8))
        painter.drawRoundedRect(cover, 7, 7)

        text_left = cover.right() + 12
        text_width = max(20.0, rect.right() - text_left - 14)
        painter.setPen(QColor("#f3ead8"))
        painter.setFont(QFont("Sans Serif", 10, QFont.DemiBold))
        painter.drawText(
            QRectF(text_left, rect.top() + 39, text_width, 21),
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
            album.title,
        )
        painter.setPen(QColor(220, 225, 214, 218))
        painter.setFont(QFont("Sans Serif", 9))
        painter.drawText(
            QRectF(text_left, rect.top() + 61, text_width, 19),
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
            album.artist,
        )
        painter.setPen(QColor(202, 213, 203, 170))
        painter.setFont(QFont("Sans Serif", 8))
        placement = album.region or (
            f"AUDIO SAMPLE · {album.sound_sampled_tracks} TRACKS"
            if album.sound_sampled_tracks > 0
            else f"SOUND POSITION · {album.analysed_tracks} TRACKS; LINK UNSAMPLED"
            if album.analysed_tracks > 0
            else "SOUND UNMEASURED"
        )
        painter.drawText(
            QRectF(text_left, rect.top() + 81, text_width, 19),
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
            placement,
        )

        context = album_horizon(self.albums, album, max_links=3)
        separator_y = rect.top() + 113
        painter.setPen(QPen(QColor(234, 226, 208, 42), 1.0))
        painter.drawLine(
            QPointF(rect.left() + 15, separator_y),
            QPointF(rect.right() - 15, separator_y),
        )
        header_font = QFont("Sans Serif", 7, QFont.DemiBold)
        painter.setFont(header_font)
        horizon_header = (
            f"HORIZON  ·  {context.linked_count} LINKS  ·  {context.unresolved_count} UNRESOLVED"
        )
        trace_header = f"TRACE  ·  {len(self._lens_trace_entries)} STOPS"
        for tab_rect, label, active, hovered in (
            (
                self._lens_horizon_tab_rect,
                horizon_header,
                self._lens_panel == "horizon",
                self._lens_horizon_tab_hovered,
            ),
            (
                self._lens_trace_tab_rect,
                trace_header,
                self._lens_panel == "trace",
                self._lens_trace_tab_hovered,
            ),
        ):
            painter.setPen(QPen(QColor(232, 210, 166, 90 if active or hovered else 38), 0.8))
            painter.setBrush(QColor(224, 210, 177, 42 if active else 16 if hovered else 4))
            painter.drawRoundedRect(tab_rect, 6, 6)
            painter.setPen(QColor(238, 222, 190, 220 if active else 148))
            painter.drawText(
                tab_rect.adjusted(5, 0, -5, 0),
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                QFontMetrics(header_font).elidedText(
                    label,
                    Qt.ElideRight,
                    max(1, int(tab_rect.width() - 10)),
                ),
            )
        available_title_rows = (
            self._lens_arc_rect.top() - 15.0
            if self.live_playback
            else rect.bottom() - 28.0
        )
        first_title_y = separator_y + 27.0
        row_height = 32.0
        title_count = (
            min(
                len(context.links),
                max(0, int((available_title_rows - first_title_y) // row_height)),
            )
            if self._lens_panel == "horizon"
            else 0
        )
        row_rects: list[QRectF] = []
        target_ids: list[str] = []
        for index, link in enumerate(context.links[:title_count]):
            row = QRectF(
                rect.left() + 12,
                first_title_y + index * row_height,
                rect.width() - 24,
                row_height - 1,
            )
            row_rects.append(row)
            target_ids.append(link.album_id)
            hovered = index == self._lens_horizon_hover_index
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(224, 210, 177, 42 if hovered else 0))
            painter.drawRoundedRect(row, 6, 6)

            target = self.album_by_id(link.album_id)
            title = target.title if target is not None else link.album_id
            title_font = QFont("Sans Serif", 8, QFont.DemiBold)
            reason_font = QFont("Sans Serif", 7)
            painter.setPen(QColor("#f3ead8") if hovered else QColor(220, 225, 214, 220))
            painter.setFont(title_font)
            title_rect = QRectF(row.left() + 5, row.top() + 1, row.width() - 10, 14)
            painter.drawText(
                title_rect,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                QFontMetrics(title_font).elidedText(
                    title,
                    Qt.ElideRight,
                    max(1, int(title_rect.width())),
                ),
            )
            painter.setPen(QColor(190, 210, 204, 210))
            painter.setFont(reason_font)
            reason_rect = QRectF(row.left() + 5, row.top() + 15, row.width() - 10, 13)
            painter.drawText(
                reason_rect,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                QFontMetrics(reason_font).elidedText(
                    link.summary,
                    Qt.ElideRight,
                    max(1, int(reason_rect.width())),
                ),
            )
        if self._lens_panel == "horizon":
            self._lens_horizon_rects = tuple(row_rects)
            self._lens_horizon_targets = tuple(target_ids)
        else:
            self._lens_horizon_rects = ()
            self._lens_horizon_targets = ()
        if (
            self._lens_panel == "horizon"
            and not context.links
            and available_title_rows > first_title_y + 16
        ):
            unresolved_font = QFont("Sans Serif", 8)
            painter.setFont(unresolved_font)
            painter.setPen(QColor(220, 225, 214, 203))
            unresolved_rect = QRectF(
                rect.left() + 15,
                first_title_y,
                rect.width() - 30,
                34,
            )
            unresolved_lines = (
                "No named link is resolved here.",
                "This does not mean the albums are unrelated.",
            )
            for index, line in enumerate(unresolved_lines):
                line_rect = QRectF(
                    unresolved_rect.left(),
                    unresolved_rect.top() + index * 16,
                    unresolved_rect.width(),
                    15,
                )
                painter.drawText(
                    line_rect,
                    Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                    QFontMetrics(unresolved_font).elidedText(
                        line,
                        Qt.ElideRight,
                        max(1, int(line_rect.width())),
                    ),
                )
        footer_text = (
            (
                f"{context.unsampled_album_count} ALBUMS OUTSIDE AUDIO SAMPLE · DISTANCE ISN'T EVIDENCE"
                if context.unsampled_album_count > 0
                else "DISTANCE ALONE DOESN'T CREATE A LINK"
            )
            if self._lens_panel == "horizon"
            else "LOCAL ONLY · LAST 48 ALBUM STOPS"
        )
        footer_font = QFont("Sans Serif", 6, QFont.DemiBold)
        footer_rect = QRectF(
            rect.left() + 15,
            (self._lens_arc_rect.top() - 14.0)
            if self.live_playback
            else rect.bottom() - 25.0,
            rect.width() - 30,
            12.0,
        )
        if (
            self._lens_panel == "horizon"
            and footer_rect.top() >= available_title_rows
            and footer_rect.bottom() < rect.bottom() - 10
        ):
            painter.setPen(QColor(180, 196, 188, 155))
            painter.setFont(footer_font)
            painter.drawText(
                footer_rect,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                QFontMetrics(footer_font).elidedText(
                    footer_text,
                    Qt.ElideRight,
                    max(1, int(footer_rect.width())),
                ),
            )
        if self._lens_panel == "trace":
            self._draw_lens_trace_contents(
                painter,
                rect,
                first_title_y,
                available_title_rows,
                footer_rect,
            )
        if self.live_playback:
            painter.setPen(
                QPen(
                    QColor(235, 226, 206, 190 if self._lens_arc_hovered else 105),
                    1.0,
                )
            )
            painter.setBrush(
                QColor(224, 210, 177, 64 if self._lens_arc_hovered else 28)
            )
            painter.drawRoundedRect(self._lens_arc_rect, 9, 9)
            painter.setPen(QColor("#f3ead8"))
            painter.setFont(QFont("Sans Serif", 8, QFont.DemiBold))
            painter.drawText(
                self._lens_arc_rect,
                Qt.AlignCenter,
                "SET AS NEXT ALBUM" if self._arc_active else "START ARC",
            )
        painter.restore()

    @staticmethod
    def _trace_time_label(recorded_at: float) -> str:
        elapsed = max(0, int(time.time() - max(0.0, recorded_at)))
        if elapsed < 60:
            return "JUST NOW"
        if elapsed < 3600:
            return f"{elapsed // 60}M AGO"
        if elapsed < 86400:
            return f"{elapsed // 3600}H AGO"
        return f"{elapsed // 86400}D AGO"

    def _draw_lens_trace_contents(
        self,
        painter: QPainter,
        rect: QRectF,
        first_title_y: float,
        available_title_rows: float,
        footer_rect: QRectF,
    ) -> None:
        (
            self._lens_trace_rects,
            self._lens_trace_play_rects,
            self._lens_trace_targets,
            self._lens_trace_older_rect,
            self._lens_trace_newer_rect,
        ) = self._lens_trace_layout(rect)
        self._lens_trace_hover_index = min(
            self._lens_trace_hover_index,
            len(self._lens_trace_rects) - 1,
        )
        body = QRectF(
            rect.left() + 8.0,
            first_title_y - 3.0,
            rect.width() - 16.0,
            max(20.0, available_title_rows - first_title_y + 4.0),
        )
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(12, 19, 23, 100))
        painter.drawRoundedRect(body, 7, 7)
        if not self._lens_trace_entries:
            painter.setPen(QColor(215, 224, 216, 188))
            painter.setFont(QFont("Sans Serif", 8))
            painter.drawText(
                body.adjusted(9, 5, -9, -5),
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
                "Your recent album route will appear here as you explore or listen.",
            )
        else:
            visible = self._lens_trace_entries[
                self._lens_trace_offset : self._lens_trace_offset
                + len(self._lens_trace_rects)
            ]
            for index, (item, row, play_rect) in enumerate(
                zip(visible, self._lens_trace_rects, self._lens_trace_play_rects)
            ):
                hovered = index == self._lens_trace_hover_index
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(224, 210, 177, 44 if hovered else 12))
                painter.drawRoundedRect(row, 6, 6)
                available_album = self.album_by_id(str(item.get("album_id") or ""))
                title = str(item.get("title") or "").strip()
                artist = str(item.get("artist") or "").strip()
                if available_album is not None:
                    title = title or available_album.title
                    artist = artist or available_album.artist
                title = title or "Unknown album"
                artist_line = artist
                if available_album is None:
                    artist_line = f"{artist_line}  ·  NOT IN COLLECTION" if artist_line else "NOT IN COLLECTION"
                activity = str(item.get("activity") or "explore")
                if activity == "explore+listen":
                    activity_label = "EXPLORED + LISTENED"
                elif activity == "listen":
                    activity_label = "LISTENED"
                else:
                    activity_label = "EXPLORED"
                time_label = self._trace_time_label(float(item.get("recorded_at") or 0.0))
                subline = f"{activity_label}  ·  {time_label}"
                if artist_line:
                    subline = f"{artist_line}  ·  {subline}"
                can_play = bool(item.get("playable")) and available_album is not None
                text_width = row.width() - (42.0 if can_play else 10.0)
                title_font = QFont("Sans Serif", 8, QFont.DemiBold)
                subline_font = QFont("Sans Serif", 6)
                painter.setPen(QColor("#f3ead8") if hovered else QColor(220, 225, 214, 224))
                painter.setFont(title_font)
                title_rect = QRectF(row.left() + 6, row.top() + 2, text_width, 13)
                painter.drawText(
                    title_rect,
                    Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                    QFontMetrics(title_font).elidedText(
                        title,
                        Qt.ElideRight,
                        max(1, int(title_rect.width())),
                    ),
                )
                painter.setPen(QColor(180, 200, 192, 205))
                painter.setFont(subline_font)
                subline_rect = QRectF(row.left() + 6, row.top() + 16, text_width, 12)
                painter.drawText(
                    subline_rect,
                    Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                    QFontMetrics(subline_font).elidedText(
                        subline,
                        Qt.ElideRight,
                        max(1, int(subline_rect.width())),
                    ),
                )
                if can_play:
                    painter.setPen(QPen(QColor(232, 221, 197, 128 if hovered else 76), 0.8))
                    painter.setBrush(QColor(224, 210, 177, 48 if hovered else 20))
                    painter.drawRoundedRect(play_rect, 6, 6)
                    painter.setPen(QColor("#f3ead8"))
                    painter.setFont(QFont("Sans Serif", 8, QFont.DemiBold))
                    painter.drawText(play_rect, Qt.AlignCenter, "▶")

            if not self._lens_trace_rects:
                painter.setPen(QColor(215, 224, 216, 178))
                painter.setFont(QFont("Sans Serif", 8))
                painter.drawText(
                    body.adjusted(8, 3, -8, -3),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    "Give the lens more height to read this trace.",
                )
            if self._lens_trace_older_rect.isValid():
                older_enabled = (
                    self._lens_trace_offset + len(self._lens_trace_rects)
                    < len(self._lens_trace_entries)
                )
                newer_enabled = self._lens_trace_offset > 0
                painter.setFont(QFont("Sans Serif", 6, QFont.DemiBold))
                painter.setPen(QColor(220, 210, 187, 195 if older_enabled else 76))
                painter.drawText(
                    self._lens_trace_older_rect,
                    Qt.AlignLeft | Qt.AlignVCenter,
                    "‹ EARLIER",
                )
                painter.setPen(QColor(220, 210, 187, 195 if newer_enabled else 76))
                painter.drawText(
                    self._lens_trace_newer_rect,
                    Qt.AlignRight | Qt.AlignVCenter,
                    "LATER ›",
                )
        painter.setPen(QColor(180, 196, 188, 155))
        painter.setFont(QFont("Sans Serif", 6, QFont.DemiBold))
        painter.drawText(
            footer_rect,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
            QFontMetrics(QFont("Sans Serif", 6, QFont.DemiBold)).elidedText(
                "LOCAL ONLY · LAST 48 ALBUM STOPS",
                Qt.ElideRight,
                max(1, int(footer_rect.width())),
            ),
        )
        painter.restore()

    def _draw_transport(self, painter: QPainter) -> None:
        if not self.live_playback:
            self._transport_rect = QRectF()
            self._transport_play_rect = QRectF()
            self._transport_next_rect = QRectF()
            self._arc_status_rect = QRectF()
            self._arc_toggle_rect = QRectF()
            self._arc_take_control_rect = QRectF()
            self._transport_hover = ""
            self._arc_control_hover = ""
            return

        width = min(410.0, self.width() - 36.0)
        panel_height = 92.0 if self._arc_active else 54.0
        self._transport_rect = QRectF(
            18.0,
            self.height() - panel_height - 18.0,
            width,
            panel_height,
        )
        self._transport_play_rect = QRectF(
            self._transport_rect.left() + 10,
            self._transport_rect.top() + 10,
            32,
            32,
        )
        self._transport_next_rect = QRectF(
            self._transport_rect.left() + 48,
            self._transport_rect.top() + 10,
            32,
            32,
        )
        if self._arc_active:
            self._arc_status_rect = QRectF(
                self._transport_rect.left() + 10,
                self._transport_rect.top() + 59,
                self._transport_rect.width() - 150,
                22,
            )
            self._arc_toggle_rect = QRectF(
                self._transport_rect.right() - 134,
                self._transport_rect.top() + 58,
                60,
                24,
            )
            self._arc_take_control_rect = QRectF(
                self._transport_rect.right() - 68,
                self._transport_rect.top() + 58,
                58,
                24,
            )
        else:
            self._arc_status_rect = QRectF()
            self._arc_toggle_rect = QRectF()
            self._arc_take_control_rect = QRectF()
            self._arc_control_hover = ""

        painter.save()
        painter.setPen(QPen(QColor(221, 230, 221, 74), 1.0))
        painter.setBrush(QColor(13, 21, 24, 222))
        painter.drawRoundedRect(self._transport_rect, 15, 15)

        painter.setPen(Qt.NoPen)
        painter.setBrush(
            QColor(224, 210, 177, 220 if self._transport_hover == "play" else 174)
            if self._current_track
            else QColor(106, 115, 112, 116)
        )
        painter.drawRoundedRect(self._transport_play_rect, 10, 10)
        painter.setPen(QColor("#101a1e"))
        painter.setFont(QFont("Sans Serif", 10, QFont.DemiBold))
        painter.drawText(
            self._transport_play_rect,
            Qt.AlignCenter,
            "Ⅱ" if self._playing else "▶",
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(
            QColor(224, 210, 177, 220 if self._transport_hover == "next" else 174)
            if self._can_next
            else QColor(106, 115, 112, 116)
        )
        painter.drawRoundedRect(self._transport_next_rect, 10, 10)
        painter.setPen(QColor("#101a1e"))
        painter.setFont(QFont("Sans Serif", 10, QFont.DemiBold))
        painter.drawText(self._transport_next_rect, Qt.AlignCenter, "›")

        text_rect = QRectF(
            self._transport_rect.left() + 91,
            self._transport_rect.top() + 7,
            self._transport_rect.width() - 103,
            23,
        )
        if self._current_track:
            artist = str(self._current_track.get("artist") or "Unknown artist")
            title = str(self._current_track.get("title") or "Unknown track")
            status = f"{artist}  ·  {title}"
            subline = "PLAYING" if self._playing else "PAUSED"
            if self._duration_ms > 0:
                current_seconds = self._position_ms // 1000
                total_seconds = self._duration_ms // 1000
                subline += (
                    f"  ·  {current_seconds // 60}:{current_seconds % 60:02d}"
                    f" / {total_seconds // 60}:{total_seconds % 60:02d}"
                )
        else:
            status = (
                "Double-click an album to play"
                if self.albums
                else "Add local music to build this field"
            )
            subline = "LOCAL COLLECTION"
        painter.setPen(QColor("#f0eadb"))
        painter.setFont(QFont("Sans Serif", 9, QFont.DemiBold))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, status)
        painter.setPen(QColor(188, 204, 197, 174))
        painter.setFont(QFont("Sans Serif", 7, QFont.DemiBold))
        painter.drawText(
            QRectF(text_rect.left(), text_rect.top() + 19, text_rect.width(), 16),
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
            subline,
        )
        if self._arc_active:
            if self._arc_next_album is not None:
                route_text = (
                    f"ARC · NEXT {self._arc_next_album.artist} — "
                    f"{self._arc_next_album.title} · {self._arc_reason}"
                )
            else:
                route_text = "ARC · END OF EXPLAINABLE ROUTE"
            painter.setPen(QColor(239, 224, 187, 205))
            painter.setFont(QFont("Sans Serif", 7, QFont.DemiBold))
            painter.drawText(
                self._arc_status_rect,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                route_text,
            )
            painter.setPen(
                QPen(
                    QColor(235, 226, 206, 195 if self._arc_control_hover == "toggle" else 105),
                    1.0,
                )
            )
            painter.setBrush(
                QColor(224, 210, 177, 64 if self._arc_control_hover == "toggle" else 24)
            )
            painter.drawRoundedRect(self._arc_toggle_rect, 8, 8)
            painter.setPen(QColor("#f3ead8"))
            painter.setFont(QFont("Sans Serif", 7, QFont.DemiBold))
            painter.drawText(
                self._arc_toggle_rect,
                Qt.AlignCenter,
                "RESUME" if self._arc_paused else "PAUSE ARC",
            )
            painter.setPen(
                QPen(
                    QColor(235, 226, 206, 195 if self._arc_control_hover == "control" else 105),
                    1.0,
                )
            )
            painter.setBrush(
                QColor(224, 210, 177, 64 if self._arc_control_hover == "control" else 24)
            )
            painter.drawRoundedRect(self._arc_take_control_rect, 8, 8)
            painter.setPen(QColor("#f3ead8"))
            painter.drawText(
                self._arc_take_control_rect,
                Qt.AlignCenter,
                "TAKE OVER",
            )
        painter.restore()

    def _home_arrow_glyph(self) -> str:
        dx = -self.camera.center_x * self.camera.zoom
        dy = -self.camera.center_y * self.camera.zoom
        if hypot(dx, dy) < 2.0:
            return "•"
        directions = ("→", "↘", "↓", "↙", "←", "↖", "↑", "↗")
        index = round(atan2(dy, dx) / (pi / 4)) % len(directions)
        return directions[index]

    def _hit_test(self, screen_x: float, screen_y: float) -> Album | None:
        world_x, world_y = self.camera.screen_to_world(
            screen_x, screen_y, self.width(), self.height()
        )
        candidates: list[tuple[float, Album]] = []
        focus = self.album_by_id(self.focused_id)
        for album in self.albums:
            radius = album_hit_radius(
                album, focus, self.hovered_id, self.camera.zoom
            )
            distance = hypot(album.x - world_x, album.y - world_y)
            if distance <= radius:
                candidates.append((distance, album))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def _update_hover_at(self, position: QPointF) -> None:
        in_transport = self.live_playback and self._transport_rect.contains(position)
        transport_hover = ""
        arc_control_hover = ""
        if in_transport:
            if self._transport_play_rect.contains(position) and self._current_track:
                transport_hover = "play"
            elif self._transport_next_rect.contains(position) and self._can_next:
                transport_hover = "next"
            elif self._arc_active and self._arc_toggle_rect.contains(position):
                arc_control_hover = "toggle"
            elif self._arc_active and self._arc_take_control_rect.contains(position):
                arc_control_hover = "control"
        in_lens = False
        close_hovered = False
        play_hovered = False
        arc_hovered = False
        horizon_hover_index = -1
        trace_hover_index = -1
        horizon_tab_hovered = False
        trace_tab_hovered = False
        trace_control_hovered = False
        if self._lens_open and not in_transport:
            album = self.album_by_id(self.focused_id)
            if album is not None:
                _anchor, self._lens_rect, self._lens_close_rect, _place_right = (
                    self._lens_layout_for(album)
                )
                self._lens_play_rect = QRectF(
                    self._lens_rect.right() - 54.0,
                    self._lens_rect.top() + 8.0,
                    20.0,
                    20.0,
                )
                self._lens_arc_rect = QRectF(
                    self._lens_rect.left() + 15.0,
                    self._lens_rect.bottom() - 28.0,
                    self._lens_rect.width() - 30.0,
                    20.0,
                )
                (
                    self._lens_horizon_tab_rect,
                    self._lens_trace_tab_rect,
                ) = self._lens_tabs_for(self._lens_rect)
                in_lens = self._lens_rect.contains(position)
                close_hovered = self._lens_close_rect.contains(position)
                play_hovered = self._lens_play_rect.contains(position)
                arc_hovered = self.live_playback and self._lens_arc_rect.contains(position)
                horizon_tab_hovered = self._lens_horizon_tab_rect.contains(position)
                trace_tab_hovered = self._lens_trace_tab_rect.contains(position)
                if self._lens_panel == "horizon":
                    horizon_hover_index = next(
                        (
                            index
                            for index, rect in enumerate(self._lens_horizon_rects)
                            if rect.contains(position)
                        ),
                        -1,
                    )
                else:
                    (
                        self._lens_trace_rects,
                        self._lens_trace_play_rects,
                        self._lens_trace_targets,
                        self._lens_trace_older_rect,
                        self._lens_trace_newer_rect,
                    ) = self._lens_trace_layout(self._lens_rect)
                    trace_hover_index = next(
                        (
                            index
                            for index, rect in enumerate(self._lens_trace_rects)
                            if rect.contains(position)
                        ),
                        -1,
                    )
                    trace_control_hovered = (
                        trace_hover_index >= 0
                        or self._lens_trace_older_rect.contains(position)
                        or self._lens_trace_newer_rect.contains(position)
                    )
        home_hovered = (
            not in_lens
            and not in_transport
            and not self.camera.is_at_home
            and self._home_cue_rect.contains(position)
        )
        hovered = (
            None
            if home_hovered or in_lens or in_transport
            else self._hit_test(position.x(), position.y())
        )
        next_id = hovered.id if hovered else None
        changed = (
            next_id != self.hovered_id
            or home_hovered != self._home_cue_hovered
            or close_hovered != self._lens_close_hovered
            or play_hovered != self._lens_play_hovered
            or arc_hovered != self._lens_arc_hovered
            or horizon_hover_index != self._lens_horizon_hover_index
            or trace_hover_index != self._lens_trace_hover_index
            or horizon_tab_hovered != self._lens_horizon_tab_hovered
            or trace_tab_hovered != self._lens_trace_tab_hovered
            or transport_hover != self._transport_hover
            or arc_control_hover != self._arc_control_hover
        )
        self.hovered_id = next_id
        self._home_cue_hovered = home_hovered
        self._lens_close_hovered = close_hovered
        self._lens_play_hovered = play_hovered
        self._lens_arc_hovered = arc_hovered
        self._lens_horizon_hover_index = horizon_hover_index
        self._lens_trace_hover_index = trace_hover_index
        self._lens_horizon_tab_hovered = horizon_tab_hovered
        self._lens_trace_tab_hovered = trace_tab_hovered
        self._transport_hover = transport_hover
        self._arc_control_hover = arc_control_hover
        if (
            close_hovered
            or play_hovered
            or arc_hovered
            or horizon_hover_index >= 0
            or trace_hover_index >= 0
            or horizon_tab_hovered
            or trace_tab_hovered
            or trace_control_hovered
            or home_hovered
            or hovered
            or transport_hover
            or arc_control_hover
        ):
            self.setCursor(Qt.PointingHandCursor)
        elif in_lens or in_transport:
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        if changed:
            self.update()

    def _refresh_hover_after_camera_motion(self) -> None:
        if self._hover_position is None:
            self.hovered_id = None
            self._home_cue_hovered = False
            return
        self._update_hover_at(self._hover_position)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._hover_position = event.position()
            self._lens_click_position = None
            if self.live_playback and self._transport_rect.contains(event.position()):
                if self._transport_play_rect.contains(event.position()) and self._current_track:
                    self.playPauseRequested.emit()
                elif self._transport_next_rect.contains(event.position()) and self._can_next:
                    self.nextRequested.emit()
                elif self._arc_active and self._arc_toggle_rect.contains(event.position()):
                    self.arcPauseRequested.emit()
                elif self._arc_active and self._arc_take_control_rect.contains(event.position()):
                    self.arcTakeControlRequested.emit()
                event.accept()
                return
            if self._lens_open:
                album = self.album_by_id(self.focused_id)
                if album is not None:
                    (
                        _anchor,
                        self._lens_rect,
                        self._lens_close_rect,
                        _place_right,
                    ) = self._lens_layout_for(album)
                    self._lens_play_rect = QRectF(
                        self._lens_rect.right() - 54.0,
                        self._lens_rect.top() + 8.0,
                        20.0,
                        20.0,
                    )
                    self._lens_arc_rect = QRectF(
                        self._lens_rect.left() + 15.0,
                        self._lens_rect.bottom() - 28.0,
                        self._lens_rect.width() - 30.0,
                        20.0,
                    )
                    (
                        self._lens_horizon_tab_rect,
                        self._lens_trace_tab_rect,
                    ) = self._lens_tabs_for(self._lens_rect)
                    if self._lens_panel == "trace":
                        (
                            self._lens_trace_rects,
                            self._lens_trace_play_rects,
                            self._lens_trace_targets,
                            self._lens_trace_older_rect,
                            self._lens_trace_newer_rect,
                        ) = self._lens_trace_layout(self._lens_rect)
                if self._lens_rect.contains(event.position()):
                    self._lens_click_position = event.position()
                    if self._lens_trace_tab_rect.contains(event.position()):
                        self._lens_panel = "trace"
                        self._lens_trace_offset = 0
                        self._lens_trace_hover_index = -1
                        self._refresh_accessible_description()
                        self.update()
                    elif self._lens_horizon_tab_rect.contains(event.position()):
                        self._lens_panel = "horizon"
                        self._lens_horizon_hover_index = -1
                        self._refresh_accessible_description()
                        self.update()
                    elif self._lens_panel == "trace":
                        trace_index = next(
                            (
                                index
                                for index, row in enumerate(self._lens_trace_rects)
                                if row.contains(event.position())
                            ),
                            -1,
                        )
                        play_index = next(
                            (
                                index
                                for index, rect in enumerate(self._lens_trace_play_rects)
                                if rect.contains(event.position())
                            ),
                            -1,
                        )
                        visible = self._lens_trace_entries[
                            self._lens_trace_offset : self._lens_trace_offset
                            + len(self._lens_trace_rects)
                        ]
                        if (
                            play_index >= 0
                            and play_index < len(visible)
                            and visible[play_index].get("playable")
                            and self.album_by_id(self._lens_trace_targets[play_index])
                            is not None
                        ):
                            self.playRequested.emit(self._lens_trace_targets[play_index])
                        elif trace_index >= 0:
                            self._follow_trace_entry(trace_index)
                        elif self._lens_trace_older_rect.contains(event.position()):
                            self._page_trace(1)
                        elif self._lens_trace_newer_rect.contains(event.position()):
                            self._page_trace(-1)
                        elif self._lens_close_rect.contains(event.position()):
                            self.close_lens()
                            self._update_hover_at(event.position())
                    else:
                        horizon_index = next(
                            (
                                index
                                for index, row in enumerate(self._lens_horizon_rects)
                                if row.contains(event.position())
                            ),
                            -1,
                        )
                        if horizon_index >= 0:
                            self._follow_horizon_link(horizon_index)
                        elif self._lens_play_rect.contains(event.position()):
                            if album is not None:
                                self._request_album_play(album)
                        elif self.live_playback and self._lens_arc_rect.contains(event.position()):
                            if album is not None:
                                if self._arc_active:
                                    self.arcSteerRequested.emit(album.id)
                                else:
                                    self.arcRequested.emit(album.id)
                        elif self._lens_close_rect.contains(event.position()):
                            self.close_lens()
                            self._update_hover_at(event.position())
                    event.accept()
                    return
            if not self.camera.is_at_home and self._home_cue_rect.contains(event.position()):
                self.return_home()
                self.setCursor(Qt.OpenHandCursor)
                event.accept()
                return
            self._pressed_at = event.position()
            self._last_pointer = event.position()
            self._dragging = False
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        position = event.position()
        self._hover_position = position
        if self._pressed_at is not None and self._last_pointer is not None:
            delta = position - self._last_pointer
            crossed_drag_threshold = (
                position - self._pressed_at
            ).manhattanLength() >= QApplication.startDragDistance()
            if crossed_drag_threshold and not self._dragging:
                # Preserve the motion gathered while the pointer was inside the
                # platform's click tolerance so the album does not jump behind
                # the cursor when a drag becomes intentional.
                delta = position - self._pressed_at
            if crossed_drag_threshold:
                self._dragging = True
                self.camera.pan_screen(delta.x(), delta.y())
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
            self._last_pointer = position
        else:
            self._update_hover_at(position)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._pressed_at is not None:
            if not self._dragging:
                album = self._hit_test(event.position().x(), event.position().y())
                if album:
                    self.focus_album(album)
                else:
                    self.release_focus()
            self._pressed_at = None
            self._last_pointer = None
            self._dragging = False
            self._hover_position = event.position()
            self._update_hover_at(event.position())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            if self.live_playback and self._transport_rect.contains(event.position()):
                event.accept()
                return
            if self._lens_click_position is not None:
                same_lens_click = (
                    event.position() - self._lens_click_position
                ).manhattanLength() <= QApplication.startDragDistance()
                self._lens_click_position = None
                if same_lens_click:
                    event.accept()
                    return
            if self._lens_open and self._lens_rect.contains(event.position()):
                event.accept()
                return
            album = self._hit_test(event.position().x(), event.position().y())
            if album:
                self._request_album_play(album)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()
        device = event.device()
        is_touchpad = (
            device is not None
            and device.type() == QInputDevice.DeviceType.TouchPad
        )

        if not pixel_delta.isNull():
            self.camera.pan_screen(pixel_delta.x(), pixel_delta.y())
            self._refresh_hover_after_camera_motion()
            self.update()
            event.accept()
            return

        if is_touchpad and not angle_delta.isNull():
            self.camera.pan_screen(
                angle_delta.x() * 0.4,
                angle_delta.y() * 0.4,
            )
            self._refresh_hover_after_camera_motion()
            self.update()
            event.accept()
            return

        if angle_delta.x():
            self.camera.pan_screen(angle_delta.x() * 0.4, 0.0)

        if angle_delta.y():
            self.camera.zoom_at(
                1.0018**angle_delta.y(),
                event.position().x(),
                event.position().y(),
                self.width(),
                self.height(),
            )
            self._refresh_hover_after_camera_motion()
            self.update()
            event.accept()
            return
        if angle_delta.x():
            self._refresh_hover_after_camera_motion()
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def event(self, event) -> bool:  # noqa: A003 - Qt virtual method
        label = self._INTERACTION_EVENT_LABELS.get(event.type(), "")
        if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.LeftButton:
            label = "chiasm:drag"
        started_at = time.perf_counter() if label else 0.0
        try:
            return self._dispatch_field_event(event)
        finally:
            if label:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                self.interactionMeasured.emit(label, max(0.0, elapsed_ms))

    def _dispatch_field_event(self, event) -> bool:
        if event.type() == QEvent.Type.NativeGesture:
            if event.gestureType() == Qt.ZoomNativeGesture:
                factor = max(0.01, 1.0 + event.value())
                position = event.position()
                self.camera.zoom_at(
                    factor,
                    position.x(),
                    position.y(),
                    self.width(),
                    self.height(),
                )
            elif event.gestureType() == Qt.PanNativeGesture:
                delta = event.delta()
                self.camera.pan_screen(delta.x(), delta.y())
            else:
                return super().event(event)
            self._refresh_hover_after_camera_motion()
            self.update()
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if (
            event.key() == Qt.Key_F
            and event.modifiers() & Qt.ControlModifier
        ):
            self.findRequested.emit()
            event.accept()
        elif event.key() == Qt.Key_Escape:
            if self._lens_open:
                self.close_lens()
            else:
                self.release_focus()
            event.accept()
        elif (
            self._lens_open
            and event.key() == Qt.Key_Tab
            and event.modifiers() & Qt.ControlModifier
        ):
            backwards = bool(event.modifiers() & Qt.ShiftModifier)
            if backwards:
                self._lens_panel = "horizon" if self._lens_panel == "trace" else "trace"
            else:
                self._lens_panel = "trace" if self._lens_panel == "horizon" else "horizon"
            self._refresh_accessible_description()
            self.update()
            event.accept()
        elif event.key() in (Qt.Key_BracketLeft, Qt.Key_BracketRight):
            direction = -1 if event.key() == Qt.Key_BracketLeft else 1
            self._focus_adjacent_album(direction)
            event.accept()
        elif self.live_playback and event.key() == Qt.Key_Space:
            if self._current_track:
                self.playPauseRequested.emit()
            event.accept()
        elif self.live_playback and event.key() == Qt.Key_N:
            if self._can_next:
                self.nextRequested.emit()
            event.accept()
        elif self.live_playback and event.key() == Qt.Key_A and self.focused_id is not None:
            if self._arc_active:
                self.arcSteerRequested.emit(self.focused_id)
            else:
                self.arcRequested.emit(self.focused_id)
            event.accept()
        elif self.live_playback and event.key() == Qt.Key_T and self._arc_active:
            self.arcTakeControlRequested.emit()
            event.accept()
        elif (
            self.live_playback
            and event.modifiers() & Qt.ControlModifier
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
            and self.focused_id is not None
        ):
            self.playRequested.emit(self.focused_id)
            event.accept()
        elif self._lens_open and self._lens_panel == "trace" and event.key() in (
            Qt.Key_PageUp,
            Qt.Key_PageDown,
        ):
            self._page_trace(1 if event.key() == Qt.Key_PageUp else -1)
            event.accept()
        elif self._lens_open and self._lens_panel == "trace" and event.key() in (
            Qt.Key_1,
            Qt.Key_2,
            Qt.Key_3,
        ):
            self._follow_trace_entry((Qt.Key_1, Qt.Key_2, Qt.Key_3).index(event.key()))
            event.accept()
        elif self._lens_open and event.key() in (Qt.Key_1, Qt.Key_2, Qt.Key_3):
            self._follow_horizon_link((Qt.Key_1, Qt.Key_2, Qt.Key_3).index(event.key()))
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.focused_id is not None:
            if self._lens_open:
                self.close_lens()
            else:
                self.open_lens()
            event.accept()
        elif event.key() in (Qt.Key_Home, Qt.Key_H):
            self.return_home()
            event.accept()
        elif event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 24.0 if event.modifiers() & Qt.ShiftModifier else 64.0
            dx = -step if event.key() == Qt.Key_Left else step if event.key() == Qt.Key_Right else 0.0
            dy = -step if event.key() == Qt.Key_Up else step if event.key() == Qt.Key_Down else 0.0
            self.camera.pan_screen(dx, dy)
            self._refresh_hover_after_camera_motion()
            self.update()
            event.accept()
        elif event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.camera.zoom_at(
                1.22, self.width() / 2, self.height() / 2, self.width(), self.height()
            )
            self._refresh_hover_after_camera_motion()
            self.update()
            event.accept()
        elif event.key() in (Qt.Key_Minus, Qt.Key_Underscore):
            self.camera.zoom_at(
                1 / 1.22, self.width() / 2, self.height() / 2, self.width(), self.height()
            )
            self._refresh_hover_after_camera_motion()
            self.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.update()

    def _clear_toast(self) -> None:
        self._play_toast = ""
        self.update()

    def show_notice(self, message: str, timeout_ms: int = 4000) -> None:
        """Show brief collection or playback feedback inside the field."""
        self._play_toast = str(message or "")
        if timeout_ms > 0:
            self._toast_timer.start(int(timeout_ms))
        else:
            self._toast_timer.stop()
        self.update()


def main() -> int:
    import sys

    arguments = list(sys.argv)
    windowed = "--windowed" in arguments[1:]
    qt_arguments = [arguments[0], *(arg for arg in arguments[1:] if arg != "--windowed")]
    app = QApplication.instance() or QApplication(qt_arguments)
    app.setApplicationName("Chiasm Field Prototype")
    field = FieldCanvas()
    field.setWindowTitle("Chiasm — Field")
    if windowed:
        field.resize(1280, 820)
        field.show()
    else:
        field.showFullScreen()
    field.setFocus()
    return app.exec()
