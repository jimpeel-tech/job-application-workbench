from __future__ import annotations

import argparse
from pathlib import Path

from jaw.fixture_export import FixtureExportError, export_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a local Smart Capture snapshot to the private jaw-fixtures inbox."
    )
    parser.add_argument(
        "fixture_id",
        nargs="?",
        default="latest",
        help="Fixture id to export. Defaults to the latest local snapshot.",
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

    try:
        destination = export_snapshot(
            Path(args.workspace),
            Path(args.fixture_repo) if args.fixture_repo else None,
            args.fixture_id,
        )
    except FixtureExportError as error:
        parser.error(str(error))
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
