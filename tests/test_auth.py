import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from spotify_fix.auth import AuthManager


def test_auth_manager_discovery(tmp_path):
    api_creds = tmp_path / "api_credentials.json"
    api_creds.write_text(
        json.dumps({
            "client_id": "cid_test",
            "access_token": "token_test",
            "refresh_token": "refresh_test",
            "type": "OAUTH_PKCE_TOKEN",
        })
    )

    auth = AuthManager(api_creds_path=api_creds)
    assert auth._api_creds_data is not None
    assert auth._api_creds_data["client_id"] == "cid_test"


@patch.object(AuthManager, "get_librespot_session", return_value=None)
@patch("requests.post")
def test_refresh_access_token(mock_post, mock_librespot_session, tmp_path):
    api_creds = tmp_path / "api_credentials.json"
    api_creds.write_text(
        json.dumps({
            "client_id": "cid_test",
            "access_token": "old_token",
            "refresh_token": "refresh_test",
            "type": "OAUTH_PKCE_TOKEN",
        })
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new_refreshed_token",
        "expires_in": 3600,
    }
    mock_post.return_value = mock_resp

    auth = AuthManager(api_creds_path=api_creds)
    token = auth.get_access_token()

    assert token == "new_refreshed_token"
    mock_post.assert_called_once()
