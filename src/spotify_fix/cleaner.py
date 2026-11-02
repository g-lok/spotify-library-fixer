from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple, Any
from spotify_fix.client import SpotifyClient
from spotify_fix.models import Track, Album, ActionLog, UnavailableItem
from spotify_fix.progress import ProgressTracker

logger = logging.getLogger(__name__)


class CleanerPipeline:
    """Orchestrates track/album relinking, album rollup, and unavailable item reporting."""

    def __init__(self, client: SpotifyClient, dry_run: bool = True, progress_enabled: Optional[bool] = None):
        self.client = client
        self.dry_run = dry_run
        self.progress_enabled = progress_enabled

        self.actions: List[ActionLog] = []
        self.unavailable_items: List[UnavailableItem] = []

    def fix_reuploaded_liked_tracks(self) -> Tuple[int, int]:
        """Scan liked tracks for unplayable/deleted tracks and attempt relinking."""
        logger.info("Scanning liked tracks for unplayable or reuploaded songs...")
        tracks = self.client.get_all_liked_tracks()

        relinked_count = 0
        unavailable_count = 0
        unplayable_tracks: List[Track] = []

        for t in tracks:
            if not t.is_playable:
                unplayable_tracks.append(t)

        logger.info(f"Found {len(unplayable_tracks)} unplayable tracks out of {len(tracks)} total liked tracks.")
        tracker = ProgressTracker("Fix Tracks", len(unplayable_tracks), enabled=self.progress_enabled)

        for idx, t in enumerate(unplayable_tracks, 1):
            artist_str = ", ".join(t.artists) if t.artists else "Unknown Artist"
            tracker.update(idx, item_info=t.name)
            logger.info(f"[{idx}/{len(unplayable_tracks)}] Searching replacement for: '{t.name}' by {artist_str} (ID: {t.id})")

            replacement = self.client.search_playable_track(t.name, artist_str)
            if replacement:
                logger.info(f"-> Found replacement: {replacement.id} for '{t.name}'")
                self.client.like_tracks([replacement.id], dry_run=self.dry_run)
                self.client.unlike_tracks([t.id], dry_run=self.dry_run)

                self.actions.append(
                    ActionLog(
                        action="RELINK_TRACK",
                        item_type="track",
                        old_id=t.id,
                        new_id=replacement.id,
                        name=t.name,
                        artist=artist_str,
                        details=f"Relinked unplayable track ID {t.id} to new track ID {replacement.id}",
                        applied=not self.dry_run,
                    )
                )
                relinked_count += 1
            else:
                logger.warning(f"-> No replacement found for: '{t.name}' by {artist_str}")
                self.unavailable_items.append(
                    UnavailableItem(
                        item_type="track",
                        id=t.id,
                        uri=t.uri,
                        name=t.name,
                        artist=artist_str,
                        album_name=t.album_name,
                        reason="Track unplayable and no replacement match found on Spotify",
                    )
                )
                unavailable_count += 1

        tracker.finish(f"Relinked: {relinked_count}, Unavailable: {unavailable_count}")
        logger.info(
            f"Liked tracks scan complete. Relinked: {relinked_count}, Unavailable: {unavailable_count}"
        )
        return relinked_count, unavailable_count

    def rollup_albums(self) -> int:
        """Consolidate tracks into album likes if ALL tracks of an album are liked."""
        logger.info("Starting album rollup scan...")
        liked_tracks = self.client.get_all_liked_tracks()

        # Group liked tracks by album_id
        album_tracks_map: Dict[str, List[Track]] = {}
        for t in liked_tracks:
            if t.album_id:
                album_tracks_map.setdefault(t.album_id, []).append(t)

        logger.info(f"Grouped liked tracks into {len(album_tracks_map)} distinct albums for evaluation.")
        rolled_up_count = 0
        evaluated = 0

        for album_id, tracks in album_tracks_map.items():
            evaluated += 1
            if evaluated % 100 == 0:
                logger.info(f"Evaluated {evaluated}/{len(album_tracks_map)} candidate albums...")

            album = self.client.get_album_details(album_id)
            if not album or not album.track_ids or album.total_tracks == 0:
                continue

            liked_track_ids_set = {t.id for t in tracks}
            album_track_ids_set = set(album.track_ids)

            # Check if all tracks in the album are liked
            if album_track_ids_set and album_track_ids_set.issubset(liked_track_ids_set):
                artist_str = ", ".join(album.artists) if album.artists else "Unknown Artist"
                logger.info(
                    f"Consolidating Album: '{album.name}' by {artist_str} ({len(album.track_ids)}/{album.total_tracks} tracks)"
                )

                self.client.like_albums([album_id], dry_run=self.dry_run)
                self.client.unlike_tracks(sorted(album_track_ids_set), dry_run=self.dry_run)

                self.actions.append(
                    ActionLog(
                        action="ROLLUP_ALBUM",
                        item_type="album",
                        old_id=album_id,
                        new_id=album_id,
                        name=album.name,
                        artist=artist_str,
                        details=f"Consolidated {len(album.track_ids)} individual track likes into album like",
                        applied=not self.dry_run,
                    )
                )
                rolled_up_count += 1

        logger.info(f"Album rollup complete. Total albums consolidated: {rolled_up_count}")
        return rolled_up_count

    def fix_reuploaded_liked_albums(self) -> Tuple[int, int]:
        """Scan liked albums for unplayable albums/tracks and attempt relinking."""
        logger.info("Scanning liked albums for unplayable or reuploaded albums...")
        albums = self.client.get_all_liked_albums()

        relinked_count = 0
        unavailable_count = 0
        tracker = ProgressTracker("Fix Albums", len(albums), enabled=self.progress_enabled)

        for idx, a in enumerate(albums, 1):
            tracker.update(idx, item_info=a.name)
            album_details = self.client.get_album_details(a.id)
            if not album_details:
                continue

            # Check album playability or if any tracks inside album are unplayable
            tracks = list(self.client.get_paginated(f"/albums/{a.id}/tracks", params={"market": "from_token"}))
            has_unplayable = not a.is_playable or any(not t.get("is_playable", True) for t in tracks)

            if not has_unplayable:
                continue

            artist_str = ", ".join(a.artists) if a.artists else "Unknown Artist"
            logger.info(f"Unplayable album/tracks detected: '{a.name}' by {artist_str} (ID: {a.id})")

            replacement = self.client.search_playable_album(a.name, artist_str)
            if replacement and replacement.id != a.id:
                logger.info(
                    f"Found replacement album for '{a.name}': {replacement.id} (Old: {a.id})"
                )

                self.client.like_albums([replacement.id], dry_run=self.dry_run)
                self.client.unlike_albums([a.id], dry_run=self.dry_run)

                self.actions.append(
                    ActionLog(
                        action="RELINK_ALBUM",
                        item_type="album",
                        old_id=a.id,
                        new_id=replacement.id,
                        name=a.name,
                        artist=artist_str,
                        details=f"Relinked unplayable album ID {a.id} to new album ID {replacement.id}",
                        applied=not self.dry_run,
                    )
                )
                relinked_count += 1
            elif not replacement:
                logger.warning(f"No replacement found for album: '{a.name}' by {artist_str}")
                self.unavailable_items.append(
                    UnavailableItem(
                        item_type="album",
                        id=a.id,
                        uri=a.uri,
                        name=a.name,
                        artist=artist_str,
                        reason="Album or tracks unplayable and no replacement match found on Spotify",
                    )
                )
                unavailable_count += 1

        tracker.finish(f"Relinked: {relinked_count}, Unavailable: {unavailable_count}")
        logger.info(
            f"Liked albums scan complete. Relinked: {relinked_count}, Unavailable: {unavailable_count}"
        )
        return relinked_count, unavailable_count

    def fix_reuploaded_playlists(self) -> Tuple[int, int]:
        """Scan user owned/editable playlists and fix unplayable tracks."""
        logger.info("Scanning user playlists for unplayable tracks...")
        current_user_id = self.client.get_current_user_id()
        playlists = self.client.get_all_user_playlists()

        relinked_count = 0
        unavailable_count = 0

        for pl in playlists:
            playlist_id = pl.get("id")
            playlist_name = pl.get("name", "Unknown Playlist")
            owner_id = pl.get("owner", {}).get("id")
            is_collaborative = pl.get("collaborative", False)

            if not playlist_id:
                continue

            # Only scan and modify playlists owned by user or collaborative
            if current_user_id and owner_id != current_user_id and not is_collaborative:
                logger.debug(f"Skipping non-owned playlist '{playlist_name}'")
                continue

            items = self.client.get_playlist_tracks(playlist_id)
            for item in items:
                track_dict = item.get("track")
                if not track_dict or not track_dict.get("id"):
                    continue

                t = Track.from_dict(track_dict)
                if t.is_playable:
                    continue

                artist_str = ", ".join(t.artists) if t.artists else "Unknown Artist"
                logger.info(
                    f"Unplayable playlist track in '{playlist_name}': '{t.name}' by {artist_str} (ID: {t.id})"
                )

                replacement = self.client.search_playable_track(t.name, artist_str)
                if replacement:
                    logger.info(
                        f"Replacing unplayable track in playlist '{playlist_name}': {t.id} -> {replacement.id}"
                    )
                    try:
                        self.client.remove_playlist_tracks(
                            playlist_id, [t.uri], dry_run=self.dry_run
                        )
                        self.client.add_playlist_tracks(
                            playlist_id, [replacement.uri], dry_run=self.dry_run
                        )

                        self.actions.append(
                            ActionLog(
                                action="FIX_PLAYLIST_TRACK",
                                item_type="playlist_track",
                                old_id=t.id,
                                new_id=replacement.id,
                                name=t.name,
                                artist=artist_str,
                                details=f"Replaced unplayable track in playlist '{playlist_name}'",
                                applied=not self.dry_run,
                            )
                        )
                        relinked_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to update playlist '{playlist_name}': {e}")
                else:
                    self.unavailable_items.append(
                        UnavailableItem(
                            item_type="playlist_track",
                            id=t.id,
                            uri=t.uri,
                            name=t.name,
                            artist=artist_str,
                            album_name=f"Playlist: {playlist_name}",
                            reason=f"Unplayable track in playlist '{playlist_name}' with no Spotify replacement",
                        )
                    )
                    unavailable_count += 1

        logger.info(
            f"Playlist scan complete. Relinked: {relinked_count}, Unavailable: {unavailable_count}"
        )
        return relinked_count, unavailable_count

    def export_reports(self, report_path: Optional[Path | str] = None) -> Path:
        """Export unavailable items and executed action logs into structured output file."""
        if not report_path:
            report_path = Path.home() / "tmp" / "spotify_fix_report.json"
        else:
            report_path = Path(report_path)

        report_path.parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "mode": "DRY RUN" if self.dry_run else "APPLIED",
            "actions_summary": {
                "total_actions": len(self.actions),
                "relinked_tracks": sum(1 for a in self.actions if a.action == "RELINK_TRACK"),
                "relinked_albums": sum(1 for a in self.actions if a.action == "RELINK_ALBUM"),
                "rolled_up_albums": sum(1 for a in self.actions if a.action == "ROLLUP_ALBUM"),
                "fixed_playlist_tracks": sum(
                    1 for a in self.actions if a.action == "FIX_PLAYLIST_TRACK"
                ),
            },
            "actions": [a.__dict__ for a in self.actions],
            "unavailable_items_summary": {
                "total_unavailable": len(self.unavailable_items),
                "tracks": sum(1 for u in self.unavailable_items if u.item_type == "track"),
                "albums": sum(1 for u in self.unavailable_items if u.item_type == "album"),
                "playlist_tracks": sum(
                    1 for u in self.unavailable_items if u.item_type == "playlist_track"
                ),
            },
            "unavailable_items": [u.__dict__ for u in self.unavailable_items],
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)

        logger.info(f"Report successfully saved to {report_path}")
        return report_path
