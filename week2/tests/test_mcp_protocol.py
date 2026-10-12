"""Exercise tool discovery and calls over subprocess stdio, without Spotify writes."""

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PLAYLIST_ID = "P" * 22
TRACK_URI = "spotify:track:" + "A" * 22


class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def server_session(self):
        with tempfile.TemporaryDirectory() as directory:
            self.request_log = Path(directory) / "requests.jsonl"
            env = {**os.environ, "SPOTIFY_TEST_REQUEST_LOG": str(self.request_log)}
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[str(Path(__file__).with_name("fixture_server.py"))],
                env=env,
            )
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

    def requests(self):
        if not self.request_log.exists():
            return []
        return [json.loads(line) for line in self.request_log.read_text().splitlines()]

    def result_data(self, result):
        self.assertFalse(result.isError, result.content)
        if result.structuredContent is not None:
            return result.structuredContent
        texts = [part.text for part in result.content if part.type == "text"]
        self.assertTrue(texts, "Tool did not return readable content")
        return json.loads(texts[0])

    async def test_discovery_exposes_only_three_tools_with_constraints_and_hints(self):
        async with self.server_session() as session:
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            self.assertEqual(set(tools), {
                "search_tracks", "list_my_playlists", "add_tracks_to_playlist"})
            search = tools["search_tracks"]
            playlist_list = tools["list_my_playlists"]
            write = tools["add_tracks_to_playlist"]
            self.assertTrue(search.annotations.readOnlyHint)
            self.assertTrue(playlist_list.annotations.readOnlyHint)
            self.assertFalse(write.annotations.readOnlyHint)
            self.assertFalse(write.annotations.idempotentHint)
            self.assertEqual(search.inputSchema["properties"]["limit"]["minimum"], 1)
            self.assertEqual(search.inputSchema["properties"]["limit"]["maximum"], 10)
            self.assertEqual(playlist_list.inputSchema["properties"]["limit"]["maximum"], 50)
            self.assertTrue(write.inputSchema["properties"]["dry_run"]["default"])
            self.assertEqual(write.inputSchema["properties"]["track_uris"]["maxItems"], 20)
            for tool in tools.values():
                self.assertTrue(tool.description)

    async def test_reads_return_compact_composable_identifiers_and_pagination(self):
        async with self.server_session() as session:
            tracks = self.result_data(await session.call_tool(
                "search_tracks", {"query": "Fixture Song", "limit": 2}))
            self.assertTrue(tracks["ok"])
            self.assertEqual(tracks["next_offset"], 2)
            self.assertEqual(tracks["tracks"][0]["uri"], TRACK_URI)
            self.assertEqual(tracks["tracks"][0]["artists"], ["Fixture Artist"])
            self.assertNotIn("album", tracks["tracks"][0])
            self.assertNotIn("available_markets", tracks["tracks"][0])
            playlists = self.result_data(await session.call_tool("list_my_playlists", {}))
            self.assertTrue(playlists["ok"])
            self.assertEqual(playlists["next_offset"], 20)
            self.assertEqual(playlists["playlists"][0]["id"], PLAYLIST_ID)
            self.assertEqual(playlists["playlists"][0]["owner_id"], "fixture-user")
            self.assertNotIn("images", playlists["playlists"][0])
            self.assertNotIn("description", playlists["playlists"][0])
            self.assertTrue(all(call["method"] == "GET" for call in self.requests()))

    async def test_preview_is_default_and_commit_posts_exactly_once(self):
        async with self.server_session() as session:
            arguments = {"playlist_id": PLAYLIST_ID, "track_uris": [TRACK_URI]}
            preview = self.result_data(await session.call_tool(
                "add_tracks_to_playlist", arguments))
            self.assertTrue(preview["ok"])
            self.assertTrue(preview["dry_run"])
            self.assertEqual(preview["playlist"]["id"], PLAYLIST_ID)
            self.assertEqual(preview["track_uris"], [TRACK_URI])
            self.assertEqual(preview["count"], 1)
            self.assertFalse(any(call["method"] == "POST" for call in self.requests()))
            commit = self.result_data(await session.call_tool(
                "add_tracks_to_playlist", {**arguments, "dry_run": False}))
            self.assertTrue(commit["ok"])
            self.assertFalse(commit["dry_run"])
            self.assertEqual(commit["snapshot_id"], "fixture-snapshot")
            posts = [call for call in self.requests() if call["method"] == "POST"]
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]["path"], f"/playlists/{PLAYLIST_ID}/items")
            self.assertEqual(posts[0]["body"], {"uris": [TRACK_URI]})

    async def test_bad_arguments_are_protocol_errors_without_api_requests(self):
        async with self.server_session() as session:
            invalid_calls = [
                ("search_tracks", {"query": "   "}),
                ("search_tracks", {"query": "song", "limit": 11}),
                ("search_tracks", {"query": "song", "offset": -1}),
                ("search_tracks", {"query": "song", "offset": 1001}),
                ("list_my_playlists", {"limit": 51}),
                ("add_tracks_to_playlist", {"playlist_id": "not-an-id",
                                           "track_uris": [TRACK_URI]}),
                ("add_tracks_to_playlist", {"playlist_id": PLAYLIST_ID,
                                           "track_uris": ["https://open.spotify.com/track/abc"]}),
                ("add_tracks_to_playlist", {"playlist_id": PLAYLIST_ID,
                                           "track_uris": []}),
                ("add_tracks_to_playlist", {"playlist_id": PLAYLIST_ID,
                                           "track_uris": [TRACK_URI] * 21}),
            ]
            for name, arguments in invalid_calls:
                with self.subTest(tool=name, arguments=arguments):
                    result = await session.call_tool(name, arguments)
                    self.assertTrue(result.isError, result)
            self.assertEqual(self.requests(), [])
            recovered = self.result_data(await session.call_tool("list_my_playlists", {}))
            self.assertTrue(recovered["ok"])

    async def test_playlist_restrictions_return_actionable_errors_and_recover(self):
        async with self.server_session() as session:
            for playlist_id, expected_code in [("U" * 22, "PUBLIC_PLAYLIST"),
                                              ("O" * 22, "NOT_PLAYLIST_OWNER")]:
                result = self.result_data(await session.call_tool("add_tracks_to_playlist", {
                    "playlist_id": playlist_id, "track_uris": [TRACK_URI], "dry_run": False}))
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["code"], expected_code)
                self.assertFalse(result["error"]["retryable"])
                self.assertTrue(result["error"]["message"])
                self.assertTrue(result["error"]["next_step"])
            self.assertFalse(any(call["method"] == "POST" for call in self.requests()))
            recovered = self.result_data(await session.call_tool("search_tracks", {"query": "song"}))
            self.assertTrue(recovered["ok"])

    async def test_api_errors_preserve_recovery_guidance_over_the_protocol(self):
        async with self.server_session() as session:
            limited = self.result_data(await session.call_tool(
                "search_tracks", {"query": "rate-limit"}))
            self.assertFalse(limited["ok"])
            self.assertEqual(limited["error"]["code"], "RATE_LIMITED")
            self.assertTrue(limited["error"]["retryable"])
            self.assertEqual(limited["error"]["retry_after_seconds"], 30)
            self.assertTrue(limited["error"]["next_step"])
            missing = self.result_data(await session.call_tool("add_tracks_to_playlist", {
                "playlist_id": "N" * 22, "track_uris": [TRACK_URI]}))
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["error"]["code"], "NOT_FOUND")
            self.assertFalse(missing["error"]["retryable"])
            self.assertFalse(any(call["method"] == "POST" for call in self.requests()))
            recovered = self.result_data(await session.call_tool("list_my_playlists", {}))
            self.assertTrue(recovered["ok"])


if __name__ == "__main__":
    unittest.main()
