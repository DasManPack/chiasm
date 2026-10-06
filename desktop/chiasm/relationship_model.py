"""Explainable, non-spatial relationships for the Chiasm Horizon."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math

from .field_model import Album, SoundLink

MAX_HORIZON_TRACKS = 700


@dataclass(frozen=True, slots=True)
class HorizonLink:
    """A named relation to another album, with its collection evidence."""

    album_id: str
    kinds: tuple[str, ...]
    reasons: tuple[str, ...]
    sound_similarity: float = 0.0
    sound_track_links: int = 0

    @property
    def summary(self) -> str:
        return " · ".join(self.reasons)


@dataclass(frozen=True, slots=True)
class AlbumHorizon:
    """Known links plus counts that distinguish missing evidence from a match."""

    links: tuple[HorizonLink, ...]
    linked_count: int
    unresolved_count: int
    unsampled_album_count: int


def _key(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _artist_key(album: Album) -> str:
    value = _key(album.artist)
    if value in {"", "unknown", "unknown artist", "various artists"}:
        return ""
    return value


def _genres(album: Album) -> dict[str, str]:
    return {
        _key(value): str(value).strip()
        for value in album.genres
        if _key(value)
    }


def album_horizon(
    albums: tuple[Album, ...], album: Album, *, max_links: int = 5
) -> AlbumHorizon:
    """Resolve nearby or distant links from names and analyzed audio evidence.

    Album coordinates are intentionally ignored. Lack of a link means that
    the collection has not resolved a relationship, not that two albums are
    unrelated.
    """
    all_albums = tuple(albums)
    sound_by_id = {link.album_id: link for link in album.sound_links}
    candidates: list[tuple[tuple[object, ...], HorizonLink]] = []
    unsampled = 0

    current_artist = _artist_key(album)
    current_genres = _genres(album)
    for candidate in all_albums:
        if candidate.id == album.id:
            continue
        if candidate.sound_sampled_tracks <= 0:
            unsampled += 1

        same_artist = bool(
            current_artist and _artist_key(candidate) == current_artist
        )
        shared_genres = tuple(
            sorted(
                (current_genres[key] for key in current_genres.keys() & _genres(candidate).keys()),
                key=str.casefold,
            )
        )
        sound_link = sound_by_id.get(candidate.id)
        kinds: list[str] = []
        reasons: list[str] = []
        if same_artist:
            kinds.append("artist")
            reasons.append("same artist")
        if shared_genres:
            kinds.append("genre")
            reasons.append(f"shared genre: {', '.join(shared_genres[:2])}")
        if sound_link is not None:
            kinds.append("sound")
            reasons.append(
                f"audio map {sound_link.similarity:.2f}"
                + (
                    f" · {sound_link.track_links} track edges"
                    if sound_link.track_links > 0
                    else ""
                )
            )
        if not reasons:
            continue

        link = HorizonLink(
            album_id=candidate.id,
            kinds=tuple(kinds),
            reasons=tuple(reasons),
            sound_similarity=(sound_link.similarity if sound_link else 0.0),
            sound_track_links=(sound_link.track_links if sound_link else 0),
        )
        sort_key = (
            0 if same_artist else 1,
            0 if shared_genres else 1,
            0 if sound_link is not None else 1,
            -len(shared_genres),
            -link.sound_similarity,
            _key(candidate.artist),
            _key(candidate.title),
            candidate.id,
        )
        candidates.append((sort_key, link))

    candidates.sort(key=lambda item: item[0])
    all_links = tuple(link for _key_value, link in candidates)
    visible_limit = max(0, int(max_links))
    return AlbumHorizon(
        links=all_links[:visible_limit],
        linked_count=len(all_links),
        unresolved_count=max(0, len(all_albums) - 1 - len(all_links)),
        unsampled_album_count=unsampled,
    )


def album_sound_links_from_track_edges(
    edges: list[dict], track_ref_to_album: dict[str, str]
) -> dict[str, tuple[SoundLink, ...]]:
    """Aggregate Music Map track edges into symmetric album-level evidence."""
    pair_scores: dict[tuple[str, str], list[float]] = defaultdict(list)
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        left = track_ref_to_album.get(str(edge.get("a") or ""))
        right = track_ref_to_album.get(str(edge.get("b") or ""))
        if not left or not right or left == right:
            continue
        try:
            similarity = float(edge.get("similarity"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(similarity) or not 0.0 <= similarity <= 1.0:
            continue
        pair_scores[tuple(sorted((left, right)))].append(similarity)

    links: dict[str, list[SoundLink]] = defaultdict(list)
    for (left, right), scores in pair_scores.items():
        link = SoundLink(
            album_id=right,
            similarity=max(scores),
            track_links=len(scores),
        )
        reverse = SoundLink(
            album_id=left,
            similarity=max(scores),
            track_links=len(scores),
        )
        links[left].append(link)
        links[right].append(reverse)

    return {
        album_id: tuple(
            sorted(
                values,
                key=lambda link: (-link.similarity, link.album_id),
            )
        )
        for album_id, values in links.items()
    }


__all__ = [
    "AlbumHorizon",
    "HorizonLink",
    "MAX_HORIZON_TRACKS",
    "album_horizon",
    "album_sound_links_from_track_edges",
]
