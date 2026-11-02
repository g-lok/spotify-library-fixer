# Errors Log

## 2026-11-02: Playlist 403 Forbidden on Non-Owned Playlists

- **Error**: `403 Client Error: Forbidden for url:
  https://api.spotify.com/v1/playlists/<id>/tracks`
- **Cause**: Attempted to remove/add tracks in a followed playlist owned by
  another user.
- **Fix**: Filter playlists by `owner.id == current_user_id` or `collaborative
  is True`, and wrap playlist track updates in `try/except` HTTPError block.

## 2026-11-02: Keymaster Token 429 Rate Limit

- **Error**: `429 Too Many Requests` on `PUT /v1/me/tracks` after 5 attempts.
- **Cause**: Using Librespot Keymaster token for Web API write endpoints.
- **Fix**: Run interactive PKCE login (`--login`) to obtain OAuth PKCE token with
  `user-library-modify` scope.
