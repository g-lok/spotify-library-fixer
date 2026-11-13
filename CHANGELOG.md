# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-11-12

### Added in 0.2.1

- **Standalone Bad Variant Audit & Purging (`--purge-variants`)**: Audits local
  Zotify music library for standalone bad variant files ("Live", "Karaoke",
  "Cover") downloaded during previous fallback searches. Compares local track
  titles against official Spotify album tracklists to preserve legitimate
  official album tracks while purging bad substitutions.
- **Generic Default Music Path**: Replaced machine-specific fallback paths with
  standard POSIX ~/Music/Zotify Music paths.

## [0.2.0] - 2026-11-12

### Added in 0.2.0

- **Strict Track/Album Candidate Scoring**: Quality matcher prevents bad
  substitutions by enforcing title fuzzy similarity, artist matching, track
  duration tolerances (±25s), and rejecting self-matches.
- **Variant Keyword Filtering**: Automatically filters out "Live", "Remix",
  "Acoustic", "Cover", "Session", and "Karaoke" versions when searching for
  replacement studio tracks/albums.
- **Fallback File Purging (`--purge-fallbacks`)**: Scans Zotify output library
  (`/mnt/minidrive/zotify`) and removes duplicate fallback files (`*_#.ogg`).
- **Unplayable Album Cleanup**: Automatically unlikes unplayable albums with
  no valid Spotify replacement to stop Zotify from retrying them indefinitely.
- **Fast Batch API Scanning**: Optimized album scanning from `/me/albums` initial
  payloads, reducing scanning time from minutes to seconds.

## [0.1.0] - 2026-11-02

### Added in 0.1.0

- **Reuploaded Content Fixer**: Scans liked tracks, albums, and playlists for
  unplayable items. Relinks them to active Spotify versions.
- **Album Rollup**: Automatically consolidates track likes into an album like
  if 100% of an album's tracks are liked.
- **Unavailable Content Report**: Exports a JSON report (`-o, --output`)
  detailing unresolvable items.
- **Zotify Integration**: Reuses existing Zotify credentials
  (`api_credentials.json` and `credentials.json`) from `~/.config/zotify/`.
- **Interactive OAuth PKCE Server (`--login`)**: Standalone PKCE authorization
  server to acquire read/write library scopes.
- **POSIX Compliant CLI**: Standard logging streams to `stderr`, summary
  outputs to `stdout`, exact `-o` output semantics.
- **Test Suite**: 17 unit tests covering authentication, rate-limiting retries,
  batching, playlist ownership filtering, and album track availability.
