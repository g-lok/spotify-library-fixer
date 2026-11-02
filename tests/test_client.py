from unittest.mock import MagicMock, patch
import pytest
import requests
from spotify_fix.client import SpotifyClient


def test_get_current_user_id():
    mock_auth = MagicMock()
    mock_auth.get_access_token.return_value = "fake_token"

    client = SpotifyClient(auth_manager=mock_auth)

    with patch.object(client.session, "request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"id": "user123"}'
        mock_resp.json.return_value = {"id": "user123"}
        mock_req.return_value = mock_resp

        user_id = client.get_current_user_id()
        assert user_id == "user123"


def test_like_tracks_batching():
    mock_auth = MagicMock()
    client = SpotifyClient(auth_manager=mock_auth)

    with patch.object(client, "request") as mock_request:
        track_ids = [f"t_{i}" for i in range(120)]
        client.like_tracks(track_ids, dry_run=False)

        # 120 tracks chunked into 50, 50, 20 = 3 calls
        assert mock_request.call_count == 3
        mock_request.assert_any_call("PUT", "/me/tracks", json_data={"ids": [f"t_{i}" for i in range(50)]})


def test_request_429_rate_limit_retry():
    mock_auth = MagicMock()
    client = SpotifyClient(auth_manager=mock_auth)

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "0"}

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.content = b'{"status": "ok"}'
    resp_200.json.return_value = {"status": "ok"}

    with patch.object(client.session, "request", side_effect=[resp_429, resp_200]):
        res = client.request("GET", "/test")
        assert res == {"status": "ok"}
