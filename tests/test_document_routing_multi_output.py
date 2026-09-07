from pathlib import Path

from jaw.application.document_workbench_job_generation import (
    routing_state,
    save_routing,
    select_routed_documents,
)
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id=None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def test_one_rule_can_generate_resume_and_cover_letter(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    cover_letter = service.create_document(1, {"name": "Cover Letter - Architect"})
    resume = service.create_document(1, {"name": "Resume - Architect"})
    fallback_cover = service.create_document(1, {"name": "Cover Letter - SRE"})
    fallback_resume = service.create_document(1, {"name": "Resume - SRE"})

    saved = save_routing(
        repository,
        1,
        {
            "rules": [
                {
                    "id": "architecture",
                    "label": "Architecture",
                    "priority": 10,
                    "keywords": ["architect", "architecture"],
                    "document_ids": [cover_letter["id"], resume["id"]],
                }
            ],
            "default_document_ids": [fallback_cover["id"], fallback_resume["id"]],
        },
    )

    assert saved == routing_state(repository, 1)
    assert saved["rules"][0]["document_ids"] == [cover_letter["id"], resume["id"]]
    assert saved["rules"][0]["document_id"] == cover_letter["id"]
    assert saved["default_document_ids"] == [fallback_cover["id"], fallback_resume["id"]]
    assert saved["default_document_id"] == fallback_cover["id"]

    documents = repository.list_documents(1)
    selected, route = select_routed_documents(documents, "Principal Cloud Architect")
    assert [document["id"] for document in selected] == [cover_letter["id"], resume["id"]]
    assert route == {
        "id": "architecture",
        "label": "Architecture",
        "keyword": "architect",
    }

    fallback, fallback_route = select_routed_documents(
        documents,
        "Staff Site Reliability Engineer",
    )
    assert [document["id"] for document in fallback] == [
        fallback_cover["id"],
        fallback_resume["id"],
    ]
    assert fallback_route["id"] == "default"


def test_unassigned_rule_survives_save_when_documents_exist(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    service.create_document(1, {"name": "Cover Letter"})

    save_routing(
        repository,
        1,
        {
            "rules": [
                {
                    "id": "management",
                    "label": "Management",
                    "priority": 10,
                    "keywords": ["manager", "director"],
                    "document_ids": [],
                }
            ],
            "default_document_ids": [],
        },
    )

    restored = routing_state(repository, 1)
    assert restored["rules"][0]["id"] == "management"
    assert restored["rules"][0]["document_ids"] == []
