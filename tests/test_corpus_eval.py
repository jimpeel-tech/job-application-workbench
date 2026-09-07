import json

from jaw.corpus_eval import evaluate_corpus, normalize_number, render_markdown


def write_fixture(root, fixture_id, expected, text, scenario="structured"):
    (root / f"{fixture_id}.txt").write_text(text, encoding="utf-8")
    (root / f"{fixture_id}.expected.json").write_text(
        json.dumps({"fixture_id": fixture_id, **expected}), encoding="utf-8"
    )
    (root / f"{fixture_id}.capture.json").write_text(
        json.dumps({
            "manifest": {
                "fixture_id": fixture_id,
                "scenario": scenario,
                "source_site": "Example Careers",
            },
            "captures": [],
        }),
        encoding="utf-8",
    )


def test_evaluator_scores_fields_groups_and_false_positives(tmp_path):
    write_fixture(
        tmp_path,
        "good",
        {"company": "Example Corp", "title": "Platform Engineer"},
        "Platform Engineer\nCompany: Example Corp\nJob Type: Full-time",
        "complete_selection",
    )

    report = evaluate_corpus(tmp_path)

    assert report["fixture_count"] == 1
    assert report["overall"]["fields"]["title"]["exact"] == 1
    assert report["overall"]["fields"]["company"]["exact"] == 1
    assert report["overall"]["fields"]["employment_type"]["false_positive"] == 1
    assert report["by_scenario"]["complete_selection"]["fixtures"] == 1
    assert report["by_source"]["Example Careers"]["fixtures"] == 1


def test_evaluator_scores_list_items_and_renders_markdown(tmp_path):
    write_fixture(
        tmp_path,
        "questions",
        {
            "company": "Example Corp",
            "title": "Platform Engineer",
            "application_questions": ["Why this role?"],
        },
        "Platform Engineer\nCompany: Example Corp\n"
        "Application Question(s):\nWhy this role?",
    )

    report = evaluate_corpus(tmp_path)
    questions = report["overall"]["fields"]["application_questions"]
    assert questions["list_recall"] == 1.0
    assert "# Smart Capture corpus baseline" in render_markdown(report)


def test_numeric_normalization_ignores_currency_formatting():
    assert normalize_number("$109,428.00") == "109428"


def test_evaluator_excludes_benefits_from_first_pass_scoring(tmp_path):
    write_fixture(
        tmp_path,
        "benefits",
        {
            "company": "Example Corp",
            "title": "Platform Engineer",
            "benefits": ["Health insurance", "Paid time off"],
        },
        "Platform Engineer\nCompany: Example Corp\n"
        "Benefits\nHealth insurance\nPaid time off",
    )

    report = evaluate_corpus(tmp_path)

    assert "benefits" not in report["overall"]["fields"]


def test_evaluator_matches_conservative_list_paraphrases(tmp_path):
    write_fixture(
        tmp_path,
        "paraphrase",
        {
            "company": "Example Corp",
            "title": "Warehouse Technician",
            "responsibilities": ["Operate a forklift and warehouse machinery"],
        },
        "Warehouse Technician\nCompany: Example Corp\nResponsibilities\n"
        "Operating a forklift and other warehouse machinery safely",
    )

    report = evaluate_corpus(tmp_path)
    responsibilities = report["overall"]["fields"]["responsibilities"]
    assert responsibilities["list_matched"] == 1
