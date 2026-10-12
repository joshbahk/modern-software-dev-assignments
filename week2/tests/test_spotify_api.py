"""Transport tests use fake credentials and never contact Spotify."""

import io
import json
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from spotify_api import SpotifyAPI, SpotifyAPIError
from spotify_auth import OAuthError


def response(payload):
    result = MagicMock()
    result.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return result


def http_error(status, payload=None, headers=None):
    return HTTPError("https://api.spotify.com/v1/me", status, "private upstream text",
                     headers or {}, io.BytesIO(json.dumps(payload or {}).encode()))


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.auth = MagicMock()
        self.auth.get_access_token.return_value = "fake-token"
        self.api = SpotifyAPI(self.auth)

    @patch("spotify_api.Config.from_env")
    @patch("spotify_api.urlopen")
    def test_init_does_not_load_credentials_or_connect(self, opened, config):
        SpotifyAPI()
        config.assert_not_called()
        opened.assert_not_called()

    @patch("spotify_api.SpotifyOAuth")
    @patch("spotify_api.Config.from_env")
    def test_concurrent_initial_calls_share_one_oauth_instance(self, config, oauth):
        # Slow configuration reading exposes overlapping first tool calls.
        config.side_effect = lambda: time.sleep(0.02)
        oauth.return_value.get_access_token.return_value = "fake-token"
        api = SpotifyAPI()
        barrier = threading.Barrier(4)

        def first_call(_):
            barrier.wait(timeout=2)
            return api._token()

        with ThreadPoolExecutor(max_workers=4) as pool:
            tokens = list(pool.map(first_call, range(4)))
        self.assertEqual(tokens, ["fake-token"] * 4)
        config.assert_called_once()
        oauth.assert_called_once()

    @patch("spotify_api.urlopen")
    def test_401_refreshes_once_and_retries(self, opened):
        opened.side_effect = [http_error(401), response({"items": []})]
        self.assertEqual(self.api.request("GET", "/me/playlists"), {"items": []})
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(self.auth.get_access_token.call_args_list[0].kwargs,
                         {"force_refresh": False})
        self.assertEqual(self.auth.get_access_token.call_args_list[1].kwargs,
                         {"force_refresh": True})

    @patch("spotify_api.urlopen")
    def test_second_401_requires_login(self, opened):
        opened.side_effect = [http_error(401), http_error(401)]
        with self.assertRaises(SpotifyAPIError) as raised:
            self.api.request("GET", "/me")
        self.assertEqual(raised.exception.code, "AUTH_REQUIRED")
        self.assertEqual(opened.call_count, 2)

    @patch("spotify_api.urlopen")
    def test_429_preserves_retry_delay(self, opened):
        opened.side_effect = http_error(429, headers={"Retry-After": "37"})
        with self.assertRaises(SpotifyAPIError) as raised:
            self.api.request("GET", "/search", params={"q": "a b"})
        result = raised.exception.as_dict()
        self.assertEqual(result["code"], "RATE_LIMITED")
        self.assertEqual(result["retry_after_seconds"], 37)
        self.assertTrue(result["retryable"])
        self.assertEqual(opened.call_count, 1)

    @patch("spotify_api.urlopen")
    def test_quota_exhaustion_is_distinct(self, opened):
        opened.side_effect = http_error(429, {"error": {"reason": "QUOTA_EXCEEDED"}})
        with self.assertRaises(SpotifyAPIError) as raised:
            self.api.request("GET", "/search")
        self.assertEqual(raised.exception.code, "QUOTA_EXCEEDED")
        self.assertFalse(raised.exception.retryable)

    @patch("spotify_api.urlopen")
    def test_forbidden_never_exposes_provider_text(self, opened):
        opened.side_effect = http_error(403, {"error": {"message": "secret-token"}})
        with self.assertRaises(SpotifyAPIError) as raised:
            self.api.request("GET", "/me")
        self.assertEqual(raised.exception.code, "FORBIDDEN")
        self.assertFalse(raised.exception.retryable)
        self.assertNotIn("secret-token", json.dumps(raised.exception.as_dict()))
        self.assertNotIn("private upstream text", str(raised.exception))

    @patch("spotify_api.urlopen")
    def test_ambiguous_writes_are_never_retried(self, opened):
        for failure in (URLError("secret network detail"), http_error(503)):
            with self.subTest(failure=type(failure).__name__):
                opened.reset_mock()
                opened.side_effect = failure
                with self.assertRaises(SpotifyAPIError) as raised:
                    self.api.request("POST", "/playlists/test/items", body={"uris": []})
                self.assertEqual(raised.exception.code, "WRITE_OUTCOME_UNKNOWN")
                self.assertFalse(raised.exception.retryable)
                self.assertEqual(opened.call_count, 1)

    @patch("spotify_api.urlopen")
    def test_network_read_is_retryable_but_not_automatically_retried(self, opened):
        opened.side_effect = URLError("private network detail")
        with self.assertRaises(SpotifyAPIError) as raised:
            self.api.request("GET", "/me")
        self.assertEqual(raised.exception.code, "NETWORK_ERROR")
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(opened.call_count, 1)

    @patch("spotify_api.urlopen")
    def test_arbitrary_urls_rejected_before_auth(self, opened):
        for path in ("https://other.example/me", "//other.example/me", "/../me", "/me?token=x"):
            with self.subTest(path=path), self.assertRaises(SpotifyAPIError):
                self.api.request("GET", path)
        self.auth.get_access_token.assert_not_called()
        opened.assert_not_called()

    @patch("spotify_api.urlopen")
    def test_oauth_errors_keep_actionable_fields(self, opened):
        self.auth.get_access_token.side_effect = OAuthError("AUTH_REQUIRED", "Login required.")
        with self.assertRaises(SpotifyAPIError) as raised:
            self.api.request("GET", "/me")
        self.assertEqual(raised.exception.code, "AUTH_REQUIRED")
        self.assertIn("--login", raised.exception.next_step)
        opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
