from unittest.mock import MagicMock
from requests.exceptions import HTTPError
from spotify_fix.cleaner import CleanerPipeline
from spotify_fix.models import Track, Album


def test_fix_reuploaded_liked_tracks():
    mock_client = MagicMock()

    playable_track = Track(
        id="t1", uri="spotify:track:t1", name="Good Song", artists=["Band"], album_id="a1", album_name="Alb", is_playable=True
    )
    unplayable_track = Track(
        id="t2", uri="spotify:track:t2", name="Deleted Song", artists=["Band"], album_id="a2", album_name="Alb2", is_playable=False
    )
    replacement_track = Track(
        id="t3", uri="spotify:track:t3", name="Deleted Song", artists=["Band"], album_id="a3", album_name="Alb3", is_playable=True
    )

    mock_client.get_all_liked_tracks.return_value = [playable_track, unplayable_track]
    mock_client.search_playable_track.return_value = replacement_track

    pipeline = CleanerPipeline(client=mock_client, dry_run=True)
    relinked, unavailable = pipeline.fix_reuploaded_liked_tracks()

    assert relinked == 1
    assert unavailable == 0
    assert len(pipeline.actions) == 1
    assert pipeline.actions[0].old_id == "t2"
    assert pipeline.actions[0].new_id == "t3"

    mock_client.like_tracks.assert_called_with(["t3"], dry_run=True)
    mock_client.unlike_tracks.assert_called_with(["t2"], dry_run=True)


def test_rollup_albums():
    mock_client = MagicMock()

    t1 = Track(id="t1", uri="spotify:track:t1", name="Track 1", artists=["Artist"], album_id="album1", album_name="Alb", is_playable=True)
    t2 = Track(id="t2", uri="spotify:track:t2", name="Track 2", artists=["Artist"], album_id="album1", album_name="Alb", is_playable=True)

    mock_client.get_all_liked_tracks.return_value = [t1, t2]

    album_obj = Album(
        id="album1",
        uri="spotify:album:album1",
        name="Alb",
        artists=["Artist"],
        total_tracks=2,
        track_ids=["t1", "t2"],
        is_playable=True,
    )
    mock_client.get_album_details.return_value = album_obj

    pipeline = CleanerPipeline(client=mock_client, dry_run=True)
    rolled_up = pipeline.rollup_albums()

    assert rolled_up == 1
    assert len(pipeline.actions) == 1
    assert pipeline.actions[0].action == "ROLLUP_ALBUM"

    mock_client.like_albums.assert_called_with(["album1"], dry_run=True)
    mock_client.unlike_tracks.assert_called_with(["t1", "t2"], dry_run=True)


def test_fix_reuploaded_liked_albums_with_unplayable_tracks():
    """Test album relinking when album container is playable but tracks inside are unplayable."""
    mock_client = MagicMock()

    playable_album = Album(id="a1", uri="spotify:album:a1", name="Good Album", artists=["Band"], total_tracks=2, is_playable=True)
    album_with_unplayable_tracks = Album(id="a2", uri="spotify:album:a2", name="Old Album", artists=["Band"], total_tracks=2, is_playable=True)
    replacement_album = Album(id="a3", uri="spotify:album:a3", name="Old Album", artists=["Band"], total_tracks=2, is_playable=True)

    mock_client.get_all_liked_albums.return_value = [playable_album, album_with_unplayable_tracks]
    mock_client.get_album_details.side_effect = lambda aid: playable_album if aid == "a1" else album_with_unplayable_tracks

    def mock_get_paginated(endpoint, params=None):
        if endpoint == "/me/albums":
            return [playable_album, album_with_unplayable_tracks]
        elif "/albums/a1/tracks" in endpoint:
            return [{"id": "t1", "is_playable": True}]
        elif "/albums/a2/tracks" in endpoint:
            return [{"id": "t2", "is_playable": False}]
        return []

    mock_client.get_paginated.side_effect = mock_get_paginated
    mock_client.search_playable_album.return_value = replacement_album

    pipeline = CleanerPipeline(client=mock_client, dry_run=True)
    relinked, unavailable = pipeline.fix_reuploaded_liked_albums()

    assert relinked == 1
    assert unavailable == 0
    assert len(pipeline.actions) == 1
    assert pipeline.actions[0].action == "RELINK_ALBUM"
    assert pipeline.actions[0].old_id == "a2"
    assert pipeline.actions[0].new_id == "a3"


