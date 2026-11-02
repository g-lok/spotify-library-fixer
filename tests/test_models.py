from spotify_fix.models import Track, Album, ActionLog, UnavailableItem


def test_track_from_dict():
    data = {
        "id": "123",
        "uri": "spotify:track:123",
        "name": "Test Song",
        "artists": [{"name": "Test Artist"}],
        "album": {"id": "album1", "name": "Test Album"},
        "is_playable": True,
        "disc_number": 1,
        "track_number": 2,
        "duration_ms": 180000,
    }
    track = Track.from_dict(data)
    assert track.id == "123"
    assert track.name == "Test Song"
    assert track.artists == ["Test Artist"]
    assert track.album_id == "album1"
    assert track.is_playable is True


def test_album_from_dict():
    data = {
        "id": "album1",
        "uri": "spotify:album:album1",
        "name": "Test Album",
        "artists": [{"name": "Test Artist"}],
        "total_tracks": 2,
        "tracks": {
            "items": [
                {"id": "t1"},
                {"id": "t2"},
            ]
        },
        "is_playable": True,
    }
    album = Album.from_dict(data)
    assert album.id == "album1"
    assert album.name == "Test Album"
    assert album.total_tracks == 2
    assert album.track_ids == ["t1", "t2"]


def test_action_log_and_unavailable_item():
    log = ActionLog(
        action="RELINK_TRACK",
        item_type="track",
        old_id="old1",
        new_id="new1",
        name="Song",
        artist="Artist",
        details="Relinked track",
        applied=False,
    )
    assert log.old_id == "old1"
    assert log.applied is False

    item = UnavailableItem(
        item_type="track",
        id="unavail1",
        uri="spotify:track:unavail1",
        name="Lost Song",
        artist="Artist",
        reason="Not found",
    )
    assert item.id == "unavail1"
    assert item.reason == "Not found"
