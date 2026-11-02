from __future__ import annotations

import logging
import time
import requests
from typing import List, Dict, Any, Optional, Generator
from spotify_fix.auth import AuthManager
from spotify_fix.models import Track, Album

logger = logging.getLogger(__name__)

BASE_URL = "https://api.spotify.com/v1"


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

    def search_playable_track(self, name: str, artist: str) -> Optional[Track]:
        """Search Spotify for an active, playable version of a track."""
        clean_name = name.replace('"', '')
        clean_artist = artist.replace('"', '')
        query = f'track:"{clean_name}" artist:"{clean_artist}"'
        
        data = self.request("GET", "/search", params={"q": query, "type": "track", "limit": 10, "market": "from_token"})
        if not data or "tracks" not in data or not data["tracks"].get("items"):
            # Try looser search query if strict search yields no results
            query = f"{clean_name} {clean_artist}"
            data = self.request("GET", "/search", params={"q": query, "type": "track", "limit": 10, "market": "from_token"})

        if data and "tracks" in data and "items" in data["tracks"]:
            for item in data["tracks"]["items"]:
                t = Track.from_dict(item)
                if t.is_playable:
                    return t

        return None

    def search_playable_album(self, name: str, artist: str) -> Optional[Album]:
        """Search Spotify for an active, playable version of an album."""
        clean_name = name.replace('"', '')
        clean_artist = artist.replace('"', '')
        query = f'album:"{clean_name}" artist:"{clean_artist}"'

        data = self.request("GET", "/search", params={"q": query, "type": "album", "limit": 10, "market": "from_token"})
        if not data or "albums" not in data or not data["albums"].get("items"):
            query = f"{clean_name} {clean_artist}"
            data = self.request("GET", "/search", params={"q": query, "type": "album", "limit": 10, "market": "from_token"})

        if data and "albums" in data and "items" in data["albums"]:
            for item in data["albums"]["items"]:
                a = Album.from_dict(item)
                if a.is_playable:
                    return self.get_album_details(a.id)

        return None
