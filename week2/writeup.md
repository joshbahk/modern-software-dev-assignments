# Week 2 Write-up

## Part I: The Server

**API chosen**, and why:
> I chose Spotify because I use it regularly, but I usually just end up shuffling my liked songs, without much customization. I've never been able to really get properly into the daylists or other Spotify recommendation features, and so I think it would be interesting to connect an AI agent to my Spotify to make better custom playlists. Also, it is something that I can feasibly meet the assignment requirements with.

**How to run it** (one command):
```
.venv/bin/python server.py
```

| Tool | What it does | Read/Write | Composes with |
|---|---|---|---|
| search_tracks | Finds songs and returns track info | Read | Returns URIs accepted by add_tracks_to_playlist |
| list_my_playlists | Lists playlists with their IDs | Read | Returns IDs accepted by add_tracks_to_playlist |
| add_tracks_to_playlist | Previews or appends tracks to an owned private playlist | Write, but preview by default | Consumes playlist IDs and track URIs from the readers |


## Part II: Agent Ergonomics

For each, point at the code (`file:line`) and say what it buys.

| Decision | Where | Why |
|---|---|---|
| Schema-level constraint | `server.py:12`, `server.py:14` | The schema requires track URIs in the `spotify:track:...` format and limits search results to between 1 and 10. This catches things like passing a song's web URL or asking for too many results before making a request to Spotify. |
| Output shaping (fields kept vs. dropped) | `server.py:72`, `server.py:97` | Search results keep the song name, artists, duration, URI, and URL. Playlist results keep the name, ID, owner ID, public/private status, and URL. Things like album artwork and playlist images are dropped because they don't help the agent find the right IDs or add a song. |
| Structured errors (retry vs. don't-retry) | `spotify_api.py:34`, `spotify_api.py:48` | Errors include a code, a message, whether retrying makes sense, and a next step. For example, a rate limit tells the agent to wait, including the delay if Spotify provides one. A missing playlist tells it to look up a valid ID instead of making the same request again. |
| Docstring that chains tools together | `server.py:113` | The write tool's docstring says that the playlist ID comes from `list_my_playlists`, and the track URIs come from `search_tracks`. This matters because a Spotify URL, a bare ID, and a track URI are different things, even though they might all look like ways to identify the same song. |
| Brake on the write tool | `server.py:111`, `server.py:145` | With the default `dry_run=true`, the tool checks the playlist and shows what would be added. The request that actually adds tracks only happens when it is false. The server instructions tell the agent to show the preview and wait for approval before doing this. |

**One thing you changed after watching the agent misuse a tool:**
> I asked Claude to find 25 distinct songs by Frank Ocean and preview adding them to MCP Test, without duplicates or any actual changes to the playlist. It searched for `artist:Frank Ocean` with `limit=10` and `offset=0`. The result had nine tracks and `next_offset: null`, but Claude still guessed `offset=10` for the next call. That request actually succeeded, so the demo did not fail, but the agent had ignored the pagination information it was given. A separate check of Spotify's response also returned `total: 9` and `next: null`, so this was not the server dropping a next-page link. I clarified the server instructions and search docstring (`server.py:45`, `server.py:64`): stop paging a query when the next offset is null, and try a different query if more songs are needed. In a fresh session with the same prompt, Claude used `Frank Ocean` as its initial query. When that query reached a null next offset, it switched to `Frank Ocean Blonde` instead of guessing another offset, and eventually completed previews of 20 and five tracks. The initial queries were different, so this is not an exact before-and-after comparison, but the second run did follow the stopping rule. Both runs are captured in [demo-transcript.md](demo-transcript.md).


## Part III: OAuth

**Flow**: how a token is obtained, cached, and refreshed:
> I first created a Spotify developer app and set its callback address to `http://127.0.0.1:8888/callback`. Then, I ran `python3 spotify_auth.py --login`, which opened Spotify in the browser and asked me to approve the playlist permissions. Spotify sends back a temporary authorization code, and the helper checks the state value before exchanging the code for an access token and a refresh token. These are saved locally with an expiry time, so I don't have to log in for every tool call. When the access token is within a minute of expiring, the helper uses the refresh token to get a new one. I also ran `--refresh` followed by `--check`, which confirmed that refreshing worked without another browser login.

**Scopes requested**, and why each is necessary:
> The two scopes are `playlist-read-private` and `playlist-modify-private`. The first lets the server find and read my private playlists, while the second lets it add songs to them. I kept the write tool limited to private playlists that I own, since that is enough for the workflow I wanted to test. It doesn't need access to playback controls or permission to edit public playlists.

**Secrets**: what's in env, what's gitignored:
> The Client ID, Client Secret, and callback address are stored in my local `.env` file, and the helper can also read them directly from environment variables. They aren't written into the server code. The access and refresh tokens are saved separately in `.spotify-tokens.json`. Both files are gitignored, along with a real `.mcp.json` if I use one. The credential and token files have permissions that only allow my account to read and write them. The `.env.example` and `.mcp.json.example` files contain configuration placeholders, without the actual credentials or tokens.

**Token dies mid-session**: what the agent sees:
> If the access token expires normally, the helper refreshes it without opening a browser. If Spotify rejects an API request with a 401, the server also tries refreshing once before repeating the request. However, if the refresh token has expired or been revoked, the agent gets an `AUTH_REQUIRED` error, with `retryable` set to false and instructions to run the login command separately. This gives it a reason to stop retrying instead of repeatedly making requests that won't work. The revoked-token case is covered by a test with a fake Spotify response; I haven't revoked my actual login to demonstrate it live.


## Part IV: Integration

**Registration config** (`.mcp.json.example`) and the client you used:
> I am using Claude Code. The server is registered locally for the `week2` folder under the name `spotify-week2`, and `claude mcp get spotify-week2` reported that it was connected. It starts the virtual environment's Python interpreter with `server.py` as the argument, using absolute paths so it can find both files. The `.mcp.json.example` file shows the same stdio setup with placeholder paths. The working registration is stored in Claude Code's local configuration, and the server loads its Spotify credentials separately from `.env`.

**End-to-end transcript**: the prompt, the tools that fired with their arguments, the result:
> I used Claude Code to test the Spotify tools and saved the conversation. For the first prompt, Claude searched for Nights and listed my playlists, then used the URI and playlist ID from those results to preview the addition. It returned the song and destination and stopped before adding anything. The excerpts below group each call with its result and leave out the unrelated songs and playlists; the captured conversation is in [demo-transcript.md](demo-transcript.md).

```text
Prompt:
Find Nights by Frank Ocean and preview adding it to my private playlist MCP Test. Show me the song and playlist before changing anything. Use the Spotify MCP tools for this.

Tool: mcp__spotify-week2__search_tracks
Arguments: {"query": "Nights Frank Ocean", "limit": 5}
Result excerpt (4 other track results omitted):
{"ok": true, "tracks": [{"uri": "spotify:track:7eqoqGkKwgOaWNNHx90uEZ", "name": "Nights", "artists": ["Frank Ocean"], "duration_ms": 307151, "url": "https://open.spotify.com/track/7eqoqGkKwgOaWNNHx90uEZ"}], "next_offset": 5}

Tool: mcp__spotify-week2__list_my_playlists
Arguments: {"limit": 50}
Result excerpt (9 unrelated playlists omitted):
{"ok": true, "playlists": [{"id": "5xeb8TBFgOW7vwYw09C3f7", "name": "MCP Test", "owner_id": "31bpuryrrfvgihrqpox5futt6iga", "public": false, "url": "https://open.spotify.com/playlist/5xeb8TBFgOW7vwYw09C3f7"}], "next_offset": null}

Tool: mcp__spotify-week2__add_tracks_to_playlist
Arguments: {"playlist_id": "5xeb8TBFgOW7vwYw09C3f7", "track_uris": ["spotify:track:7eqoqGkKwgOaWNNHx90uEZ"], "dry_run": true}
Result:
{"ok": true, "dry_run": true, "playlist": {"id": "5xeb8TBFgOW7vwYw09C3f7", "name": "MCP Test", "url": "https://open.spotify.com/playlist/5xeb8TBFgOW7vwYw09C3f7"}, "track_uris": ["spotify:track:7eqoqGkKwgOaWNNHx90uEZ"], "count": 1}

Claude's final response (excerpt):
Preview complete — **nothing has been added yet.**
The dry run confirmed the playlist is writable and that 1 track would be appended to the end.
```

> Later, I asked Claude to add just Nights once. Claude made one write call, and Spotify returned a new snapshot ID. A separate read of the playlist confirmed that it contained exactly one track, Nights. The 25-song selection stayed as a preview.

```text
Prompt:
Go ahead and add the original single-song preview of Nights by Frank Ocean to MCP Test once. Only add spotify:track:7eqoqGkKwgOaWNNHx90uEZ to playlist 5xeb8TBFgOW7vwYw09C3f7. Leave the 25-song selection as a preview.

Tool: mcp__spotify-week2__add_tracks_to_playlist
Arguments: {"playlist_id": "5xeb8TBFgOW7vwYw09C3f7", "track_uris": ["spotify:track:7eqoqGkKwgOaWNNHx90uEZ"], "dry_run": false}
Result:
{"ok": true, "dry_run": false, "playlist": {"id": "5xeb8TBFgOW7vwYw09C3f7", "name": "MCP Test", "url": "https://open.spotify.com/playlist/5xeb8TBFgOW7vwYw09C3f7"}, "track_uris": ["spotify:track:7eqoqGkKwgOaWNNHx90uEZ"], "count": 1, "snapshot_id": "AAAAAwe5s0w3cpRTJMQHc0Ba5eOHyiOh"}

Claude's final response (excerpt):
Added. **Nights** by Frank Ocean is now in **MCP Test**.

Separate read after the write:
{"playlist": "MCP Test", "playlist_id": "5xeb8TBFgOW7vwYw09C3f7", "total": 1, "next": null, "tracks": [{"name": "Nights", "uri": "spotify:track:7eqoqGkKwgOaWNNHx90uEZ"}]}
```

**A failure, handled**: what you provoked, what the agent saw, what it did next:
> For the error-handling prompt, I gave Claude a deliberately invalid playlist ID. It was the right length to pass the schema check, but Spotify returned `NOT_FOUND`. Claude then followed the error's instructions by listing my playlists again and retrying the preview with the ID for MCP Test. This succeeded without changing the playlist. The prompt explicitly asked Claude to recover, so this shows that it could follow the recovery instructions when asked.

```text
Prompt:
Now test the error handling. Preview that same song with playlist ID 0000000000000000000000, which is deliberately invalid. If it fails, use the error's instructions to find MCP Test and try the preview there. Don't add anything.

Tool: mcp__spotify-week2__add_tracks_to_playlist
Arguments: {"playlist_id": "0000000000000000000000", "track_uris": ["spotify:track:7eqoqGkKwgOaWNNHx90uEZ"], "dry_run": true}
Result:
{"ok": false, "error": {"code": "NOT_FOUND", "message": "Spotify could not find an accessible resource.", "retryable": false, "next_step": "Use list_my_playlists or search_tracks to obtain a current accessible ID."}}

Tool: mcp__spotify-week2__list_my_playlists
Arguments: {"limit": 50}
Result excerpt (9 unrelated playlists omitted):
{"ok": true, "playlists": [{"id": "5xeb8TBFgOW7vwYw09C3f7", "name": "MCP Test", "owner_id": "31bpuryrrfvgihrqpox5futt6iga", "public": false, "url": "https://open.spotify.com/playlist/5xeb8TBFgOW7vwYw09C3f7"}], "next_offset": null}

Tool: mcp__spotify-week2__add_tracks_to_playlist
Arguments: {"playlist_id": "5xeb8TBFgOW7vwYw09C3f7", "track_uris": ["spotify:track:7eqoqGkKwgOaWNNHx90uEZ"], "dry_run": true}
Result:
{"ok": true, "dry_run": true, "playlist": {"id": "5xeb8TBFgOW7vwYw09C3f7", "name": "MCP Test", "url": "https://open.spotify.com/playlist/5xeb8TBFgOW7vwYw09C3f7"}, "track_uris": ["spotify:track:7eqoqGkKwgOaWNNHx90uEZ"], "count": 1}

Claude's final response (excerpt):
Nothing was added. All three calls were reads only — your playlist is unchanged, and the pending addition from before is still uncommitted.
```

**Protocol-level test**: what it covers and how to run it:
> The tests in `tests/test_mcp_protocol.py` start a separate server process and communicate with it over stdio using an MCP client. They discover the tools and call them through the protocol, so they also check that the schemas and returned results work outside a direct Python function call. The tests cover invalid arguments, the fields kept in results, pagination, previewing without writing, an explicit write, and recovering from errors within the same session. Spotify itself is replaced with a fake API for these tests, so the write test doesn't change any real playlists. The full suite passed 27 tests, including six protocol tests. To run them from `week2`, use `.venv/bin/python -m unittest discover -s tests -v`.


## Submission
1. `Command (⌘) + F` for `TODO`. No results means you're done.
2. Confirm no tokens, client secrets, cached token file, or real `.mcp.json` are committed.
3. Push all changes to your remote repository and submit via Gradescope.
4. Clean up (optional): remove the server from your agent config, delete your cached token, and revoke the OAuth app's access.
