from __future__ import annotations

import argparse
import json
from pathlib import Path

from jaw.spreadsheet_fixture_eval import (
    evaluate_spreadsheet_corpus,
    render_spreadsheet_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the archived spreadsheet-approved fixture corpus."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("..") / "jaw-fixtures" / "spreadsheet_approved",
        help="Spreadsheet fixture root (default: ../jaw-fixtures/spreadsheet_approved)",
    )
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--markdown", dest="markdown_path", type=Path)
    args = parser.parse_args()

    report = evaluate_spreadsheet_corpus(args.corpus)
    markdown = render_spreadsheet_markdown(report)
    print(markdown, end="")

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.markdown_path:
        args.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_path.write_text(markdown, encoding="utf-8")

    return 1 if report["corpus_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