def test_fix_reuploaded_liked_albums_unavailable_no_match():
    """Test when an unplayable album cannot be matched on Spotify."""
    mock_client = MagicMock()

    unplayable_album = Album(id="a2", uri="spotify:album:a2", name="Lost Album", artists=["Band"], total_tracks=2, is_playable=False)

    mock_client.get_all_liked_albums.return_value = [unplayable_album]
    mock_client.get_album_details.return_value = unplayable_album
    
    def mock_get_paginated(endpoint, params=None):
        if endpoint == "/me/albums":
            return [unplayable_album]
        return [{"id": "t1", "is_playable": False}]

    mock_client.get_paginated.side_effect = mock_get_paginated
    mock_client.search_playable_album.return_value = None

    pipeline = CleanerPipeline(client=mock_client, dry_run=True)
    relinked, unavailable = pipeline.fix_reuploaded_liked_albums()

    assert relinked == 0
    assert unavailable == 1
    assert len(pipeline.unavailable_items) == 1
    assert pipeline.unavailable_items[0].id == "a2"
    assert pipeline.unavailable_items[0].name == "Lost Album"


def test_purge_fallback_files(tmp_path):
    mock_client = MagicMock()
    pipeline = CleanerPipeline(client=mock_client, dry_run=False)

    file_orig = tmp_path / "01 - Track.ogg"
    file_fallback = tmp_path / "01 - Track_1.ogg"
    file_orig.write_text("audio data")
    file_fallback.write_text("fallback data")

    purged = pipeline.purge_fallback_files(tmp_path)
    assert purged == 1
    assert not file_fallback.exists()
    assert file_orig.exists()


def test_fix_reuploaded_playlists_ownership_filtering():
    mock_client = MagicMock()
    mock_client.get_current_user_id.return_value = "user_me"

    owned_playlist = {
        "id": "pl_owned",
        "name": "My Playlist",
        "owner": {"id": "user_me"},
        "collaborative": False,
    }
    other_playlist = {
        "id": "pl_other",
        "name": "Other Playlist",
        "owner": {"id": "user_other"},
        "collaborative": False,
    }

    unplayable_track = {
        "track": {
            "id": "t_del",
            "name": "Unplayable Track",
            "artists": [{"name": "Artist"}],
            "is_playable": False,
        }
    }
    replacement = Track(
        id="t_new", uri="spotify:track:t_new", name="Unplayable Track", artists=["Artist"], album_id="a1", album_name="Alb", is_playable=True
    )

    mock_client.get_all_user_playlists.return_value = [owned_playlist, other_playlist]
    mock_client.get_playlist_tracks.side_effect = lambda pl_id: [unplayable_track] if pl_id == "pl_owned" else []
    mock_client.search_playable_track.return_value = replacement

    pipeline = CleanerPipeline(client=mock_client, dry_run=True)
    relinked, unavailable = pipeline.fix_reuploaded_playlists()

    assert relinked == 1
    mock_client.get_playlist_tracks.assert_called_once_with("pl_owned")


def test_fix_reuploaded_playlists_error_handling():
    mock_client = MagicMock()
    mock_client.get_current_user_id.return_value = "user_me"

    playlist = {
        "id": "pl1",
        "name": "My Playlist",
        "owner": {"id": "user_me"},
        "collaborative": False,
    }
    unplayable_track = {
        "track": {
            "id": "t_del",
            "name": "Deleted Track",
            "artists": [{"name": "Artist"}],
            "is_playable": False,
        }
    }
    replacement = Track(
        id="t_new", uri="spotify:track:t_new", name="Deleted Track", artists=["Artist"], album_id="a1", album_name="Alb", is_playable=True
    )

    mock_client.get_all_user_playlists.return_value = [playlist]
    mock_client.get_playlist_tracks.return_value = [unplayable_track]
    mock_client.search_playable_track.return_value = replacement
    mock_client.remove_playlist_tracks.side_effect = HTTPError("403 Client Error: Forbidden")

    pipeline = CleanerPipeline(client=mock_client, dry_run=False)
    relinked, unavailable = pipeline.fix_reuploaded_playlists()

    assert relinked == 0


def test_export_reports(tmp_path):
    mock_client = MagicMock()
    pipeline = CleanerPipeline(client=mock_client, dry_run=True)

    out_file = tmp_path / "report.json"
    result_path = pipeline.export_reports(report_path=out_file)

    assert result_path.exists()
