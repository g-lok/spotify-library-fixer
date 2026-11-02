# AGENTS.md — spotify-fix Instructions

## Project Overview

`spotify-fix` is a Python CLI utility managed via Poetry and mise. It cleans
up Spotify Liked Songs, Liked Albums, and Playlists using Zotify credentials
and `librespot`.

## POSIX Compliance Mandate

- Standard streams: Log messages go to `stderr`, summaries to `stdout`.
- Shell redirection: Never force hardcoded file logging inside CLI code; allow
  `> file 2>&1` shell redirection.
- Exact `-o`/`--output` semantics: Write to exact specified path without
  modifying or appending suffixes.

## Architecture

- `src/spotify_fix/auth.py`: Zotify credentials discovery
  (`api_credentials.json`, `credentials.json`), PKCE OAuth login server
  (`--login`), token refresh.
- `src/spotify_fix/client.py`: Spotify Web API wrapper with rate-limiting
  retries, batching (50 items/chunk), 2-stage search.
- `src/spotify_fix/cleaner.py`: Reuploaded track/album/playlist relinking,
  complete album rollup, unavailable items reporting.
- `src/spotify_fix/cli.py`: POSIX argument parsing and CLI runner.

## Testing & Quality Assurance

- Always run `poetry run pytest` before committing.
- Run `npx markdownlint-cli2 <file.md>` on documentation files.
