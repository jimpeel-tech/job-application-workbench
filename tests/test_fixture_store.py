from jaw.fixture_store import FixtureStore


def test_smart_capture_snapshot_preserves_observations_without_ground_truth(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    store = FixtureStore(tmp_path)
    package = store.snapshot_session(
        [
            {
                "id": 11,
                "content_type": "job_title",
                "classification_status": "classified",
                "content": "Senior Platform Engineer",
                "metadata": {
                    "metrics": {"sequence": 1},
                    "extraction": {
                        "capture_context": "job_title",
                        "fields": {"title": "Senior Platform Engineer"},
                    },
                },
            },
            {
                "content_type": "unclassified",
                "content": "Full-Time Remote $200,000 - $250,000 /yr",
            },
        ],
        {
            "title": ("Senior Platform Engineer",),
            "pay": ("$200000–250000 per year",),
        },
        {
            "fields": {
                "title": "Senior Platform Engineer",
                "pay": "$200,000 - $250,000 /yr",
            },
            "evidence": {"pay": "$200,000 - $250,000 /yr"},
            "insights": [],
        },
        {"analysis_mode": "verify", "ollama_model": "qwen3:14b"},
        active_user_id=7,
        active_user_name="Any User",
        parser_resolution={
            "values": {"title": ["Senior Platform Engineer"]},
            "fields": {
                "title": {
                    "support_count": 1,
                    "corroborated": False,
                    "contexts": ["job_title"],
                }
            },
        },
        merge_resolution={
            "title": {
                "values": ["Senior Platform Engineer"],
                "source": "both",
                "review_status": "verified",
            }
        },
    )

    fixture_id = package["manifest"]["fixture_id"]
    folder = store.snapshot_root / fixture_id
    assert package["manifest"]["active_user_id"] == 7
    assert package["manifest"]["active_user_name"] == "Any User"
    assert package["manifest"]["expected_values"] == "not-set"
    assert package["manifest"]["version"] == 3
    assert package["captures"][0]["metadata"]["metrics"]["sequence"] == 1
    assert (folder / "combined.txt").is_file()
    assert (folder / "captures.json").is_file()
    assert (folder / "parser.json").is_file()
    assert (folder / "parser_resolution.json").is_file()
    assert (folder / "merge_resolution.json").is_file()
    assert package["parser_resolution"]["fields"]["title"]["support_count"] == 1
    assert package["merge_resolution"]["title"]["review_status"] == "verified"
    assert (folder / "ollama.json").is_file()
    assert not any(folder.glob("*.expected.json"))
    assert store.list_snapshots()[0]["fixture_id"] == fixture_id


def test_smart_capture_snapshot_requires_captured_content(tmp_path):
    store = FixtureStore(tmp_path)
    try:
        store.snapshot_session(
            [],
            {},
            None,
            {"analysis_mode": "parser", "ollama_model": "qwen3:14b"},
            active_user_id=1,
            active_user_name="User",
        )
    except ValueError as error:
        assert "Capture at least one selection" in str(error)
    else:
        raise AssertionError("empty Smart Capture sessions must not create fixtures")


def test_fixture_store_has_no_review_or_approval_api(tmp_path):
    store = FixtureStore(tmp_path)
    for retired in (
        "new",
        "current",
        "add_capture",
        "prepare",
        "save",
        "approve",
        "reject",
        "publish_codex_review",
        "delete_rejected",
    ):
        assert not hasattr(store, retired)
