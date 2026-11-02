from __future__ import annotations

import json
import logging
import secrets
import hashlib
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from base64 import urlsafe_b64encode, b64encode
from pathlib import Path
from typing import Optional, Dict, Any
import requests
from librespot.core import Session

logger = logging.getLogger(__name__)

DEFAULT_CREDENTIAL_LOCATIONS = [
    Path.home() / ".config/zotify/api_credentials.json",
    Path.home() / ".config/zotify/credentials.json",
    Path.home() / ".config/spotify-fix/api_credentials.json",
    Path.home() / ".config/spotify-fix/credentials.json",
    Path.cwd() / "api_credentials.json",
    Path.cwd() / "credentials.json",
]


class PKCEAuthServer:
    """Standalone PKCE Authorization Server for Spotify OAuth."""

    def __init__(self, client_id: str = "715afe9af8b3491199907272a61625c4", port: int = 8888):
        self.client_id = client_id
        self.port = port
        self.redirect_uri = f"http://127.0.0.1:{self.port}/login"
        self.code_verifier = secrets.token_urlsafe(64)
        self.received_creds: Optional[Dict[str, Any]] = None

    def _generate_challenge(self) -> str:
        digest = hashlib.sha256(self.code_verifier.encode("ascii")).digest()
        return urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def get_auth_url(self) -> str:
        scopes = [
            "streaming",
            "playlist-read-private",
            "playlist-read-collaborative",
            "playlist-modify-public",
            "playlist-modify-private",
            "user-follow-read",
            "user-read-playback-position",
            "user-top-read",
            "user-read-recently-played",
            "user-library-read",
            "user-library-modify",
            "user-read-email",
            "user-read-private",
        ]
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": self._generate_challenge(),
            "scope": " ".join(scopes),
        }
        return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)

    def run_server(self) -> Dict[str, Any]:
        server_instance = self

        class OAuthCallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress default HTTP server logging

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)

                if "code" in qs:
                    code = qs["code"][0]
                    # Exchange authorization code for token
                    token_url = "https://accounts.spotify.com/api/token"
                    payload = {
                        "grant_type": "authorization_code",
                        "client_id": server_instance.client_id,
                        "code": code,
                        "redirect_uri": server_instance.redirect_uri,
                        "code_verifier": server_instance.code_verifier,
                    }
                    headers = {"Content-Type": "application/x-www-form-urlencoded"}

                    resp = requests.post(token_url, data=payload, headers=headers, timeout=15)
                    if resp.status_code == 200:
                        token_data = resp.json()
                        import time
                        server_instance.received_creds = {
                            "client_id": server_instance.client_id,
                            "access_token": token_data["access_token"],
                            "refresh_token": token_data.get("refresh_token", ""),
                            "expires_at": time.time() + token_data.get("expires_in", 3600),
                            "type": "OAUTH_PKCE_TOKEN",
                        }

                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        html = """
                        <html><body style="font-family:sans-serif; text-align:center; padding-top:50px;">
                        <h1 style="color:#1DB954;">Authorization Successful!</h1>
                        <p>Spotify permissions granted for <b>spotify-fix</b>.</p>
                        <p>You can close this tab and return to your terminal.</p>
                        </body></html>
                        """
                        self.wfile.write(html.encode("utf-8"))
                        return

                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>Authorization Failed or Missing Code</h1>")

        class ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        httpd = ReusableHTTPServer(("127.0.0.1", self.port), OAuthCallbackHandler)
        auth_url = self.get_auth_url()

        print("\n" + "=" * 70, flush=True)
        print("SPOTIFY AUTHORIZATION REQUIRED (READ + WRITE PERMISSIONS)", flush=True)
        print("Open the following link in your browser to approve permissions:", flush=True)
        print(f"\n{auth_url}\n", flush=True)
        print("Waiting for browser callback on http://127.0.0.1:8888/login ...", flush=True)
        print("=" * 70 + "\n", flush=True)

        while not self.received_creds:
            httpd.handle_request()

        httpd.server_close()
        return self.received_creds


