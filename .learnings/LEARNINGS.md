# Learnings

## Category: best_practice

### 2026-11-02: Spotify API Scopes & Rate Limits

- **Observation**: Spotify Web API enforces severe 429 rate limit penalties
  (60s+ windows) on Keymaster Desktop client tokens for library write operations
  (`PUT /v1/me/tracks`).
- **Solution**: Use OAuth PKCE tokens generated via Zotify's Client ID
  (`715afe9af8b3491199907272a61625c4`) with explicit `user-library-modify` scope.
  This allows batch write operations without rate limit penalties.

### 2026-11-02: Search Fallback & Market Parameters

- **Observation**: Strict `track:"..." artist:"..."` search queries fail when
  song titles include remaster or edition suffixes (e.g. `(2005 Remaster)`).
- **Solution**: Strip remaster/edition suffixes before searching, pass `market:
  'from_token'`, and implement a 2-stage fallback query (`<clean_name>
  <clean_artist>`).

## Category: correction

### 2026-11-02: POSIX Compliance & Logging Streams

- **Observation**: Forcing hardcoded file logging inside CLI code prevents
  standard Unix shell redirection (`> file 2>&1`).
- **Solution**: Standardize CLI logging to `stderr`, data/summaries to
  `stdout`, and respect exact `-o` output path semantics without forcing
  internal log files.
