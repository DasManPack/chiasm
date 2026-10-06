from __future__ import annotations

from melodex.navigation_controller import NavigationController, navigation_parent


class FakePage:
    def __init__(self):
        self.updated = 0

    def update(self):
        self.updated += 1


class FakeStack:
    def __init__(self):
        self.current = None

    def setCurrentWidget(self, widget):
        self.current = widget


class FakeMotion:
    def __init__(self):
        self.calls = []

    def settle(self, target, **kwargs):
        self.calls.append((target, kwargs))


class FakeChiasmFeature:
    def __init__(self):
        self.refreshes = 0

    def refresh(self):
        self.refreshes += 1


class FakeHost:
    def __init__(self):
        self._closing = False
        self.current_page = "home"
        self.pages = {
            "home": FakePage(),
            "library": FakePage(),
            "album_wall": FakePage(),
            "chiasm": FakePage(),
        }
        self.stack = FakeStack()
        self.motion = FakeMotion()
        self.chiasm_feature = FakeChiasmFeature()
        self.page_titles = {}
        self.nav_buttons = {}
        self.invalidated = []
        self.started = []
        self.library_refreshes = 0
        self.plugin_refreshes = 0

    def _invalidate_async(self, scope):
        self.invalidated.append(scope)

    def _startup_mark(self, phase):
        self.started.append(phase)

    def _refresh_library(self):
        self.library_refreshes += 1

    def _refresh_plugin_presence(self):
        self.plugin_refreshes += 1

    def _show_home(self):
        pass

    def _refresh_explore_visibility(self):
        pass

    def _refresh_album_wall(self):
        pass

    def _refresh_music_map(self):
        pass

    def _refresh_sources(self):
        pass

    def _refresh_source_config_statuses_async(self):
        pass

    def _refresh_moments(self):
        pass

    def _refresh_journeys(self):
        pass

    def _refresh_playlists(self):
        pass

    def _refresh_taste(self):
        pass

    def _refresh_source_combo(self):
        pass


def test_navigation_parent_groups_secondary_pages():
    assert navigation_parent("now_playing") == "home"
    assert navigation_parent("moments") == "library"
    assert navigation_parent("album_wall") == "explore"
    assert navigation_parent("chiasm") == "explore"
    assert navigation_parent("sources") == "sources"
    assert navigation_parent("unknown") == ""


def test_lazy_page_build_and_population_are_owned_by_controller():
    callbacks = []
    host = FakeHost()
    controller = NavigationController(
        host,
        refresh_delay_ms=16,
        schedule=lambda _delay, callback: callbacks.append(callback),
    )
    built = []
    controller.set_lazy_builders({"library": lambda: built.append("library")})

    assert controller.open_page("library") is True
    assert host.current_page == "library"
    assert host.stack.current is host.pages["library"]
    assert built == []
    assert len(callbacks) == 1

    callbacks.pop(0)()
    assert built == ["library"]
    assert "library" in controller.built_lazy_pages
    assert "library" in controller.lazy_page_build_metrics
    assert host.started == ["lazy_page_ready:library"]
    assert len(callbacks) == 1

    callbacks.pop(0)()
    assert host.library_refreshes == 1
    assert host.plugin_refreshes == 1


def test_stale_navigation_callback_is_dropped():
    callbacks = []
    host = FakeHost()
    host.current_page = "album_wall"
    controller = NavigationController(
        host,
        schedule=lambda _delay, callback: callbacks.append(callback),
    )
    controller.set_lazy_builders({"library": lambda: None})

    controller.open_page("library")
    stale = callbacks.pop(0)
    controller.open_page("home")

    stale()

    assert host.invalidated == ["page:album-wall-model"]
    assert "library" not in controller.built_lazy_pages


def test_chiasm_page_refreshes_through_navigation_controller():
    callbacks = []
    host = FakeHost()
    controller = NavigationController(
        host,
        schedule=lambda _delay, callback: callbacks.append(callback),
    )

    assert controller.open_page("chiasm") is True
    callbacks.pop(0)()

    assert host.current_page == "chiasm"
    assert host.chiasm_feature.refreshes == 1