class AuthManager:
    """Handles Spotify OAuth token management and Librespot session initialization."""

    def __init__(
        self,
        api_creds_path: Optional[Path | str] = None,
        creds_path: Optional[Path | str] = None,
    ):
        self.api_creds_path = Path(api_creds_path) if api_creds_path else None
        self.creds_path = Path(creds_path) if creds_path else None

        self._api_creds_data: Optional[Dict[str, Any]] = None
        self._creds_data: Optional[Dict[str, Any]] = None
        self._librespot_session: Optional[Session] = None
        self.read_token: Optional[str] = None
        self.write_token: Optional[str] = None

        self._discover_credentials()

    def _discover_credentials(self) -> None:
        """Find zotify or local credential files."""
        # Check API credentials
        api_candidates = []
        if self.api_creds_path:
            api_candidates.append(self.api_creds_path)
        api_candidates.extend(
            p for p in DEFAULT_CREDENTIAL_LOCATIONS if p.name == "api_credentials.json"
        )

        for p in api_candidates:
            if p.exists() and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "refresh_token" in data and "client_id" in data:
                        self._api_creds_data = data
                        self.api_creds_path = p
                        logger.info(f"Loaded API credentials from {p}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to read API credentials from {p}: {e}")

        # Check Login5 credentials
        creds_candidates = []
        if self.creds_path:
            creds_candidates.append(self.creds_path)
        creds_candidates.extend(
            p for p in DEFAULT_CREDENTIAL_LOCATIONS if p.name == "credentials.json"
        )

        for p in creds_candidates:
            if p.exists() and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "credentials" in data and "username" in data:
                        self._creds_data = data
                        self.creds_path = p
                        logger.info(f"Loaded Login5 credentials from {p}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to read Login5 credentials from {p}: {e}")

    def interactive_login(self) -> None:
        """Run PKCE OAuth login server to acquire write permissions."""
        pkce_server = PKCEAuthServer()
        creds = pkce_server.run_server()

        self._api_creds_data = creds
        if not self.api_creds_path:
            self.api_creds_path = Path.home() / ".config/zotify/api_credentials.json"
        self._save_api_credentials()
        logger.info(f"Successfully authorized and saved API credentials to {self.api_creds_path}")

    def refresh_read_token(self) -> str:
        """Refresh read token via api_credentials.json for high-quota GET requests."""
        if self._api_creds_data:
            client_id = self._api_creds_data["client_id"]
            refresh_token = self._api_creds_data["refresh_token"]

            url = "https://accounts.spotify.com/api/token"
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            resp = requests.post(url, data=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                token_data = resp.json()
                self.read_token = token_data["access_token"]
                self._api_creds_data["access_token"] = self.read_token
                if "refresh_token" in token_data:
                    self._api_creds_data["refresh_token"] = token_data["refresh_token"]
                if "expires_in" in token_data:
                    import time
                    self._api_creds_data["expires_at"] = time.time() + token_data["expires_in"]

                self._save_api_credentials()
                logger.info("Successfully refreshed Spotify API read token.")
                return self.read_token

        return self.get_write_token()

    def get_read_token(self, force_refresh: bool = False) -> str:
        """Get valid token for GET requests."""
        if not self.read_token or force_refresh:
            return self.refresh_read_token()
        return self.read_token

    def get_write_token(self, force_refresh: bool = False) -> str:
        """Get valid token with user-library-modify and playlist write scopes."""
        if self.write_token and not force_refresh:
            return self.write_token

        read_token = self.get_read_token(force_refresh=force_refresh)
        if self._api_creds_data and self.read_token:
            self.write_token = self.read_token
            return self.write_token

        session = self.get_librespot_session()
        if session:
            try:
                scopes = [
                    "user-library-read",
                    "user-library-modify",
                    "playlist-read-private",
                    "playlist-read-collaborative",
                    "playlist-modify-public",
                    "playlist-modify-private",
                ]
                self.write_token = session.tokens().get_token(*scopes).access_token
                logger.info("Acquired write access token via Librespot Session.")
                return self.write_token
            except Exception as e:
                logger.warning(f"Failed to acquire Librespot write token: {e}")

        return self.get_read_token()

    def get_access_token(self, force_refresh: bool = False, is_write: bool = False) -> str:
        """Return token according to request type."""
        if is_write:
            return self.get_write_token(force_refresh=force_refresh)
        return self.get_read_token(force_refresh=force_refresh)

    def _save_api_credentials(self) -> None:
        """Write refreshed API credentials back to disk."""
        if self.api_creds_path and self._api_creds_data:
            try:
                with open(self.api_creds_path, "w", encoding="utf-8") as f:
                    json.dump(self._api_creds_data, f, indent=4)
            except Exception as e:
                logger.warning(f"Failed to save credentials to {self.api_creds_path}: {e}")

    def get_librespot_session(self) -> Optional[Session]:
        """Initialize or return cached Librespot session."""
        if self._librespot_session:
            return self._librespot_session

        if not self._creds_data:
            return None

        try:
            b64creds = b64encode(json.dumps(self._creds_data).encode("ascii"))
            builder = Session.Builder()
            builder.conf.store_credentials = False
            self._librespot_session = builder.stored(b64creds).create()
            logger.info("Librespot Session initialized.")
            return self._librespot_session
        except Exception as e:
            logger.error(f"Failed to create Librespot session: {e}")
            return None
