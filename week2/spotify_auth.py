"""Small Spotify OAuth helper. Run --configure, then --login, then --check.

Only --login opens a browser. Server tools should use get_access_token(), which
refreshes cached credentials or raises an actionable, safe OAuthError.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import getpass
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import warnings
import webbrowser


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
TOKEN_PATH = BASE_DIR / ".spotify-tokens.json"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = ("playlist-read-private", "playlist-modify-private")
TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
REQUEST_TIMEOUT = 15
LOGIN_TIMEOUT = 300
EXPIRY_SKEW = 60


class OAuthError(Exception):
    """An error whose public fields never contain credentials or raw responses."""

    def __init__(self, code: str, message: str, retryable: bool = False,
                 next_step: str = "Run python spotify_auth.py --login."):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.next_step = next_step

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable, "next_step": self.next_step}


def _read_env(path: Path) -> dict[str, str]:
    """Read simple KEY=value files; generated values are JSON-quoted strings."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    except OSError:
        raise OAuthError("CONFIG_ERROR", "Cannot read the local .env file.",
                         next_step="Check file permissions, then run --configure.") from None
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key.strip() not in {
            "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI"
        }:
            continue
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                raise OAuthError("CONFIG_ERROR", "A .env value is incorrectly quoted.",
                                 next_step="Run python spotify_auth.py --configure.") from None
        if not isinstance(value, str):
            raise OAuthError("CONFIG_ERROR", "Configuration values must be strings.",
                             next_step="Run python spotify_auth.py --configure.")
        values[key.strip()] = value
    return values


def _atomic_write(path: Path, content: str) -> None:
    """Replace a file atomically with owner-only permissions, including on first write."""
    path = Path(path)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f"{path.name}.", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        raise OAuthError("LOCAL_STORAGE_ERROR", "Cannot save the local credentials file.",
                         next_step="Check that this script's directory is writable, then retry.") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str = REDIRECT_URI
    token_path: Path = TOKEN_PATH

    @classmethod
    def from_env(cls) -> Config:
        values = _read_env(ENV_PATH)
        for key in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI"):
            if key in os.environ:
                values[key] = os.environ[key]
        client_id = values.get("SPOTIFY_CLIENT_ID", "").strip()
        client_secret = values.get("SPOTIFY_CLIENT_SECRET", "").strip()
        redirect_uri = values.get("SPOTIFY_REDIRECT_URI", REDIRECT_URI).strip()
        if not client_id or not client_secret:
            raise OAuthError("CONFIG_ERROR", "Spotify app credentials are missing.",
                             next_step="Run python spotify_auth.py --configure.")
        if redirect_uri != REDIRECT_URI:
            raise OAuthError("CONFIG_ERROR", "The redirect URI does not match this local helper.",
                             next_step=f"Register {REDIRECT_URI} in Spotify and run --configure.")
        return cls(client_id, client_secret, redirect_uri, TOKEN_PATH)


