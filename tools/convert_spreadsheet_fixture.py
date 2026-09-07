from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jaw.capture import extract_job_fields

if __package__:
    from .fixture_review_schema import FIXTURE_FIELDS, LIST_FIELDS
else:
    from fixture_review_schema import FIXTURE_FIELDS, LIST_FIELDS

_REVIEW_NOISE = re.compile(
    r"(?:equal (?:employment )?opportunit|all qualified applicants|"
    r"without regard to race|request an accommodation|need assistance .*application|"
    r"alternative methods of applying|unsolicited resumes|privacy notice|"
    r"you belong here|ready to (?:join|build)|learn more: about us)",
    re.IGNORECASE,
)
_COMPENSATION_BOILERPLATE = re.compile(
    r"(?:target salary range|base salary range|pay transparency|"
    r"compensation (?:package|structure)|placement within the pay range|"
    r"pay is based on several factors)",
    re.IGNORECASE,
)


def _review_list(field: str, items: list[str]) -> list[str]:
    if field in {"benefits", "application_questions"}:
        return items
    reviewed = []
    for item in items:
        if _REVIEW_NOISE.search(item):
            continue
        if len(item) >= 180 and _COMPENSATION_BOILERPLATE.search(item):
            continue
        reviewed.append(item)
    return reviewed


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def convert_fixture(
    workspace: Path,
    fixture_id: str,
    *,
    overwrite_manual_review: bool = False,
) -> Path:
    source_root = workspace / "tests/fixtures/job_postings/private"
    output_root = source_root / "spreadsheet_approved"
    output_expected = output_root / f"{fixture_id}.expected.json"
    if output_expected.is_file() and not overwrite_manual_review:
        current = _read_json(output_expected)
        if current.get("annotation", {}).get("method") == ("independent_manual_review"):
            raise FileExistsError(
                f"Refusing to overwrite independently reviewed fixture {fixture_id}. "
                "Use --overwrite-manual-review only when intentionally rebuilding it."
            )
    expected_source = _read_json(source_root / f"{fixture_id}.expected.json")
    description = (source_root / f"{fixture_id}.txt").read_text(encoding="utf-8").strip()
    company = str(expected_source["company"]).strip()
    title = str(expected_source["title"]).strip()
    if fixture_id.startswith("015-key-capture-energy-llc-"):
        title = "Senior IT Engineer"
    elif fixture_id == "125-l3harris-lead-systems-sofware-engineer":
        title = "Lead, Systems Software Engineer"
    captures = [company, title, description]
    combined = "\n\n".join(captures)

    extraction = extract_job_fields(combined)
    values: dict[str, Any] = {
        field: ([] if field in LIST_FIELDS else "") for field in FIXTURE_FIELDS
    }
    values.update(
        {key: value for key, value in extraction.get("fields", {}).items() if key in values}
    )
    values["application_questions"] = extraction.get("application_questions", [])
    values["company"] = company
    values["title"] = title
    values["raw_description"] = combined
    for field in LIST_FIELDS:
        values[field] = _review_list(field, values[field])

    # Codex-reviewed corrections live here so regeneration is deterministic.
    if fixture_id == "002-techfinite-systems-sr-devops-engineer":
        values.update(
            {
                "location": "",
                "remote_status": "Hybrid/Remote",
                "employment_type": "Full-time",
                "preferred_skills": [
                    "AWS/Azure DevOps certifications.",
                    "Prior experience with healthcare IT or federal projects.",
                    "Exposure to security automation and compliance frameworks (HIPAA, FedRAMP).",
                ],
            }
        )
        values["experience_requirements"] = [
            item
            for item in values["experience_requirements"]
            if not item.startswith("Hybrid/Remote")
        ]
    elif fixture_id == ("073-mongodb-site-reliability-engineer-senior-or-staff-storage-layer-serv"):
        values.update(
            {
                "location": (
                    "Boston, New York City, Raleigh, Miami, Pittsburgh, or remote "
                    "in the United States (Eastern or Central time zone)"
                ),
                "remote_status": "Remote or on-site",
            }
        )

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    source = expected_source.get("source", {})
    manifest = {
        "format": "jaw-capture-fixture",
        "version": 1,
        "fixture_id": fixture_id,
        "status": "awaiting_codex",
        "scenario": "archived_description",
        "created_at": now,
        "updated_at": now,
        "active_user": "Dev",
        "target_role": "",
        "source_site": "Spreadsheet: Applied",
        "capture_files": ["captures/001.txt", "captures/002.txt", "captures/003.txt"],
        "source": source,
        "reviewer": "",
    }
    capture_document = {
        "manifest": manifest,
        "captures": [
            {
                "number": number,
                "file": f"captures/{number:03d}.txt",
                "content": content,
            }
            for number, content in enumerate(captures, 1)
        ],
    }

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / f"{fixture_id}.txt").write_text(combined + "\n", encoding="utf-8")
    _write_json(output_root / f"{fixture_id}.capture.json", capture_document)
    _write_json(
        output_expected,
        {
            "fixture_id": fixture_id,
            **values,
            "annotation": {
                "method": "automated_proposal",
                "reviewer": "",
                "reviewed_at": "",
                "source": "JAW local extractor",
            },
        },
    )
    return output_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_id", nargs="?")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Convert every spreadsheet-derived fixture in the private corpus.",
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--overwrite-manual-review",
        action="store_true",
        help="Allow replacing an independently reviewed expected file.",
    )
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if args.all:
        root = workspace / "tests/fixtures/job_postings/private"
        fixture_ids = sorted(
            path.name.removesuffix(".expected.json") for path in root.glob("*.expected.json")
        )
        for fixture_id in fixture_ids:
            convert_fixture(
                workspace,
                fixture_id,
                overwrite_manual_review=args.overwrite_manual_review,
            )
        print(f"Converted {len(fixture_ids)} fixtures")
        return
    if not args.fixture_id:
        parser.error("provide fixture_id or --all")
    print(
        convert_fixture(
            workspace,
            args.fixture_id,
            overwrite_manual_review=args.overwrite_manual_review,
        )
    )


if __name__ == "__main__":
    main()
