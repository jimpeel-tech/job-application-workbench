from __future__ import annotations

import argparse
from pathlib import Path

from jaw.database import JobDatabase
from jaw.importers.spreadsheet_applications import (
    import_spreadsheet_applications,
    resolve_user_id,
)
from jaw.paths import database_path


def _default_source_dir(workspace: Path) -> Path:
    return workspace / "tests" / "fixtures" / "job_postings" / "private" / "spreadsheet_approved"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import approved historical spreadsheet job applications into a JAW user."
    )
    parser.add_argument(
        "--user",
        required=True,
        help="Target JAW user account name.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="JAW checkout root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help=(
            "Approved spreadsheet fixture directory. Defaults to "
            "tests/fixtures/job_postings/private/spreadsheet_approved under --workspace."
        ),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=database_path(),
        help="JAW SQLite database path. Defaults to the normal JAW database.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the import. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    source_dir = (args.source_dir or _default_source_dir(workspace)).resolve()
    target_database = args.database.expanduser().resolve()

    user_id = resolve_user_id(target_database, args.user)
    database = JobDatabase(target_database)
    result = import_spreadsheet_applications(
        database,
        user_id=user_id,
        source_dir=source_dir,
        apply=args.apply,
    )

    print(f"Target user: {args.user} (id={user_id})")
    print(f"Database: {target_database}")
    print(f"Source: {source_dir}")
    print(f"Approved fixtures: {result.approved}")
    print(f"Already imported: {result.already_imported}")
    print(f"Ignored unapproved: {result.ignored_unapproved}")
    if result.dry_run:
        pending = result.approved - result.already_imported
        print(f"Would import: {pending}")
        print("Dry run only. Re-run with --apply to write changes.")
    else:
        print(f"Imported: {result.imported}")


if __name__ == "__main__":
    main()
