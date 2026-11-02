from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Track:
    id: str
    uri: str
    name: str
    artists: List[str]
    album_id: str
    album_name: str
    is_playable: bool
    disc_number: int = 1
    track_number: int = 1
    duration_ms: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Track:
        artists = [a.get("name", "") for a in data.get("artists", []) if a.get("name")]
        album = data.get("album", {})
        album_id = album.get("id", "")
        album_name = album.get("name", "")
        
        # Check playability: Spotify API provides is_playable directly or in restriction
        is_playable = data.get("is_playable", True)
        if "restrictions" in data:
            is_playable = False

        return cls(
            id=data.get("id", ""),
            uri=data.get("uri", f"spotify:track:{data.get('id', '')}"),
            name=data.get("name", "Unknown Track"),
            artists=artists,
            album_id=album_id,
            album_name=album_name,
            is_playable=is_playable,
            disc_number=data.get("disc_number", 1),
            track_number=data.get("track_number", 1),
            duration_ms=data.get("duration_ms", 0),
        )


@dataclass
class Album:
    id: str
    uri: str
    name: str
    artists: List[str]
    total_tracks: int
    track_ids: List[str] = field(default_factory=list)
    is_playable: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Album:
        artists = [a.get("name", "") for a in data.get("artists", []) if a.get("name")]
        tracks_obj = data.get("tracks", {})
        items = tracks_obj.get("items", []) if isinstance(tracks_obj, dict) else []
        track_ids = [t["id"] for t in items if isinstance(t, dict) and t.get("id")]
        
        is_playable = data.get("is_playable", True)
        if "restrictions" in data:
            is_playable = False

        return cls(
            id=data.get("id", ""),
            uri=data.get("uri", f"spotify:album:{data.get('id', '')}"),
            name=data.get("name", "Unknown Album"),
            artists=artists,
            total_tracks=data.get("total_tracks", len(track_ids)),
            track_ids=track_ids,
            is_playable=is_playable,
        )


@dataclass
class ActionLog:
    action: str  # RELINK_TRACK, RELINK_ALBUM, ROLLUP_ALBUM, FIX_PLAYLIST_TRACK
    item_type: str  # track, album, playlist
    old_id: str
    new_id: Optional[str]
    name: str
    artist: str
    details: str
    applied: bool = False


@dataclass
class UnavailableItem:
    item_type: str  # track, album, playlist
    id: str
    uri: str
    name: str
    artist: str
    album_name: Optional[str] = None
    reason: str = "Not available in market or deleted"
