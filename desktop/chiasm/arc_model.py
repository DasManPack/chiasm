"""Explainable, deterministic album-to-album routes for Chiasm Arc."""

from __future__ import annotations

from dataclasses import dataclass

from .field_model import Album

MAX_ARC_ALBUMS = 12


@dataclass(frozen=True, slots=True)
class ArcHop:
    """One suggested album and the explicit metadata link that supports it."""

    album_id: str
    reason: str


def _key(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _artist_key(album: Album) -> str:
    artist = _key(album.artist)
    if artist in {"", "unknown", "unknown artist", "various artists"}:
        return ""
    return artist


def _genre_map(album: Album) -> dict[str, str]:
    return {
        _key(genre): str(genre).strip()
        for genre in album.genres
        if _key(genre)
    }


def _next_hop(
    albums: tuple[Album, ...], current: Album, visited: set[str]
) -> ArcHop | None:
    current_artist = _artist_key(current)
    current_genres = _genre_map(current)
    candidates: list[tuple[tuple[object, ...], Album, bool, tuple[str, ...]]] = []

    for album in albums:
        if album.id in visited:
            continue
        same_artist = bool(current_artist and _artist_key(album) == current_artist)
        shared_genres = tuple(
            sorted(
                (current_genres[key] for key in current_genres.keys() & _genre_map(album).keys()),
                key=str.casefold,
            )
        )
        if not same_artist and not shared_genres:
            continue
        order = (
            0 if same_artist else 1,
            -len(shared_genres),
            _key(album.artist),
            _key(album.title),
            album.id,
        )
        candidates.append((order, album, same_artist, shared_genres))

    if not candidates:
        remaining = [album for album in albums if album.id not in visited]
        if not remaining:
            return None
        chosen = min(
            remaining,
            key=lambda album: (
                _key(album.artist),
                _key(album.title),
                album.id,
            ),
        )
        return ArcHop(chosen.id, "next album in collection (alphabetical fallback)")
    _order, chosen, same_artist, shared_genres = min(candidates, key=lambda item: item[0])
    if same_artist and shared_genres:
        reason = f"same artist; shares {', '.join(shared_genres)}"
    elif same_artist:
        reason = f"same artist: {chosen.artist}"
    else:
        reason = f"shares genre: {', '.join(shared_genres)}"
    return ArcHop(chosen.id, reason)


def build_arc_route(
    albums: tuple[Album, ...],
    start_album_id: str,
    *,
    max_hops: int = MAX_ARC_ALBUMS - 1,
    exclude_ids: tuple[str, ...] = (),
) -> tuple[ArcHop, ...]:
    """Build a repeat-free route using only explicit artist and genre labels.

    Album coordinates are deliberately ignored: spatial proximity does not
    provide evidence for a listening recommendation.
    """
    collection = tuple(albums)
    by_id = {album.id: album for album in collection}
    current = by_id.get(str(start_album_id))
    if current is None:
        return ()

    visited = {current.id, *(str(album_id) for album_id in exclude_ids)}
    route: list[ArcHop] = []
    hop_limit = min(MAX_ARC_ALBUMS - 1, max(0, int(max_hops)))
    for _ in range(hop_limit):
        hop = _next_hop(collection, current, visited)
        if hop is None:
            break
        route.append(hop)
        visited.add(hop.album_id)
        current = by_id[hop.album_id]
    return tuple(route)
