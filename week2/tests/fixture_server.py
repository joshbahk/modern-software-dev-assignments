"""Local-only Spotify fixture for the real MCP stdio integration tests."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import build_server
from spotify_api import SpotifyAPIError


PLAYLIST_ID = "P" * 22
PUBLIC_PLAYLIST_ID = "U" * 22
FOREIGN_PLAYLIST_ID = "O" * 22
TRACK_URI = "spotify:track:" + "A" * 22


class FakeSpotifyAPI:
    def request(self, method, path, params=None, body=None):
        # This audit file is confined to the fixture, never production code.
        with Path(os.environ["SPOTIFY_TEST_REQUEST_LOG"]).open("a") as log:
            log.write(json.dumps({"method": method, "path": path,
                                  "params": params, "body": body}) + "\n")
        if method == "GET" and path == "/search":
            if params.get("q") == "rate-limit":
                raise SpotifyAPIError(
                    code="RATE_LIMITED", message="Spotify has temporarily limited requests.",
                    retryable=True, next_step="Wait 30 seconds before retrying.",
                    retry_after_seconds=30,
                )
            return {"tracks": {"items": [{
                "uri": TRACK_URI,
                "name": "Fixture Song",
                "artists": [{"name": "Fixture Artist", "id": "unused"}],
                "duration_ms": 180000,
                "external_urls": {"spotify": "https://open.spotify.com/track/" + "A" * 22},
                "album": {"images": [{"url": "unused-image"}]},
                "available_markets": ["US", "GB"],
            }], "next": "https://api.spotify.com/v1/search?offset=2"}}
        if method == "GET" and path == "/me/playlists":
            return {"items": [self.playlist(PLAYLIST_ID)],
                    "next": "https://api.spotify.com/v1/me/playlists?offset=20"}
        if method == "GET" and path == "/me":
            return {"id": "fixture-user"}
        if method == "GET" and path.startswith("/playlists/"):
            if path.rsplit("/", 1)[-1] == "N" * 22:
                raise SpotifyAPIError(
                    code="NOT_FOUND", message="Playlist was not found.",
                    retryable=False, next_step="Use an ID returned by list_my_playlists.",
                )
            return self.playlist(path.rsplit("/", 1)[-1])
        if method == "POST" and path == f"/playlists/{PLAYLIST_ID}/items":
            return {"snapshot_id": "fixture-snapshot"}
        raise AssertionError(f"Unexpected fixture request: {method} {path}")

    @staticmethod
    def playlist(playlist_id):
        return {"id": playlist_id,
                "name": "MCP Test",
                "public": playlist_id == PUBLIC_PLAYLIST_ID,
                "owner": {"id": "someone-else" if playlist_id == FOREIGN_PLAYLIST_ID
                          else "fixture-user"},
                "external_urls": {"spotify": f"https://open.spotify.com/playlist/{playlist_id}"},
                "images": [{"url": "unused-image"}],
                "description": "A raw response field that tools should omit."}


if __name__ == "__main__":
    build_server(FakeSpotifyAPI()).run(
        transport="stdio", show_banner=False, log_level="CRITICAL"
    )
