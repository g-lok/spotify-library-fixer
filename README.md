# spotify-fix

Utility tool to clean up Spotify Liked Songs, Liked Albums, and Playlists using
Zotify credentials and `librespot`.

## Features

- **Reuploaded Content Fixer**: Scans liked tracks, albums, and playlists for
  unplayable/deleted items. Searches Spotify for active reuploaded versions,
  relinking them under new IDs.
- **Album Rollup**: Automatically detects when all tracks of an album are
  liked, adding the album to Liked Albums and removing individual track likes.
- **Unavailable Content Report**: Generates a detailed JSON report of content
  no longer available on Spotify so you can source it manually.
- **Zotify Credentials Integration**: Automatically reuses existing
  `api_credentials.json` and `credentials.json` from Zotify
  (`~/.config/zotify/`). No re-authentication required.

## Installation & Setup

Managed via Poetry and mise:

```bash
poetry install
```

## Usage

By default, `spotify-fix` runs in **Dry Run** mode (simulation without modifying
your Spotify account).

### Examples

Run full cleanup pipeline in Dry Run mode:

```bash
poetry run spotify-fix --dry-run
```

Apply changes directly to Spotify account:

```bash
poetry run spotify-fix --apply
```

Run specific cleanup tasks:

```bash
# Relink reuploaded liked tracks only
poetry run spotify-fix --fix-tracks

# Consolidate liked tracks into album likes
poetry run spotify-fix --rollup-albums

# Custom report output location
poetry run spotify-fix -o ~/tmp/my_spotify_report.json
```

## Options

- `--login`: Run interactive OAuth PKCE authorization to grant read & write
  library permissions.
- `--api-creds <path>`: Path to Zotify `api_credentials.json` file.
- `--creds <path>`: Path to Zotify `credentials.json` file.
- `--apply` / `--no-dry-run`: Apply changes directly to your Spotify library.
- `--dry-run`: Simulate changes without making API mutations (default).
- `--fix-tracks`: Scan and relink reuploaded liked tracks.
- `--fix-albums`: Scan and relink reuploaded liked albums.
- `--fix-playlists`: Scan and fix reuploaded tracks in playlists.
- `--rollup-albums`: Consolidate liked tracks into album likes if full album is
  liked.
- `--all`: Execute all fixes (default).
- `-o, --output <path>`: JSON file path to write actions and unavailable items
  report.
- `-v, --verbose`: Enable detailed debug logging.
