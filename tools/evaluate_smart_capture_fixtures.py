from __future__ import annotations

import argparse
import json
from pathlib import Path

from jaw.smart_capture_fixture_eval import evaluate_fixture_root, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate human-reviewed Smart Capture fixtures."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("..") / "jaw-fixtures" / "golden",
        help="Golden fixture root (default: ../jaw-fixtures/golden)",
    )
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--markdown", dest="markdown_path", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    baseline = None
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))

    report = evaluate_fixture_root(args.corpus, baseline=baseline)
    markdown = render_markdown(report)

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

    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
