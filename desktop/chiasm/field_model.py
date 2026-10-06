"""Deterministic spatial data and camera math for the Chiasm C0 prototype."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from math import cos, exp, hypot, pi, sin, sqrt

HOME_ZOOM = 0.88


@dataclass(frozen=True, slots=True)
class Album:
    id: str
    title: str
    artist: str
    region: str
    x: float
    y: float
    motif: int
    genres: tuple[str, ...] = ()
    analysed_tracks: int = 0
    sound_sampled_tracks: int = 0
    sound_links: tuple["SoundLink", ...] = ()


@dataclass(frozen=True, slots=True)
class DepthCue:
    """Perceptual emphasis around attention without changing field geography."""

    scale: float
    opacity: float
    focus_strength: float


@dataclass(frozen=True, slots=True)
class AlbumLensContext:
    """Explicit shared-place context; spatial proximity alone implies nothing."""

    albums_in_region: int
    other_titles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SoundLink:
    """Album-level evidence aggregated from analyzed track-profile links."""

    album_id: str
    similarity: float
    track_links: int = 1


class SemanticLevel(str, Enum):
    OVERVIEW = "overview"
    ALBUMS = "albums"
    DETAIL = "detail"


@dataclass(slots=True)
class FieldCamera:
    """A stable 2D camera whose world coordinates do not change while exploring."""

    center_x: float = 0.0
    center_y: float = 0.0
    zoom: float = HOME_ZOOM
    min_zoom: float = 0.36
    max_zoom: float = 2.8

    @property
    def is_at_home(self) -> bool:
        return (
            hypot(self.center_x, self.center_y) <= 0.5
            and abs(self.zoom - HOME_ZOOM) <= 0.005
        )

    def world_to_screen(self, x: float, y: float, width: float, height: float) -> tuple[float, float]:
        return (
            width / 2 + (x - self.center_x) * self.zoom,
            height / 2 + (y - self.center_y) * self.zoom,
        )

    def screen_to_world(self, x: float, y: float, width: float, height: float) -> tuple[float, float]:
        return (
            self.center_x + (x - width / 2) / self.zoom,
            self.center_y + (y - height / 2) / self.zoom,
        )

    def pan_screen(self, dx: float, dy: float) -> None:
        self.center_x -= dx / self.zoom
        self.center_y -= dy / self.zoom

    def zoom_at(
        self,
        factor: float,
        screen_x: float,
        screen_y: float,
        width: float,
        height: float,
    ) -> bool:
        """Zoom around a screen point, keeping its world point under the pointer."""
        old_zoom = self.zoom
        next_zoom = min(self.max_zoom, max(self.min_zoom, old_zoom * factor))
        if abs(next_zoom - old_zoom) < 1e-9:
            return False

        anchor_x, anchor_y = self.screen_to_world(screen_x, screen_y, width, height)
        self.zoom = next_zoom
        self.center_x = anchor_x - (screen_x - width / 2) / next_zoom
        self.center_y = anchor_y - (screen_y - height / 2) / next_zoom
        return True

    def home(self) -> None:
        self.center_x = 0.0
        self.center_y = 0.0
        self.zoom = HOME_ZOOM


def album_depth_cue(album: Album, focus: Album | None, hovered_id: str | None) -> DepthCue:
    """Resolve focus, nearby emphasis, and recession from one shared distance curve."""
    if focus is None:
        return DepthCue(1.12 if album.id == hovered_id else 1.0, 1.0, 0.0)

    distance = hypot(album.x - focus.x, album.y - focus.y)
    focus_strength = exp(-distance / 420.0)
    if album.id == focus.id:
        return DepthCue(1.24, 1.0, 1.0)

    scale = 1.0 + 0.22 * focus_strength
    opacity = 0.62 + 0.38 * exp(-distance / 900.0)
    return DepthCue(scale, opacity, focus_strength)


def semantic_zoom_level(zoom: float) -> SemanticLevel:
    """Name the field information layer shown at the current zoom."""
    if zoom < 0.55:
        return SemanticLevel.OVERVIEW
    if zoom < 1.2:
        return SemanticLevel.ALBUMS
    return SemanticLevel.DETAIL


def album_hit_radius(
    album: Album,
    focus: Album | None,
    hovered_id: str | None,
    zoom: float,
    min_screen_radius: float = 22.0,
) -> float:
    """Return the rendered hit radius in world units with a 44px target floor."""
    if zoom <= 0:
        raise ValueError("zoom must be positive")
    cue = album_depth_cue(album, focus, hovered_id)
    visual_radius = 49.0 * cue.scale + 3.0
    return max(visual_radius, min_screen_radius / zoom)


def album_lens_context(
    albums: tuple[Album, ...], album: Album, max_other_titles: int = 3
) -> AlbumLensContext:
    """Return a few titles sharing the album's named region, without inferring taste."""
    in_region = tuple(
        candidate
        for candidate in albums
        if album.region and candidate.region == album.region
    )
    other_titles = tuple(
        candidate.title for candidate in in_region if candidate.id != album.id
    )[:max(0, max_other_titles)]
    return AlbumLensContext(len(in_region), other_titles)


