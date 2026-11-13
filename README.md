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
- **POSIX Compliant CLI**: Standard logging streams to `stderr`, data summaries
  output to `stdout`. Compatible with standard shell redirection (`> file 2>&1`).

## Installation

### Via Pip / Pipx

Install directly from GitHub:

```bash
pip install git+https://github.com/g-lok/spotify-library-fixer
```

Or using `pipx` for isolated application environment:

```bash
pipx install git+https://github.com/g-lok/spotify-library-fixer
```

### From Source (Poetry + mise)

Clone and install dependencies locally:

```bash
git clone https://github.com/g-lok/spotify-library-fixer.git
cd spotify-library-fixer
poetry install
```

## First-Time Authorization

To grant read and write library permissions (preventing rate limit errors when
saving or un-liking tracks), run the interactive authorization helper:

```bash
spotify-fix --login
```

Follow the link printed in your terminal, approve permissions in your browser,
and `~/.config/zotify/api_credentials.json` will be saved automatically.

## Usage & Examples

By default, `spotify-fix` runs in **Dry Run** mode (simulation without modifying
your Spotify account).

### Run Full Cleanup in Dry Run Mode

```bash
spotify-fix --dry-run
```

### Apply Changes to Spotify Library

```bash
spotify-fix --apply
```

### Run in Background with Shell Redirection

```bash
PYTHONUNBUFFERED=1 spotify-fix --all --apply > ~/tmp/spotify_fix.log 2>&1 &
```

### Run Specific Tasks with Progress Bar

```bash
# Relink reuploaded liked tracks only with progress bar
spotify-fix --fix-tracks --progress

# Consolidate liked tracks into album likes
spotify-fix --rollup-albums --apply

# Export report to custom path
spotify-fix -o ~/tmp/my_spotify_report.json
```

## CLI Options

- `--login`: Run interactive OAuth PKCE authorization server to grant read &
  write permissions.
- `--api-creds <path>`: Path to Zotify `api_credentials.json` file.
- `--creds <path>`: Path to Zotify `credentials.json` file.
- `--apply` / `--no-dry-run`: Apply changes directly to your Spotify library.
- `--dry-run`: Simulate changes without making API mutations (default).
- `--progress`, `-P`: Display rsync-style progress indicator on `stderr`.
- `--fix-tracks`: Scan and relink reuploaded liked tracks.
- `--fix-albums`: Scan and relink reuploaded liked albums.
- `--fix-playlists`: Scan and fix reuploaded tracks in playlists.
- `--rollup-albums`: Consolidate liked tracks into album likes if full album is
  liked.
- `--purge-fallbacks [DIR]`: Purge duplicate fallback files (`*_#.ogg`) from
  Zotify music library directory (default: `/mnt/minidrive/zotify`).
- `--all`: Execute all fixes including fallback file purging (default).
- `-o, --output <path>`: JSON file path to write actions and unavailable items
  report.
- `-v, --verbose`: Enable detailed debug logging.
