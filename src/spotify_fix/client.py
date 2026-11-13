from __future__ import annotations

import difflib
import logging
import re
import time
import requests
from typing import List, Dict, Any, Optional, Generator
from spotify_fix.auth import AuthManager
from spotify_fix.models import Track, Album

logger = logging.getLogger(__name__)

BASE_URL = "https://api.spotify.com/v1"


def normalize_title(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return s.strip()


def has_unwanted_variant_keywords(orig_name: str, candidate_name: str) -> bool:
    orig_lower = orig_name.lower()
    cand_lower = candidate_name.lower()
    variant_keywords = ["live", "remix", "rework", "acoustic", "cover", "karaoke", "instrumental", "tribute"]
    for kw in variant_keywords:
        if kw in cand_lower and kw not in orig_lower:
            return True
    return False


def calculate_match_score(
    orig_name: str,
    orig_artist: str,
    candidate: Track | Album,
    orig_duration_ms: int = 0,
    orig_id: Optional[str] = None,
) -> float:
    # Reject candidate if same ID as target
    if orig_id and candidate.id == orig_id:
        return 0.0

    # Reject if candidate has unwanted variants ("Live", "Remix", etc.)
    if has_unwanted_variant_keywords(orig_name, candidate.name):
        return 0.0

    # Title similarity
    n_orig = normalize_title(orig_name)
    n_cand = normalize_title(candidate.name)
    if not n_orig or not n_cand:
        title_score = difflib.SequenceMatcher(None, orig_name.lower(), candidate.name.lower()).ratio()
    else:
        title_score = difflib.SequenceMatcher(None, n_orig, n_cand).ratio()

    if title_score < 0.45:
        return 0.0

    # Artist match check
    orig_artists = [a.lower().strip() for a in orig_artist.split(",") if a.strip()]
    cand_artists = [a.lower().strip() for a in candidate.artists]
    
    artist_match = False
    for oa in orig_artists:
        for ca in cand_artists:
            if oa in ca or ca in oa or difflib.SequenceMatcher(None, oa, ca).ratio() > 0.6:
                artist_match = True
                break
        if artist_match:
            break

    if not artist_match:
        return 0.0

    # Duration tolerance for tracks
    if isinstance(candidate, Track) and orig_duration_ms > 0 and candidate.duration_ms > 0:
        duration_diff_sec = abs(candidate.duration_ms - orig_duration_ms) / 1000.0
        if duration_diff_sec > 25.0:
            return 0.0

    return title_score


class SpotifyClient:
    """Spotify Web API Client with rate limiting, auth retry, and paginated getters."""

    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        self.session = requests.Session()

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        max_retries: int = 5,
    ) -> Any:
        """Execute HTTP request against Spotify API with retry and token refresh logic."""
        url = endpoint if endpoint.startswith("http") else f"{BASE_URL}{endpoint}"
        is_write = method.upper() in {"PUT", "POST", "DELETE"}

        for attempt in range(max_retries):
            token = self.auth_manager.get_access_token(is_write=is_write)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) spotify-fix/1.0",
            }

            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    timeout=20,
                )

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    logger.warning(
                        f"Rate limit hit (429). Waiting {retry_after}s before retry (attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(retry_after)
                    continue

                if resp.status_code == 401:
                    logger.warning("Access token expired/unauthorized (401). Refreshing token...")
                    self.auth_manager.get_access_token(force_refresh=True, is_write=is_write)
                    continue

                resp.raise_for_status()
                time.sleep(0.25)  # 0.25s fetch delay to respect Spotify rate limits
                if resp.status_code == 204 or not resp.content:
                    return None
                return resp.json()

            except requests.RequestException as e:
                logger.error(f"HTTP request error ({method} {url}): {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError(f"Request failed after {max_retries} attempts: {method} {url}")

    def get_paginated(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None, limit: int = 50
    ) -> Generator[Dict[str, Any], None, None]:
        """Yield items from paginated Spotify API responses."""
        if params is None:
            params = {}
        params["limit"] = limit
        params["offset"] = 0

        url = f"{BASE_URL}{endpoint}"
        page_num = 1

        while url:
            data = self.request("GET", url, params=params if url == f"{BASE_URL}{endpoint}" else None)
            if not data:
                break

            # Handle response structure: object containing 'items' or wrapper object
            items_container = data
            if "items" not in items_container:
                for k in ("tracks", "albums", "playlists"):
                    if k in data and isinstance(data[k], dict) and "items" in data[k]:
                        items_container = data[k]
                        break

            items = items_container.get("items", [])
            total = items_container.get("total")
            if page_num % 10 == 0 or not items_container.get("next"):
                logger.info(f"Paginating {endpoint}: page {page_num} (items fetched: {page_num * limit}/{total or '?'})")

            for item in items:
                yield item

            url = items_container.get("next")
            params = None
            page_num += 1

    # --- Liked Library Getters ---

    def get_all_liked_tracks(self) -> List[Track]:
        """Fetch all user liked tracks with market playability check."""
        logger.info("Fetching all user liked tracks...")
        tracks = []
        for item in self.get_paginated("/me/tracks", params={"market": "from_token"}):
            if "track" in item and item["track"]:
                tracks.append(Track.from_dict(item["track"]))
        logger.info(f"Retrieved {len(tracks)} liked tracks.")
        return tracks

    def get_all_liked_albums(self) -> List[Album]:
        """Fetch all user liked albums with market playability check."""
        logger.info("Fetching all user liked albums...")
        albums = []
        for item in self.get_paginated("/me/albums", params={"market": "from_token"}):
            if "album" in item and item["album"]:
                albums.append(Album.from_dict(item["album"]))
        logger.info(f"Retrieved {len(albums)} liked albums.")
        return albums

    def get_all_user_playlists(self) -> List[Dict[str, Any]]:
        """Fetch all playlists owned or followed by user."""
        logger.info("Fetching all user playlists...")
        playlists = list(self.get_paginated("/me/playlists"))
        logger.info(f"Retrieved {len(playlists)} playlists.")
        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Any]]:
        """Fetch all track items from a playlist with market playability check."""
        return list(self.get_paginated(f"/playlists/{playlist_id}/tracks", params={"market": "from_token"}))

    def get_album_details(self, album_id: str) -> Optional[Album]:
        """Fetch full details and tracklist for an album."""
        data = self.request("GET", f"/albums/{album_id}", params={"market": "from_token"})
        if not data:
            return None
        
        album = Album.from_dict(data)
        # Handle paginated album tracks if total_tracks > items returned in single response
        if len(album.track_ids) < album.total_tracks:
            all_tracks = list(self.get_paginated(f"/albums/{album_id}/tracks", params={"market": "from_token"}))
            album.track_ids = [t["id"] for t in all_tracks if t.get("id")]

        return album

    # --- Library Mutation Methods ---

    def like_tracks(self, track_ids: List[str], dry_run: bool = False) -> None:
        """Save tracks to user's Liked Songs in chunks of 50."""
        if not track_ids:
            return
        if dry_run:
            logger.info(f"[DRY RUN] Would like tracks: {track_ids}")
            return

        for i in range(0, len(track_ids), 50):
            chunk = track_ids[i : i + 50]
            self.request("PUT", "/me/tracks", json_data={"ids": chunk})
            logger.info(f"Liked {len(chunk)} tracks.")

    def unlike_tracks(self, track_ids: List[str], dry_run: bool = False) -> None:
        """Remove tracks from user's Liked Songs in chunks of 50."""
        if not track_ids:
            return
        if dry_run:
            logger.info(f"[DRY RUN] Would unlike tracks: {track_ids}")
            return

        for i in range(0, len(track_ids), 50):
            chunk = track_ids[i : i + 50]
            self.request("DELETE", "/me/tracks", json_data={"ids": chunk})
            logger.info(f"Unliked {len(chunk)} tracks.")

    def like_albums(self, album_ids: List[str], dry_run: bool = False) -> None:
        """Save albums to user's Library in chunks of 50."""
        if not album_ids:
            return
        if dry_run:
            logger.info(f"[DRY RUN] Would like albums: {album_ids}")
            return

        for i in range(0, len(album_ids), 50):
            chunk = album_ids[i : i + 50]
            self.request("PUT", "/me/albums", json_data={"ids": chunk})
            logger.info(f"Liked {len(chunk)} albums.")

    def unlike_albums(self, album_ids: List[str], dry_run: bool = False) -> None:
        """Remove albums from user's Library in chunks of 50."""
        if not album_ids:
            return
        if dry_run:
            logger.info(f"[DRY RUN] Would unlike albums: {album_ids}")
            return

        for i in range(0, len(album_ids), 50):
            chunk = album_ids[i : i + 50]
            self.request("DELETE", "/me/albums", json_data={"ids": chunk})
            logger.info(f"Unliked {len(chunk)} albums.")

    def remove_playlist_tracks(
        self, playlist_id: str, track_uris: List[str], dry_run: bool = False
    ) -> None:
        """Remove tracks from a playlist by URIs."""
        if not track_uris:
            return
        if dry_run:
            logger.info(f"[DRY RUN] Would remove tracks from playlist {playlist_id}: {track_uris}")
            return

        for i in range(0, len(track_uris), 100):
            chunk = track_uris[i : i + 100]
            tracks_payload = [{"uri": u} for u in chunk]
            self.request("DELETE", f"/playlists/{playlist_id}/tracks", json_data={"tracks": tracks_payload})
            logger.info(f"Removed {len(chunk)} tracks from playlist {playlist_id}.")

    def add_playlist_tracks(
        self, playlist_id: str, track_uris: List[str], dry_run: bool = False
    ) -> None:
        """Add tracks to a playlist by URIs."""
        if not track_uris:
            return
        if dry_run:
            logger.info(f"[DRY RUN] Would add tracks to playlist {playlist_id}: {track_uris}")
            return

        for i in range(0, len(track_uris), 100):
            chunk = track_uris[i : i + 100]
            self.request("POST", f"/playlists/{playlist_id}/tracks", json_data={"uris": chunk})
            logger.info(f"Added {len(chunk)} tracks to playlist {playlist_id}.")

    def get_current_user_id(self) -> Optional[str]:
        """Fetch current authenticated Spotify user ID."""
        data = self.request("GET", "/me")
        return data.get("id") if data else None

    def search_playable_track(
        self, name: str, artist: str, orig_track: Optional[Track] = None
    ) -> Optional[Track]:
        """Search Spotify for an active, playable version of a track with quality scoring."""
        clean_name = name.replace('"', '')
        clean_artist = artist.replace('"', '')
        orig_id = orig_track.id if orig_track else None
        orig_duration = orig_track.duration_ms if orig_track else 0

        queries = [
            f'track:"{clean_name}" artist:"{clean_artist}"',
            f"{clean_name} {clean_artist}",
        ]

        # Stripped parenthetical query if name had (Remaster), (Live), etc.
        stripped_name = normalize_title(clean_name)
        if stripped_name and stripped_name != clean_name.lower():
            queries.append(f'track:"{stripped_name}" artist:"{clean_artist}"')

        best_candidate: Optional[Track] = None
        best_score = 0.0

        for query in queries:
            data = self.request("GET", "/search", params={"q": query, "type": "track", "limit": 10, "market": "from_token"})
            if data and "tracks" in data and "items" in data["tracks"]:
                for item in data["tracks"]["items"]:
                    t = Track.from_dict(item)
                    if not t.is_playable:
                        continue
                    score = calculate_match_score(
                        orig_name=name,
                        orig_artist=artist,
                        candidate=t,
                        orig_duration_ms=orig_duration,
                        orig_id=orig_id,
                    )
                    if score > best_score:
                        best_score = score
                        best_candidate = t
                if best_candidate and best_score >= 0.7:
                    return best_candidate

        return best_candidate if best_score >= 0.45 else None

    def search_playable_album(
        self, name: str, artist: str, orig_album_id: Optional[str] = None
    ) -> Optional[Album]:
        """Search Spotify for an active, playable version of an album with quality scoring."""
        clean_name = name.replace('"', '')
        clean_artist = artist.replace('"', '')

        queries = [
            f'album:"{clean_name}" artist:"{clean_artist}"',
            f"{clean_name} {clean_artist}",
        ]

        stripped_name = normalize_title(clean_name)
        if stripped_name and stripped_name != clean_name.lower():
            queries.append(f'album:"{stripped_name}" artist:"{clean_artist}"')

        best_candidate: Optional[Album] = None
        best_score = 0.0

        for query in queries:
            data = self.request("GET", "/search", params={"q": query, "type": "album", "limit": 10, "market": "from_token"})
            if data and "albums" in data and "items" in data["albums"]:
                for item in data["albums"]["items"]:
                    a = Album.from_dict(item)
                    if not a.is_playable:
                        continue
                    score = calculate_match_score(
                        orig_name=name,
                        orig_artist=artist,
                        candidate=a,
                        orig_id=orig_album_id,
                    )
                    if score > best_score:
                        best_score = score
                        best_candidate = a
                if best_candidate and best_score >= 0.7:
                    return self.get_album_details(best_candidate.id)

        if best_candidate and best_score >= 0.45:
            return self.get_album_details(best_candidate.id)

        return None
