"""Narrow adapters from Melodex's local services into the Chiasm field."""

from __future__ import annotations

from typing import Any, Callable


MAX_COLLECTION_TRACKS = 5000
MAX_COLLECTION_ALBUMS = 1200
MAX_ARTWORK_BATCH = 24


def _empty_payload(status: str) -> dict[str, Any]:
    return {
        "albums": (),
        "tracks_by_album": {},
        "track_to_album": {},
        "status": status,
    }


class MelodexCollectionAdapter:
    """Build field data from the existing local catalog, models, and art cache.

    Factories keep Melodex's heavier services lazy until Chiasm needs them. This
    adapter deliberately exposes only local catalog rows and cached/local art;
    it never invokes provider playback or online metadata lookup.
    """

    def __init__(
        self,
        providers: Any,
        local_intelligence: Callable[[], Any],
        metadata: Callable[[], Any],
    ) -> None:
        self.providers = providers
        self._local_intelligence = local_intelligence
        self._metadata = metadata

    def build_collection(self) -> dict[str, Any]:
        from melodex.album_wall_model import build_album_wall, layout_album_positions
        from melodex.music_map_model import build_music_map
        from chiasm.field_model import albums_from_collection_rows
        from chiasm.relationship_model import (
            MAX_HORIZON_TRACKS,
            album_sound_links_from_track_edges,
        )

        try:
            catalog = list(self.providers.local_catalog() or [])
        except Exception:
            return _empty_payload("provider-unavailable")
        catalog = [track for track in catalog if isinstance(track, dict)]
        if not catalog:
            return _empty_payload("empty")

        intelligence_available = True
        try:
            profiles, _seed_refs, ref_map, _analysed = self._local_intelligence().build_snapshot(
                catalog,
                [],
                max_tracks=MAX_COLLECTION_TRACKS,
                analyse_seeds=False,
            )
        except Exception:
            # Metadata still gives a stable collection layout when Flow or its
            # intelligence service is unavailable.
            profiles, ref_map = [], {}
            intelligence_available = False

        projection = build_music_map(
            profiles,
            max_nodes=MAX_COLLECTION_TRACKS,
            neighbours=0,
        )
        projected_refs = {
            str(node.get("ref") or "")
            for node in list(projection.get("nodes") or [])
            if isinstance(node, dict) and str(node.get("ref") or "")
        }
        projected_ref_map = {
            ref: dict(track)
            for ref, track in ref_map.items()
            if ref in projected_refs
        }

        # Nearest-neighbor analysis is the expensive part. Keep its existing
        # bounded sample separate from the larger, position-only projection.
        sound_projection = build_music_map(
            profiles,
            max_nodes=MAX_HORIZON_TRACKS,
            neighbours=2,
        )
        sound_refs = {
            str(node.get("ref") or "")
            for node in list(sound_projection.get("nodes") or [])
            if isinstance(node, dict) and str(node.get("ref") or "")
        }
        sound_ref_map = {
            ref: dict(track)
            for ref, track in ref_map.items()
            if ref in sound_refs
        }
        wall_model = build_album_wall(
            catalog,
            projection,
            projected_ref_map,
            max_albums=MAX_COLLECTION_ALBUMS,
        )
        rows = [
            dict(row)
            for row in list(wall_model.get("albums") or [])
            if isinstance(row, dict)
        ]
        positions = layout_album_positions(wall_model, "sound")

        tracks_by_album: dict[str, list[dict[str, Any]]] = {}
        track_to_album: dict[str, str] = {}
        identity_to_album: dict[tuple[str, str], str] = {}
        for row in rows:
            album_id = str(row.get("key") or "").strip()
            if not album_id:
                continue
            tracks = [
                dict(track)
                for track in list(row.get("tracks") or [])
                if isinstance(track, dict)
            ]
            tracks_by_album[album_id] = tracks
            for track in tracks:
                local_path = str(track.get("local_path") or "").strip()
                if local_path:
                    track_to_album[local_path] = album_id
                for identity_key in ("local_path", "rel", "track_id"):
                    identity_value = str(track.get(identity_key) or "").strip()
                    if identity_value:
                        identity_to_album[(identity_key, identity_value)] = album_id

        track_ref_to_album: dict[str, str] = {}
        for ref, track in sound_ref_map.items():
            for identity_key in ("local_path", "rel", "track_id"):
                identity_value = str(track.get(identity_key) or "").strip()
                album_id = identity_to_album.get((identity_key, identity_value))
                if identity_value and album_id:
                    track_ref_to_album[ref] = album_id
                    break
        sound_links = album_sound_links_from_track_edges(
            list(sound_projection.get("edges") or []),
            track_ref_to_album,
        )
        sound_sampled_tracks: dict[str, int] = {}
        for album_id in track_ref_to_album.values():
            sound_sampled_tracks[album_id] = sound_sampled_tracks.get(album_id, 0) + 1

        albums = albums_from_collection_rows(
            rows,
            positions,
            sound_links,
            sound_sampled_tracks,
        )
        return {
            "albums": albums,
            "tracks_by_album": tracks_by_album,
            "track_to_album": track_to_album,
            "status": (
                "ready"
                if intelligence_available and int(projection.get("analysed") or 0) > 0
                else "metadata-only"
            ),
        }

    def local_artwork_paths(
        self,
        tracks_by_album: dict[str, list[dict[str, Any]]],
        album_ids: list[str] | tuple[str, ...],
        *,
        max_items: int = MAX_ARTWORK_BATCH,
    ) -> dict[str, str]:
        """Resolve a small batch using local files and the existing artwork cache."""
        batch_limit = max(0, min(MAX_ARTWORK_BATCH, int(max_items)))
        selected = tuple(dict.fromkeys(str(album_id) for album_id in album_ids if album_id))
        selected = selected[:batch_limit]
        if not selected:
            return {}

        try:
            metadata = self._metadata()
        except Exception:
            return {album_id: "" for album_id in selected}

        result: dict[str, str] = {}
        for album_id in selected:
            tracks = tracks_by_album.get(album_id) or []
            representative = next(
                (dict(track) for track in tracks if isinstance(track, dict)),
                None,
            )
            if representative is None:
                result[album_id] = ""
                continue
            try:
                info = metadata.local_artwork(representative)
                result[album_id] = str((info or {}).get("path") or "")
            except Exception:
                result[album_id] = ""
        return result
