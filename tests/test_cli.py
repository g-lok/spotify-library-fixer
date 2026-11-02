from spotify_fix.cli import parse_args


def test_parse_args():
    args = parse_args(["--apply", "--all", "-o", "/tmp/custom.json"])
    assert args.apply is True
    assert args.all is True
    assert args.output == "/tmp/custom.json"


def test_parse_args_dry_run():
    args = parse_args(["--dry-run", "--fix-tracks"])
    assert args.apply is False
    assert args.fix_tracks is True