class SpotifyOAuth:
    def __init__(self, config: Config):
        self.config = config
        self._lock = threading.Lock()

    def _load_tokens(self) -> dict[str, Any] | None:
        try:
            tokens = json.loads(Path(self.config.token_path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            raise OAuthError("AUTH_REQUIRED", "The local token cache cannot be read.") from None
        if (not isinstance(tokens, dict)
                or tokens.get("client_id") != self.config.client_id
                or not isinstance(tokens.get("access_token"), str)
                or not tokens["access_token"]):
            raise OAuthError("AUTH_REQUIRED", "The token cache is invalid or belongs to another app.")
        self._check_scopes(tokens.get("scope"))
        return tokens

    @staticmethod
    def _check_scopes(scope: Any) -> None:
        if scope is not None and (not isinstance(scope, str)
                                  or not set(SCOPES).issubset(scope.split())):
            raise OAuthError("AUTH_REQUIRED", "Spotify did not grant both required playlist permissions.",
                             next_step="Run --login and approve the requested playlist permissions.")

    def _save_tokens(self, response: dict[str, Any],
                     previous: dict[str, Any] | None = None) -> dict[str, Any]:
        previous = previous or {}
        access_token = response.get("access_token")
        refresh_token = response.get("refresh_token") or previous.get("refresh_token")
        token_type = response.get("token_type", "Bearer")
        try:
            lifetime = float(response["expires_in"])
        except (KeyError, TypeError, ValueError):
            lifetime = 0
        if (not isinstance(access_token, str) or not access_token
                or not isinstance(refresh_token, str) or not refresh_token
                or not math.isfinite(lifetime) or lifetime <= 0
                or not isinstance(token_type, str) or token_type.lower() != "bearer"):
            raise OAuthError("TOKEN_ERROR", "Spotify returned an incomplete token response.",
                             retryable=True, next_step="Retry once; if this persists, run --login.")
        scope = response.get("scope", previous.get("scope", " ".join(SCOPES)))
        self._check_scopes(scope)
        tokens = {"access_token": access_token, "refresh_token": refresh_token,
                  "token_type": "Bearer", "expires_at": time.time() + lifetime,
                  "scope": scope, "client_id": self.config.client_id}
        _atomic_write(Path(self.config.token_path), json.dumps(tokens, indent=2) + "\n")
        return tokens

    def _clear_tokens(self) -> None:
        try:
            Path(self.config.token_path).unlink(missing_ok=True)
        except OSError:
            raise OAuthError("AUTH_REQUIRED", "Spotify authorization expired; the cache could not be removed.",
                             next_step="Remove .spotify-tokens.json locally, then run --login.") from None

    def _token_request(self, fields: dict[str, str]) -> dict[str, Any]:
        credentials = f"{self.config.client_id}:{self.config.client_secret}".encode()
        request = Request(TOKEN_URL, data=urlencode(fields).encode(), method="POST", headers={
            "Authorization": "Basic " + base64.b64encode(credentials).decode(),
            "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                data = json.loads(response.read(1_000_000))
        except HTTPError as error:
            try:
                body = json.loads(error.read(1_000_000))
                provider_code = body.get("error") if isinstance(body, dict) else None
            except (ValueError, OSError):
                provider_code = None
            if provider_code == "invalid_grant":
                self._clear_tokens()
                raise OAuthError("AUTH_REQUIRED", "Spotify authorization has expired or been revoked.") from None
            if provider_code == "invalid_client":
                raise OAuthError("CONFIG_ERROR", "Spotify rejected the app credentials.",
                                 next_step="Check your developer app credentials and run --configure.") from None
            if error.code == 429:
                raise OAuthError("RATE_LIMITED", "Spotify is temporarily limiting token requests.",
                                 retryable=True, next_step="Wait a minute, then retry.") from None
            if error.code >= 500:
                raise OAuthError("SERVICE_UNAVAILABLE", "Spotify's authorization service is unavailable.",
                                 retryable=True, next_step="Retry in a moment.") from None
            raise OAuthError("TOKEN_ERROR", "Spotify rejected the token request.",
                             next_step="Check the app's redirect URI, then run --login.") from None
        except (URLError, TimeoutError, OSError):
            raise OAuthError("NETWORK_ERROR", "Could not reach Spotify's authorization service.",
                             retryable=True, next_step="Check your connection and retry.") from None
        except ValueError:
            raise OAuthError("TOKEN_ERROR", "Spotify returned an unreadable token response.",
                             retryable=True, next_step="Retry in a moment.") from None
        if not isinstance(data, dict):
            raise OAuthError("TOKEN_ERROR", "Spotify returned an unexpected token response.",
                             retryable=True, next_step="Retry in a moment.")
        return data

    def exchange_code(self, code: str) -> dict[str, Any]:
        with self._lock:
            response = self._token_request({"grant_type": "authorization_code", "code": code,
                                            "redirect_uri": self.config.redirect_uri})
            return self._save_tokens(response)

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Return a usable access token without ever opening a browser."""
        with self._lock:
            tokens = self._load_tokens()
            if tokens is None:
                raise OAuthError("AUTH_REQUIRED", "Spotify login is required.")
            try:
                expires_at = float(tokens.get("expires_at", 0))
            except (TypeError, ValueError):
                expires_at = 0
            if not force_refresh and math.isfinite(expires_at) and expires_at > time.time() + EXPIRY_SKEW:
                return tokens["access_token"]
            refresh_token = tokens.get("refresh_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise OAuthError("AUTH_REQUIRED", "No refresh token is available.")
            response = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
            return self._save_tokens(response, previous=tokens)["access_token"]


def configure() -> None:
    client_id = input("Spotify Client ID: ").strip()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            client_secret = getpass.getpass("Spotify Client Secret (hidden): ").strip()
    except getpass.GetPassWarning:
        raise OAuthError("CONFIG_ERROR", "This terminal cannot hide the client secret.",
                         next_step="Run --configure from an interactive terminal.") from None
    if not client_id or not client_secret or "\n" in client_id or "\n" in client_secret:
        raise OAuthError("CONFIG_ERROR", "Both app credentials must be nonempty, single-line values.",
                         next_step="Run --configure again with the values from your app's settings.")
    values = {"SPOTIFY_CLIENT_ID": client_id, "SPOTIFY_CLIENT_SECRET": client_secret,
              "SPOTIFY_REDIRECT_URI": REDIRECT_URI}
    _atomic_write(ENV_PATH, "".join(f"{key}={json.dumps(value)}\n" for key, value in values.items()))
    print("Saved .env with owner-only permissions. Next: python spotify_auth.py --login")


def login(oauth: SpotifyOAuth) -> None:
    state = secrets.token_urlsafe(32)
    outcome: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass  # Never log the callback URL: it contains the authorization code.

        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            status, message = 400, "Invalid callback. Return to your terminal and retry login."
            if parts.path != "/callback":
                status, message = 404, "Not found."
            elif len(query.get("state", [])) == 1 and secrets.compare_digest(query["state"][0], state):
                if query.get("error"):
                    outcome["error"] = "denied"
                    message = "Authorization was declined. You may close this tab."
                elif len(query.get("code", [])) == 1 and query["code"][0]:
                    outcome["code"] = query["code"][0]
                    status, message = 200, "Authorization received. Return to your terminal; you can close this tab."
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    class CallbackServer(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(2)
            return connection, address

        def handle_error(self, request: Any, client_address: Any) -> None:
            pass  # Suppress tracebacks containing a browser's raw request.

    try:
        server = CallbackServer(("127.0.0.1", 8888), CallbackHandler)
    except OSError:
        raise OAuthError("CALLBACK_UNAVAILABLE", "Cannot listen on 127.0.0.1:8888.",
                         next_step="Stop the other process using port 8888, then run --login again.") from None
    url = AUTHORIZE_URL + "?" + urlencode({"client_id": oauth.config.client_id,
        "response_type": "code", "redirect_uri": oauth.config.redirect_uri,
        "scope": " ".join(SCOPES), "state": state})
    with server:
        server.timeout = 1
        print("Opening Spotify authorization. Approve the playlist permissions in your browser.")
        if not webbrowser.open(url):
            print("Open this authorization link in your browser:\n" + url)
        deadline = time.monotonic() + LOGIN_TIMEOUT
        while not outcome and time.monotonic() < deadline:
            server.handle_request()
    if "error" in outcome:
        raise OAuthError("AUTH_REQUIRED", "Spotify authorization was declined.")
    if "code" not in outcome:
        raise OAuthError("AUTH_TIMEOUT", "No valid Spotify callback arrived within five minutes.")
    oauth.exchange_code(outcome["code"])
    print("Login complete. Tokens saved with owner-only permissions. Next: python spotify_auth.py --check")


def check(oauth: SpotifyOAuth) -> None:
    request = Request("https://api.spotify.com/v1/me/playlists?limit=1", headers={
        "Authorization": "Bearer " + oauth.get_access_token(), "Accept": "application/json"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            response.read(1_000_000)
    except HTTPError as error:
        if error.code == 401:
            raise OAuthError("AUTH_REQUIRED", "Spotify rejected the access token.",
                             next_step="Run --refresh and retry --check; if it fails, run --login.") from None
        if error.code == 403:
            raise OAuthError("ACCESS_DENIED", "Spotify denied playlist access.",
                             next_step="Check development-app user access and permissions, then run --login.") from None
        retryable = error.code == 429 or error.code >= 500
        raise OAuthError("RATE_LIMITED" if error.code == 429 else "API_ERROR",
                         f"Spotify returned HTTP {error.code}.", retryable,
                         "Wait a minute and retry." if retryable else "Check the developer app settings.") from None
    except (URLError, TimeoutError, OSError):
        raise OAuthError("NETWORK_ERROR", "Could not reach Spotify's playlist API.",
                         retryable=True, next_step="Check your connection and retry.") from None
    print("Spotify playlist API is accessible. This check did not modify any playlists.")


def status(oauth: SpotifyOAuth) -> None:
    tokens = oauth._load_tokens()
    if tokens is None:
        print("No saved login. Run python spotify_auth.py --login.")
        return
    try:
        expiry = float(tokens.get("expires_at", 0))
        expiry_text = datetime.fromtimestamp(expiry, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        expiry, expiry_text = 0, "unknown"
    state = "usable" if expiry > time.time() + EXPIRY_SKEW else "due for refresh"
    print(f"Cached access token: {state}. Expires at: {expiry_text}")
    print("Refresh token available: " + ("yes" if tokens.get("refresh_token") else "no"))
    print("Permissions: " + " ".join(SCOPES))
    print("Local cache only; Spotify has not been contacted.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    for name, help_text in (("configure", "Save developer app credentials locally"),
                            ("login", "Authorize through your browser"),
                            ("status", "Inspect local login state without network requests"),
                            ("check", "Make a read-only playlist API request"),
                            ("refresh", "Force token refresh without opening a browser")):
        actions.add_argument("--" + name, action="store_true", help=help_text)
    args = parser.parse_args()
    try:
        if args.configure:
            configure()
            return 0
        oauth = SpotifyOAuth(Config.from_env())
        if args.login:
            login(oauth)
        elif args.status:
            status(oauth)
        elif args.check:
            check(oauth)
        elif args.refresh:
            oauth.get_access_token(force_refresh=True)
            print("Token refresh succeeded. No browser login was needed.")
        return 0
    except OAuthError as error:
        print(json.dumps(error.as_dict()))
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Cancelled. No credentials were printed.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
