"""Evaluate Smart Capture against the ignored private golden corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jaw.corpus_eval import evaluate_corpus, render_markdown


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).parent / "fixtures" / "job_postings" / "private"
        / "approved",
    )
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    report = evaluate_corpus(args.corpus)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
    if not args.json and not args.markdown:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
