from pathlib import Path

from jaw.application.document_workbench_job_generation import (
    _job_context,
    routing_state,
    save_routing,
    select_routed_document,
)
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id=None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def _documents():
    return [
        {
            "id": "doc_management",
            "name": "Management Cover Letter",
            "settings": {
                "generation_rules": [
                    {
                        "id": "management",
                        "label": "Management",
                        "priority": 10,
                        "keywords": [
                            "manager",
                            "management",
                            "director",
                            "head",
                            "vice president",
                            "vp",
                            "chief",
                        ],
                    }
                ]
            },
        },
        {
            "id": "doc_architecture",
            "name": "Architecture Cover Letter",
            "settings": {
                "generation_rules": [
                    {
                        "id": "architecture",
                        "label": "Architecture",
                        "priority": 20,
                        "keywords": ["architect", "architecture"],
                    }
                ]
            },
        },
        {
            "id": "doc_platform",
            "name": "Platform & SRE Cover Letter",
            "settings": {"generation_default": True},
        },
    ]


def test_title_routing_prefers_management_for_director_titles():
    document, route = select_routed_document(
        _documents(),
        "Director, Cloud Architecture",
    )

    assert document["id"] == "doc_management"
    assert route == {
        "id": "management",
        "label": "Management",
        "keyword": "director",
    }


def test_title_routing_uses_architecture_without_management_match():
    document, route = select_routed_document(
        _documents(),
        "Principal Cloud Architect",
    )

    assert document["id"] == "doc_architecture"
    assert route["id"] == "architecture"
    assert route["keyword"] == "architect"


def test_title_routing_defaults_to_platform_sre():
    document, route = select_routed_document(
        _documents(),
        "Staff Site Reliability Engineer",
    )

    assert document["id"] == "doc_platform"
    assert route["id"] == "default"


def test_lead_is_not_implicitly_management():
    document, route = select_routed_document(
        _documents(),
        "Technical Lead, Platform Engineering",
    )

    assert document["id"] == "doc_platform"
    assert route["id"] == "default"


def test_explicit_document_selection_bypasses_title_rules():
    document, route = select_routed_document(
        _documents(),
        "Director of Infrastructure",
        explicit_document_id="doc_architecture",
    )

    assert document["id"] == "doc_architecture"
    assert route["id"] == "manual"


def test_routing_is_persisted_on_user_owned_document_resources(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    management = service.create_document(1, {"name": "Management Cover Letter"})
    architecture = service.create_document(1, {"name": "Architecture Cover Letter"})
    platform = service.create_document(1, {"name": "Platform & SRE Cover Letter"})

    saved = save_routing(
        database.document_workbench_repository,
        1,
        {
            "rules": [
                {
                    "id": "management",
                    "label": "Management",
                    "priority": 10,
                    "keywords": ["manager", "director"],
                    "document_id": management["id"],
                },
                {
                    "id": "architecture",
                    "label": "Architecture",
                    "priority": 20,
                    "keywords": ["architect"],
                    "document_id": architecture["id"],
                },
            ],
            "default_document_id": platform["id"],
        },
    )

    assert saved == routing_state(database.document_workbench_repository, 1)
    assert saved["default_document_id"] == platform["id"]
    assert [rule["document_id"] for rule in saved["rules"]] == [
        management["id"],
        architecture["id"],
    ]

    management_state = database.document_workbench_repository.get_document(1, management["id"])
    platform_state = database.document_workbench_repository.get_document(1, platform["id"])
    management_routing = management_state["settings"]["generation_routing"]
    platform_routing = platform_state["settings"]["generation_routing"]
    assert management_routing["rules"][0]["id"] == "management"
    assert platform_routing["default_document_ids"] == [platform["id"]]


def test_tracker_job_context_uses_current_generation_schema():
    context = _job_context(
        {
            "user": {"first_name": "Jane", "last_name": "Engineer"},
            "work_history": [
                {"company": "Example", "title": "Engineer", "enabled": True}
            ],
            "capability_model": {"entities": [], "relationships": []},
        },
        {"id": 42, "company": "GovCIO", "title": "DevSecOps Lead"},
        job_id=42,
    )

    assert context.schema_version == 2
    assert context.job_ref["company"] == "GovCIO"
    assert context.job_ref["title"] == "DevSecOps Lead"
    assert context.work_exp == (
        {
            "company": "Example",
            "title": "Engineer",
            "enabled": True,
            "highlights": [],
        },
    )
    assert context.cap == {"all": [], "sets": {}}
    assert context.as_mapping()["job_ref"]["title"] == "DevSecOps Lead"
