import json
from pathlib import Path

import pytest

from tools.apply_manual_fixture_reviews import LIST_FIELDS, REVIEW_FIELDS, apply_reviews
from tools.convert_spreadsheet_fixture import convert_fixture


def test_converter_protects_independently_reviewed_fixture(tmp_path):
    fixture_id = "001-example"
    output = tmp_path / "tests/fixtures/job_postings/private/spreadsheet_approved"
    output.mkdir(parents=True)
    (output / f"{fixture_id}.expected.json").write_text(
        json.dumps({"annotation": {"method": "independent_manual_review"}}),
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        convert_fixture(tmp_path, fixture_id)


def test_manual_review_helper_uses_source_lines_and_preserves_captures(tmp_path):
    fixture_id = "001-example"
    corpus = tmp_path / "private"
    output = corpus / "spreadsheet_approved"
    output.mkdir(parents=True)
    (corpus / f"{fixture_id}.txt").write_text(
        "Responsibilities\n- Operate Kubernetes\n", encoding="utf-8"
    )
    (output / f"{fixture_id}.expected.json").write_text("{}", encoding="utf-8")
    captures = ["Example Corp", "Platform Engineer", "Responsibilities\n- Operate Kubernetes"]
    (output / f"{fixture_id}.capture.json").write_text(
        json.dumps(
            {
                "captures": [
                    {"number": number, "content": content}
                    for number, content in enumerate(captures, 1)
                ]
            }
        ),
        encoding="utf-8",
    )

    values = {field: ([] if field in LIST_FIELDS else "") for field in REVIEW_FIELDS}
    values.update({"company": "Example Corp", "title": "Platform Engineer"})
    values.pop("responsibilities")
    manifest = tmp_path / "reviews.json"
    manifest.write_text(
        json.dumps(
            {
                "reviews": {
                    fixture_id: {
                        "values": values,
                        "line_fields": {"responsibilities": [2]},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    count, fixture_ids = apply_reviews(corpus, manifest)

    assert count == 1
    assert fixture_ids == [fixture_id]
    reviewed = json.loads((output / f"{fixture_id}.expected.json").read_text(encoding="utf-8"))
    assert reviewed["responsibilities"] == ["Operate Kubernetes"]
    assert reviewed["raw_description"] == "\n\n".join(captures)
    assert reviewed["annotation"]["method"] == "independent_manual_review"


def test_offline_review_tools_do_not_depend_on_production_fixture_store():
    converter_source = Path("tools/convert_spreadsheet_fixture.py").read_text(encoding="utf-8")
    manual_source = Path("tools/apply_manual_fixture_reviews.py").read_text(encoding="utf-8")

    assert "jaw.fixture_store" not in converter_source
    assert "jaw.fixture_store" not in manual_source
