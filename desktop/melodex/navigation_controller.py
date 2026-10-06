from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

_NAV_PARENT = {
    "home": "home",
    "for_you": "home",
    "now_playing": "home",
    "library": "library",
    "moments": "library",
    "explore": "explore",
    "discover": "explore",
    "album_wall": "explore",
    "chiasm": "explore",
    "music_map": "explore",
    "ask": "explore",
    "journeys": "journeys",
    "playlists": "playlists",
    "sources": "sources",
}

_STALE_PAGE_SCOPES = {
    "album_wall": ("page:album-wall-model",),
    "chiasm": ("page:chiasm-field",),
    "music_map": ("page:music-map-model",),
    "now_playing": (
        "now-playing-visual-analysis",
        "now-playing-visual-context",
    ),
}


def navigation_parent(page: str) -> str:
    return _NAV_PARENT.get(str(page or ""), "")


class NavigationController:
    """Own page transitions, lazy-page lifecycle and stale navigation work."""

    def __init__(
        self,
        host: Any,
        *,
        refresh_delay_ms: int = 16,
        settle_duration_ms: int = 120,
        schedule: Callable[[int, Callable[[], None]], None],
    ) -> None:
        self.host = host
        self.refresh_delay_ms = max(0, int(refresh_delay_ms))
        self.settle_duration_ms = max(0, int(settle_duration_ms))
        self._schedule = schedule
        self.generation = 0
        self.lazy_builders: dict[str, Callable[[], None]] = {}
        self.built_lazy_pages: set[str] = set()
        self.lazy_page_build_metrics: dict[str, float] = {}

    def set_lazy_builders(
        self,
        builders: dict[str, Callable[[], None]],
    ) -> None:
        self.lazy_builders = dict(builders)

    def ensure_lazy_page_built(self, name: str) -> bool:
        builder = self.lazy_builders.get(name)
        if builder is None or name in self.built_lazy_pages:
            return False
        started = time.perf_counter()
        builder()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.built_lazy_pages.add(name)
        self.lazy_page_build_metrics[name] = round(elapsed_ms, 3)
        self.host._startup_mark(f"lazy_page_ready:{name}")
        return True

    def _is_current(self, name: str, generation: int) -> bool:
        return not (
            self.host._closing
            or generation != self.generation
            or name != self.host.current_page
        )

    def build_lazy_page_if_current(self, name: str, generation: int) -> None:
        if not self._is_current(name, generation):
            return
        self.ensure_lazy_page_built(name)
        self.host.pages[name].update()
        self._schedule(
            0,
            lambda page=name, token=generation: self.populate_if_current(
                page,
                token,
            ),
        )

    def open_page(self, name: str) -> bool:
        if name not in self.host.pages:
            return False

        previous_page = self.host.current_page
        if previous_page != name:
            for scope in _STALE_PAGE_SCOPES.get(previous_page, ()):
                self.host._invalidate_async(scope)

        interaction = (
            self.host.responsiveness.begin_interaction(f"navigate:{name}")
            if hasattr(self.host, "responsiveness")
            else None
        )

        self.generation += 1
        generation = self.generation
        self.host.current_page = name
        self.host.stack.setCurrentWidget(self.host.pages[name])
        self.update_nav_state(name)
        self.host.pages[name].update()
        self.host.motion.settle(
            self.host.page_titles.get(name),
            duration_ms=self.settle_duration_ms,
            start_opacity=0.88,
        )

        if interaction is not None:
            self.host.responsiveness.end_interaction(interaction)

        if name in self.lazy_builders and name not in self.built_lazy_pages:
            self._schedule(
                self.refresh_delay_ms,
                lambda page=name, token=generation: self.build_lazy_page_if_current(
                    page,
                    token,
                ),
            )
            return True

        self._schedule(
            self.refresh_delay_ms,
            lambda page=name, token=generation: self.populate_if_current(
                page,
                token,
            ),
        )
        return True

    def populate_if_current(self, name: str, generation: int) -> None:
        if not self._is_current(name, generation):
            return

        host = self.host
        if name == "home":
            host._show_home()
        elif name == "library":
            host._refresh_library()
            host._refresh_plugin_presence()
        elif name == "explore":
            host._refresh_explore_visibility()
        elif name == "album_wall":
            host._refresh_album_wall()
        elif name == "chiasm":
            host.chiasm_feature.refresh()
        elif name == "music_map":
            host.journey_workspace.refresh_music_map()
        elif name == "sources":
            host.sources_feature.refresh()
            self._schedule(0, host.sources_feature.refresh_config_statuses_async)
        elif name == "moments":
            host._refresh_moments()
        elif name == "journeys":
            host.journey_workspace.refresh_journeys()
        elif name == "playlists":
            host._refresh_playlists()
        elif name == "for_you":
            host._refresh_taste()
            host._refresh_plugin_presence()
        elif name == "discover":
            host._refresh_source_combo()
            host._refresh_plugin_presence()
        elif name == "now_playing":
            host._refresh_plugin_presence()

    def update_nav_state(self, page: str) -> None:
        parent = navigation_parent(page)
        for key, button in getattr(self.host, "nav_buttons", {}).items():
            active = key == parent
            if bool(button.property("active")) == active:
                continue
            button.setProperty("active", active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