def albums_from_collection_rows(
    rows: list[dict],
    positions: dict[str, tuple[float, float]],
    sound_links: dict[str, tuple[SoundLink, ...]] | None = None,
    sound_sampled_tracks: dict[str, int] | None = None,
) -> tuple[Album, ...]:
    """Adapt Album Wall rows into field records without importing Melodex UI code."""
    albums: list[Album] = []
    for row in rows:
        album_id = str(row.get("key") or "").strip()
        if not album_id:
            continue
        artist = str(row.get("artist") or "Unknown artist").strip() or "Unknown artist"
        title = str(row.get("title") or "Unknown album").strip() or "Unknown album"
        region = str(row.get("region") or "").strip()
        point = positions.get(album_id)
        if point is None:
            point = (
                float(row.get("fallback_x") or 0.0) * 900.0,
                float(row.get("fallback_y") or 0.0) * 700.0,
            )
        motif = hashlib.sha256(album_id.encode("utf-8", errors="ignore")).digest()[0] % 8
        raw_genres = row.get("genres") or ()
        if isinstance(raw_genres, str):
            raw_genres = raw_genres.replace("/", ";").split(";")
        genres = tuple(
            dict.fromkeys(
                str(genre).strip()
                for genre in raw_genres
                if str(genre).strip()
            )
        )
        albums.append(
            Album(
                id=album_id,
                title=title,
                artist=artist,
                region=region,
                x=float(point[0]),
                y=float(point[1]),
                motif=motif,
                genres=genres,
                analysed_tracks=max(0, int(row.get("analysed_tracks") or 0)),
                sound_sampled_tracks=max(
                    0, int((sound_sampled_tracks or {}).get(album_id, 0))
                ),
                sound_links=tuple((sound_links or {}).get(album_id, ())),
            )
        )
    return tuple(albums)


_REGIONS = (
    ("COASTAL LIGHT", "Mira Sol", "Low Water", "Salt Bloom", "Tidepool Radio", "The Blue Hour", "Glass Shore", "Soft Current", "Sea Change", "Open Window", "Far Lantern", "Shallow Blue"),
    ("SLOW ORBIT", "Ivo North", "Paper Satellites", "Small Moons", "A Quiet Signal", "Orbiting Home", "Sleeper Train", "The Long Return", "Rooms in Space", "Silver Weight", "Drift Study", "Night Coordinates"),
    ("EMBER ROOM", "June Vale", "Warm Static", "Copper Weather", "After the Fire", "Cinder Garden", "Borrowed Heat", "Red Thread", "Last October", "Kindling Song", "Smoke Letters", "Small Flame"),
    ("AFTERIMAGE", "Noah Fern", "Memory Foam", "Soft Focus", "Almost Here", "The Other Side", "Green Glass", "Sunday Negative", "Field Notes", "Lighter Than Air", "A Familiar Shape", "When We Were Near"),
    ("OPEN SKY", "Ada West", "Cloud Index", "Blue Arithmetic", "North of Morning", "Nothing Fixed", "Bird Atlas", "Weather Radio", "High Country", "Wide Awake", "Clear Distance", "A Map of Wind"),
)


def make_demo_collection() -> tuple[Album, ...]:
    """Return 50 fictional records arranged in five stable, explorable regions."""
    albums: list[Album] = []
    center_radius = 490.0
    golden_angle = pi * (3.0 - sqrt(5.0))

    for region_index, row in enumerate(_REGIONS):
        region, artist, *titles = row
        region_angle = -pi / 2 + region_index * (2 * pi / len(_REGIONS))
        center_x = cos(region_angle) * center_radius
        center_y = sin(region_angle) * center_radius

        for slot, title in enumerate(titles):
            angle = slot * golden_angle + region_index * 0.27
            radius = 36 + sqrt(slot + 1) * 37
            albums.append(
                Album(
                    id=f"album-{region_index + 1:02d}-{slot + 1:02d}",
                    title=title,
                    artist=artist,
                    region=region,
                    x=center_x + cos(angle) * radius,
                    y=center_y + sin(angle) * radius * 0.82,
                    motif=(region_index * 3 + slot) % 8,
                )
            )

    return tuple(albums)


def nearest_album(
    albums: tuple[Album, ...], x: float, y: float, radius: float
) -> Album | None:
    """Return the nearest album within a world-space hit radius."""
    closest: Album | None = None
    closest_distance = radius
    for album in albums:
        distance = hypot(album.x - x, album.y - y)
        if distance <= closest_distance:
            closest = album
            closest_distance = distance
    return closest


DEMO_COLLECTION = make_demo_collection()
