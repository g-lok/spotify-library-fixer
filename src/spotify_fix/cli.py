from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from spotify_fix.auth import AuthManager
from spotify_fix.client import SpotifyClient
from spotify_fix.cleaner import CleanerPipeline


def parse_args(args: list[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spotify Fix - Clean up reuploaded tracks/albums/playlists and consolidate album likes."
    )

    parser.add_argument(
        "--login",
        action="store_true",
        help="Run interactive PKCE OAuth login to authorize write permissions for Zotify API credentials",
    )
    parser.add_argument(
        "--api-creds",
        type=str,
        default=None,
        help="Path to Zotify api_credentials.json file",
    )
    parser.add_argument(
        "--creds",
        type=str,
        default=None,
        help="Path to Zotify credentials.json file",
    )
    parser.add_argument(
        "--apply",
        "--no-dry-run",
        dest="apply",
        action="store_true",
        default=False,
        help="Apply changes to Spotify account (default is Dry Run simulation)",
    )
    parser.add_argument(
        "--dry-run",
        dest="apply",
        action="store_false",
        help="Simulate actions without applying changes to Spotify (default)",
    )
    parser.add_argument(
        "--fix-tracks",
        action="store_true",
        help="Scan and fix reuploaded liked tracks",
    )
    parser.add_argument(
        "--fix-albums",
        action="store_true",
        help="Scan and fix reuploaded liked albums",
    )
    parser.add_argument(
        "--fix-playlists",
        action="store_true",
        help="Scan and fix reuploaded tracks in playlists",
    )
    parser.add_argument(
        "--rollup-albums",
        action="store_true",
        help="Consolidate liked tracks into album likes if full album is liked",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all cleanup tasks (tracks, albums, playlists, and album rollup)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(Path.home() / "tmp" / "spotify_fix_report.json"),
        help="File path to save the JSON report of actions and unavailable content",
    )
    parser.add_argument(
        "--progress",
        "-P",
        action="store_true",
        help="Show rsync-style progress bar indicator on stderr",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    return parser.parse_args(args)


class FlushingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


def main():
    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO

    # POSIX Standard: Logs stream to stderr or stdout cleanly
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[FlushingStreamHandler(sys.stderr)],
    )

    logger = logging.getLogger("spotify_fix")

    if args.login:
        auth = AuthManager(api_creds_path=args.api_creds, creds_path=args.creds)
        auth.interactive_login()
        sys.exit(0)

    dry_run = not args.apply

    if dry_run:
        logger.info("Running in DRY RUN mode. No changes will be applied to Spotify.")
    else:
        logger.warning("Running in APPLY mode. Changes WILL be made to your Spotify library.")

    # Initialize Auth & Client
    auth = AuthManager(api_creds_path=args.api_creds, creds_path=args.creds)
    client = SpotifyClient(auth_manager=auth)
    pipeline = CleanerPipeline(client=client, dry_run=dry_run, progress_enabled=args.progress)

    # Determine tasks to execute
    run_all = args.all or not (
        args.fix_tracks or args.fix_albums or args.fix_playlists or args.rollup_albums
    )

    if run_all or args.fix_tracks:
        logger.info("=== Scanning & Fixing Liked Tracks ===")
        pipeline.fix_reuploaded_liked_tracks()

    if run_all or args.fix_albums:
        logger.info("=== Scanning & Fixing Liked Albums ===")
        pipeline.fix_reuploaded_liked_albums()

    if run_all or args.fix_playlists:
        logger.info("=== Scanning & Fixing Playlists ===")
        pipeline.fix_reuploaded_playlists()

    if run_all or args.rollup_albums:
        logger.info("=== Scanning & Consolidating Album Rollups ===")
        pipeline.rollup_albums()

    # Generate Report
    report_file = pipeline.export_reports(report_path=args.output)
    
    print("\n" + "=" * 50)
    print(f"Cleanup Run Completed ({'DRY RUN' if dry_run else 'APPLIED'}).")
    print(f"Total Actions Recorded: {len(pipeline.actions)}")
    print(f"Total Unavailable Items: {len(pipeline.unavailable_items)}")
    print(f"Detailed Report Written To: {report_file}")
    print("=" * 50)


if __name__ == "__main__":
    main()
