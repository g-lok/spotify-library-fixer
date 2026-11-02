# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-02

### Added

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
