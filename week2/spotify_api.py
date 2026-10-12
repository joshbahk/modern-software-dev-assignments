"""Small, secret-safe Spotify transport shared by the three MCP tools."""

from __future__ import annotations

from http.client import HTTPException
import json
import re
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from spotify_auth import Config, OAuthError, SpotifyOAuth


API_BASE = "https://api.spotify.com/v1"
REQUEST_TIMEOUT = 15


class SpotifyAPIError(Exception):
    """Safe, actionable fields suitable for returning to an MCP client."""

    def __init__(self, code: str, message: str, retryable: bool = False,
                 next_step: str = "Check the request and try again.",
                 retry_after_seconds: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.next_step = next_step
        self.retry_after_seconds = retry_after_seconds

    def as_dict(self) -> dict[str, Any]:
        fields = {"code": self.code, "message": self.message,
                  "retryable": self.retryable, "next_step": self.next_step}
        if self.retry_after_seconds is not None:
            fields["retry_after_seconds"] = self.retry_after_seconds
        return fields


def _uncertain_write() -> SpotifyAPIError:
    return SpotifyAPIError(
        "WRITE_OUTCOME_UNKNOWN", "Spotify may have accepted the playlist change.",
        next_step="Inspect the playlist in Spotify before repeating this write, to avoid duplicates.")


def _http_error(error: HTTPError, writing: bool) -> SpotifyAPIError:
    if error.code >= 500:
        if writing:
            return _uncertain_write()
        return SpotifyAPIError("SERVICE_UNAVAILABLE", "Spotify is temporarily unavailable.",
                               True, "Wait briefly, then retry the read request.")
    if error.code == 429:
        try:
            payload = json.loads(error.read(1_000_000))
            detail = payload.get("error", {}) if isinstance(payload, dict) else {}
            reason = detail.get("reason") if isinstance(detail, dict) else None
        except (ValueError, OSError, HTTPException):
            reason = None
        if reason == "QUOTA_EXCEEDED":
            return SpotifyAPIError(
                "QUOTA_EXCEEDED", "The Spotify app's request quota is exhausted.",
                next_step="Check the app quota in Spotify's developer dashboard before retrying.")
        try:
            delay = max(0, int(error.headers.get("Retry-After", "")))
        except (AttributeError, ValueError, TypeError):
            delay = None
        return SpotifyAPIError(
            "RATE_LIMITED", "Spotify is temporarily limiting requests.", True,
            f"Wait at least {delay} seconds before retrying." if delay is not None
            else "Wait a minute before retrying.", delay)
    errors = {
        400: ("INVALID_REQUEST", "Spotify rejected the request parameters.",
              "Check the query, playlist ID, and track URIs, then retry."),
        401: ("AUTH_REQUIRED", "Spotify authorization was rejected after refreshing.",
              "Run python spotify_auth.py --login, then retry."),
        403: ("FORBIDDEN", "Spotify denied access to this operation.",
              "Check playlist ownership, granted permissions, and the app's allowed users and Premium status."),
        404: ("NOT_FOUND", "Spotify could not find an accessible resource.",
              "Use list_my_playlists or search_tracks to obtain a current accessible ID."),
    }
    code, message, action = errors.get(error.code, (
        "UPSTREAM_ERROR", "Spotify rejected the request.",
        "Check the request and Spotify's service status before trying again."))
    return SpotifyAPIError(code, message, next_step=action)


class SpotifyAPI:
    def __init__(self, auth: SpotifyOAuth | None = None):
        # Discovery never reads credentials or makes an API request.
        self.auth = auth
        self._auth_lock = threading.Lock()

    def _token(self, force_refresh: bool = False) -> str:
        try:
            # All concurrent tool calls must share the OAuth object's refresh lock.
            with self._auth_lock:
                if self.auth is None:
                    self.auth = SpotifyOAuth(Config.from_env())
            return self.auth.get_access_token(force_refresh=force_refresh)
        except OAuthError as error:
            raise SpotifyAPIError(error.code, error.message, error.retryable,
                                  error.next_step) from None

    def request(self, method: str, path: str, *,
                params: dict | None = None, body: dict | None = None) -> dict:
        """Send one API request; only an explicit 401 permits one auth retry."""
        if (not isinstance(path, str) or not re.fullmatch(r"/[A-Za-z0-9_/-]+", path)
                or "//" in path):
            raise SpotifyAPIError("INVALID_REQUEST", "An API-relative resource path is required.")
        method = method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise SpotifyAPIError("INVALID_REQUEST", "This HTTP method is not supported.")
        writing = method != "GET"
        url = API_BASE + path
        if params:
            url += "?" + urlencode(params)
        data = json.dumps(body, allow_nan=False).encode("utf-8") if body is not None else None
        for attempt in range(2):
            token = self._token(force_refresh=attempt == 1)
            request = Request(url, method=method, data=data, headers={
                "Authorization": f"Bearer {token}", "Accept": "application/json",
                "Content-Type": "application/json",
            })
            try:
                with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                    result = json.loads(response.read(1_000_000))
            except HTTPError as error:
                try:
                    if error.code == 401 and attempt == 0:
                        continue
                    failure = _http_error(error, writing)
                finally:
                    error.close()
                raise failure from None
            except (URLError, TimeoutError, OSError, HTTPException):
                if writing:
                    raise _uncertain_write() from None
                raise SpotifyAPIError("NETWORK_ERROR", "Could not reach Spotify.", True,
                                      "Check your connection and retry the read request.") from None
            except ValueError:
                if writing:
                    raise _uncertain_write() from None
                raise SpotifyAPIError("INVALID_RESPONSE", "Spotify returned unreadable data.", True,
                                      "Wait briefly, then retry the read request.") from None
            if not isinstance(result, dict):
                if writing:
                    raise _uncertain_write()
                raise SpotifyAPIError("INVALID_RESPONSE", "Spotify returned an unexpected data shape.",
                                      True, "Wait briefly, then retry the read request.")
            return result
        raise SpotifyAPIError("AUTH_REQUIRED", "Spotify login is required.",
                              next_step="Run python spotify_auth.py --login, then retry.")
