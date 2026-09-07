import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer


def request_json(
    server: DashboardServer,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict | list]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{server.url}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


@pytest.fixture
def dashboard(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    user_data = UserDataStore(database_path)
    server = DashboardServer(
        database,
        port=0,
        user_data_path=database_path,
    )
    server.start()
    try:
        yield server, database, user_data
    finally:
        server.stop()


def test_capability_http_contracts(dashboard):
    server, _, user_data = dashboard

    status, created = request_json(
        server,
        "/api/capabilities/entities/upsert",
        method="POST",
        payload={
            "entity": {
                "id": "cap_test_kubernetes",
                "type": "technology",
                "canonical_name": "Test Kubernetes",
                "display_name": "Test Kubernetes",
                "rating": 0,
                "match_enabled": True,
                "iterator_enabled": True,
            }
        },
    )
    assert status == 200
    assert created["entity"]["id"] == "cap_test_kubernetes"

    status, response = request_json(
        server,
        "/api/capabilities/rating",
        method="POST",
        payload={"entity_id": "cap_test_kubernetes", "rating": 4},
    )
    assert status == 200
    entity = next(
        item for item in response["capabilities"]["entities"] if item["id"] == "cap_test_kubernetes"
    )
    assert entity["rating"] == 4

    status, schema = request_json(server, "/api/capabilities/schema")
    assert status == 200
    assert schema["api_version"] == 2
    assert {item["value"] for item in schema["entity_types"]} >= {
        "competency",
        "technology",
        "product",
        "set",
    }

    assert user_data.read()["capability_model"]["entities"]


def test_tracker_mutations_are_scoped_to_active_user(dashboard):
    server, database, user_data = dashboard
    owner_id = user_data.create_user("Tracker Owner")
    other_id = user_data.create_user("Tracker Other")
    user_data.switch_user(owner_id)

    owner_job = database.create_job("Owner description", owner_id)
    other_job = database.create_job("Other description", other_id)

    status, jobs = request_json(server, "/api/jobs")
    assert status == 200
    assert [job["id"] for job in jobs] == [owner_job]

    status, response = request_json(
        server,
        f"/api/jobs/{owner_job}/status",
        method="POST",
        payload={"status": "Applying"},
    )
    assert status == 200
    assert response["job"]["status"] == "Applying"

    status, response = request_json(
        server,
        f"/api/jobs/{other_job}/status",
        method="POST",
        payload={"status": "Applied"},
    )
    assert (status, response) == (404, {"error": "Not found"})
    assert database.get_job(other_job, other_id)["status"] == "Captured"

    status, response = request_json(
        server,
        f"/api/jobs/{owner_job}/questions",
        method="POST",
        payload={"question": "Why this role?", "answer": "Initial answer"},
    )
    assert status == 200
    question_id = response["question_id"]

    status, response = request_json(
        server,
        f"/api/jobs/{owner_job}/questions/{question_id}",
        method="POST",
        payload={"question": "Updated question?", "answer": "Updated answer"},
    )
    assert status == 200
    assert response["job"]["questions"][0]["submitted_answer"] == "Updated answer"

    status, response = request_json(
        server,
        f"/api/jobs/{other_job}",
        method="DELETE",
    )
    assert (status, response) == (404, {"error": "Not found"})


def test_user_data_export_import_is_document_engine_agnostic(dashboard):
    server, _, user_data = dashboard
    user_data.save_custom_fields(
        [
            {
                "id": "before-import",
                "label": "Before import",
                "value": "old",
                "type": "single",
            }
        ]
    )

    status, exported = request_json(server, "/api/user-data/export")
    assert status == 200
    assert exported["format"] == "jaw-user-data"
    assert exported["version"] == 6
    assert "documents" not in exported

    exported["user"]["first_name"] = "Imported"
    exported["custom_fields"] = [
        {
            "id": "after-import",
            "label": "After import",
            "value": "new",
            "type": "multi",
        }
    ]

    status, response = request_json(
        server,
        "/api/user-data/import",
        method="POST",
        payload={"data": exported, "mode": "replace"},
    )
    assert (status, response) == (200, {"ok": True})

    status, current = request_json(server, "/api/user-data")
    assert status == 200
    assert current["user"]["first_name"] == "Imported"
    assert current["custom_fields"] == [
        {
            "id": "after-import",
            "label": "After import",
            "value": "new",
            "type": "multi",
        }
    ]

    status, response = request_json(
        server,
        "/api/user-data/import",
        method="POST",
        payload={"data": exported, "mode": "unsupported"},
    )
    assert status == 400
    assert response["error"] == "Import mode must be merge or replace"


def test_native_workbench_state_create_and_template_lifecycle(dashboard):
    server, _, _ = dashboard

    status, initial = request_json(server, "/api/workbench/state")
    assert status == 200
    assert initial["workbench"]["documents"] == []
    assert initial["workbench"]["resources"] == []

    status, created = request_json(
        server,
        "/api/workbench/documents/create",
        method="POST",
        payload={"name": "HTTP Workbench Document"},
    )
    assert status == 200
    document = created["document"]
    assert document["name"] == "HTTP Workbench Document"
    template = document["template"]
    assert template["name"] == "HTTP Workbench Document"
    assert template["visibility"] == "private"
    assert template["owner_id"] == document["id"]
    assert template["settings"] == {"renderer": "tectonic", "format": "latex_jinja"}
    assert [item["id"] for item in created["workbench"]["documents"]] == [document["id"]]

    edited_source = template["content"].replace("{{ section }}", "{{ intro }}")
    status, checkpointed = request_json(
        server,
        "/api/workbench/checkpoint",
        method="POST",
        payload={
            "resource_id": template["id"],
            "document_id": document["id"],
            "content": edited_source,
        },
    )
    assert status == 200
    assert "template_replaced" not in checkpointed

    current = next(
        item for item in checkpointed["state"]["documents"] if item["id"] == document["id"]
    )
    current_template = current["template"]
    assert current_template["id"] == template["id"]
    assert current_template["visibility"] == "private"
    assert current_template["owner_id"] == document["id"]
    symbols = {section["reference_symbol"] for section in current["sections"]}
    # Checkpoint reconciliation is additive. Removing an existing reference
    # requires an explicit structural transition.
    assert symbols == {"intro", "section"}


def test_native_workbench_shared_template_becomes_global_and_cannot_be_deleted(dashboard):
    server, _, _ = dashboard

    _, first_created = request_json(
        server,
        "/api/workbench/documents/create",
        method="POST",
        payload={"name": "First"},
    )
    first = first_created["document"]
    private_template = first["template"]

    _, second_created = request_json(
        server,
        "/api/workbench/documents/create",
        method="POST",
        payload={"name": "Second"},
    )
    second = second_created["document"]

    status, reassigned = request_json(
        server,
        "/api/workbench/meta",
        method="POST",
        payload={
            "resource_id": second["id"],
            "template_id": private_template["id"],
        },
    )
    assert status == 200
    shared_template = next(
        item for item in reassigned["state"]["templates"] if item["id"] == private_template["id"]
    )
    assert shared_template["visibility"] == "global"
    assert shared_template["owner_id"] is None

    status, blocked = request_json(
        server,
        "/api/workbench/delete",
        method="POST",
        payload={"resource_id": private_template["id"]},
    )
    assert status == 400
    assert blocked["error"] == "Template is used by 2 Documents"


def test_native_workbench_routes_are_scoped_to_active_user(dashboard):
    server, _, user_data = dashboard
    owner_id = user_data.create_user("Document Owner")
    user_data.switch_user(owner_id)

    status, created = request_json(
        server,
        "/api/workbench/documents/create",
        method="POST",
        payload={"name": "Owner Document"},
    )
    assert status == 200
    owner_document = created["document"]

    status, owner_state = request_json(server, "/api/workbench/state")
    assert status == 200
    assert [item["id"] for item in owner_state["workbench"]["documents"]] == [owner_document["id"]]

    other_id = user_data.create_user("Document Other")
    assert int(user_data.read()["active_user_id"]) == other_id

    status, other_state = request_json(server, "/api/workbench/state")
    assert status == 200
    assert other_state["workbench"]["documents"] == []
    assert other_state["workbench"]["resources"] == []

    status, response = request_json(
        server,
        "/api/workbench/meta",
        method="POST",
        payload={"resource_id": owner_document["id"], "name": "Cross-user rename"},
    )
    assert status == 400
    assert response["error"] == "Workbench resource was not found"


def test_native_workbench_routing_contract(dashboard):
    server, _, _ = dashboard

    _, created = request_json(
        server,
        "/api/workbench/documents/create",
        method="POST",
        payload={"name": "Platform Resume"},
    )
    document = created["document"]

    status, initial = request_json(server, "/api/workbench/routing")
    assert status == 200
    assert initial == {
        "rules": [],
        "default_document_id": "",
        "default_document_ids": [],
    }

    status, saved = request_json(
        server,
        "/api/workbench/routing/save",
        method="POST",
        payload={
            "rules": [
                {
                    "id": "architecture",
                    "label": "Architecture",
                    "priority": 20,
                    "keywords": ["architect"],
                    "document_id": document["id"],
                }
            ],
            "default_document_id": document["id"],
        },
    )
    assert status == 200
    assert saved["routing"]["default_document_id"] == document["id"]
    assert saved["routing"]["default_document_ids"] == [document["id"]]
    assert saved["routing"]["rules"][0]["document_id"] == document["id"]
    assert saved["routing"]["rules"][0]["document_ids"] == [document["id"]]

    status, current = request_json(server, "/api/workbench/routing")
    assert status == 200
    assert current == saved["routing"]
