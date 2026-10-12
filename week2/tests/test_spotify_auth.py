"""OAuth lifecycle tests with mocked Spotify responses; no real account needed."""

import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spotify_auth import Config, OAuthError, SpotifyOAuth


class OAuthLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / "tokens.json"
        self.config = Config(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://127.0.0.1:8888/callback",
            token_path=self.cache,
        )
        self.auth = SpotifyOAuth(self.config)

    def cached_token(self, **overrides):
        token = {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": time.time() + 3600,
            "client_id": "test-client",
            "scope": "playlist-read-private playlist-modify-private",
            **overrides,
        }
        self.cache.write_text(json.dumps(token))

    def test_cached_token_avoids_network_and_browser(self):
        self.cached_token()
        with patch.object(self.auth, "_token_request") as request, patch(
            "webbrowser.open"
        ) as browser:
            self.assertEqual(self.auth.get_access_token(), "old-access")
        request.assert_not_called()
        browser.assert_not_called()

    def test_expiry_refreshes_and_persists_rotated_refresh_token(self):
        self.cached_token(expires_at=0)
        response = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }
        with patch.object(self.auth, "_token_request", return_value=response) as request:
            self.assertEqual(self.auth.get_access_token(), "new-access")
        request.assert_called_once_with(
            {"grant_type": "refresh_token", "refresh_token": "old-refresh"}
        )
        saved = json.loads(self.cache.read_text())
        self.assertEqual(saved["refresh_token"], "new-refresh")
        self.assertGreater(saved["expires_at"], time.time() + 3500)
        self.assertEqual(stat.S_IMODE(self.cache.stat().st_mode), 0o600)

    def test_refresh_preserves_old_refresh_token_when_omitted(self):
        self.cached_token(expires_at=0)
        with patch.object(
            self.auth, "_token_request", return_value={"access_token": "new", "expires_in": 3600}
        ):
            self.auth.get_access_token()
        self.assertEqual(json.loads(self.cache.read_text())["refresh_token"], "old-refresh")

    def test_force_refresh_exercises_refresh_before_natural_expiry(self):
        self.cached_token()
        with patch.object(
            self.auth, "_token_request", return_value={"access_token": "new", "expires_in": 3600}
        ) as request:
            self.assertEqual(self.auth.get_access_token(force_refresh=True), "new")
        request.assert_called_once()

    def test_missing_authorization_returns_error_without_opening_browser(self):
        with patch("webbrowser.open") as browser:
            with self.assertRaises(OAuthError) as caught:
                self.auth.get_access_token()
        self.assertEqual(caught.exception.code, "AUTH_REQUIRED")
        self.assertFalse(caught.exception.retryable)
        browser.assert_not_called()

    def test_cached_token_from_another_app_is_rejected(self):
        self.cached_token(client_id="another-client")
        with patch.object(self.auth, "_token_request") as request:
            with self.assertRaises(OAuthError):
                self.auth.get_access_token()
        request.assert_not_called()

    def test_code_is_exchanged_and_tokens_are_saved(self):
        response = {
            "access_token": "initial-access",
            "refresh_token": "initial-refresh",
            "expires_in": 3600,
            "scope": "playlist-read-private playlist-modify-private",
        }
        with patch.object(self.auth, "_token_request", return_value=response) as request:
            self.auth.exchange_code("test-authorization-code")
        request.assert_called_once_with(
            {
                "grant_type": "authorization_code",
                "code": "test-authorization-code",
                "redirect_uri": self.config.redirect_uri,
            }
        )
        self.assertEqual(self.auth.get_access_token(), "initial-access")
        self.assertEqual(stat.S_IMODE(self.cache.stat().st_mode), 0o600)

    def test_revoked_refresh_token_is_cleared_without_browser_or_secret_output(self):
        self.cached_token(expires_at=0)
        error = HTTPError(
            "https://accounts.spotify.com/api/token", 400, "Bad request", {},
            io.BytesIO(b'{"error":"invalid_grant","error_description":"private-value"}'),
        )
        with patch("spotify_auth.urlopen", side_effect=error), patch("webbrowser.open") as browser:
            with self.assertRaises(OAuthError) as caught:
                self.auth.get_access_token()
        self.assertEqual(caught.exception.code, "AUTH_REQUIRED")
        self.assertFalse(caught.exception.retryable)
        self.assertFalse(self.cache.exists())
        self.assertNotIn("private-value", json.dumps(caught.exception.as_dict()))
        browser.assert_not_called()

    def test_malformed_token_type_returns_structured_error(self):
        with self.assertRaises(OAuthError):
            self.auth._save_tokens(
                {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600,
                 "token_type": None}
            )

    def test_incomplete_granted_scopes_are_rejected(self):
        with self.assertRaises(OAuthError):
            self.auth._save_tokens(
                {
                    "access_token": "initial-access",
                    "refresh_token": "initial-refresh",
                    "expires_in": 3600,
                    "scope": "playlist-read-private",
                }
            )


if __name__ == "__main__":
    unittest.main()
