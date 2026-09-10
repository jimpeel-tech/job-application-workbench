from __future__ import annotations

import argparse
from pathlib import Path

from jaw.fixture_export import FixtureExportError, export_all_snapshots, export_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export local Smart Capture snapshots to the private jaw-fixtures inbox."
    )
    parser.add_argument(
        "fixture_id",
        nargs="?",
        default="latest",
        help="Fixture id to export. Defaults to the latest local snapshot.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export every local snapshot not already present in the fixture inbox.",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="JAW repository/workspace path. Defaults to the current directory.",
    )
    parser.add_argument(
        "--fixture-repo",
        default=None,
        help=(
            "Path to the private jaw-fixtures clone. Defaults to JAW_FIXTURE_REPO "
            "or a sibling directory named jaw-fixtures."
        ),
    )
    args = parser.parse_args()

    if args.all and args.fixture_id != "latest":
        parser.error("fixture_id cannot be combined with --all")

    workspace = Path(args.workspace)
    fixture_repo = Path(args.fixture_repo) if args.fixture_repo else None
    try:
        if args.all:
            destinations = export_all_snapshots(workspace, fixture_repo)
            if not destinations:
                print("No new fixtures to export.")
                return 0
            for destination in destinations:
                print(destination)
            return 0

        destination = export_snapshot(workspace, fixture_repo, args.fixture_id)
    except FixtureExportError as error:
        parser.error(str(error))
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
