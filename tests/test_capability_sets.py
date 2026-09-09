from __future__ import annotations

from pathlib import Path

import pytest

from jaw.application.capability_service import CAPABILITY_SCHEMA, CapabilityService
from jaw.config import RATEABLE_ENTITY_TYPES as CONFIG_RATEABLE_ENTITY_TYPES
from jaw.documents.expression_context import build_cap_projection
from jaw.userdata import SYSTEM_SET_ALL, UserDataStore


def test_capability_set_schema_is_first_class_but_not_generic_capability_create() -> None:
    entity_types = {item["value"]: item for item in CAPABILITY_SCHEMA["entity_types"]}
    assert set(entity_types) == {"competency", "technology", "product", "set"}
    assert "role" not in entity_types
    assert "tool" not in entity_types
    assert entity_types["set"]["rateable"] is False
    assert entity_types["set"]["creatable"] is False


def test_legacy_tool_entity_type_is_rejected(tmp_path: Path) -> None:
    store = UserDataStore(tmp_path / "jaw.db")
    with pytest.raises(ValueError, match="Unsupported entity type: tool"):
        store.upsert_entity(
            {
                "type": "tool",
                "canonical_name": "Legacy Tool",
                "display_name": "Legacy Tool",
            }
        )


def test_capability_projections_have_no_legacy_role_or_tool_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    config_source = (root / "src/jaw/config.py").read_text(encoding="utf-8")
    document_source = (
        root / "src/jaw/documents/expression_context.py"
    ).read_text(encoding="utf-8")

    assert CONFIG_RATEABLE_ENTITY_TYPES == frozenset(
        {"competency", "technology", "product"}
    )
    assert '"tool": "Products & Tools"' not in config_source
    assert "for role in set_entities" not in config_source
    assert "role = self.active_set" not in config_source
    assert '{"role", "set"}' not in document_source


def test_documents_projects_canonical_capability_sets() -> None:
    projection = build_cap_projection(
        {
            "capability_model": {
                "entities": [
                    {
                        "id": "set_sre",
                        "type": "set",
                        "display_name": "Platform & SRE",
                        "canonical_name": "Platform & SRE",
                    },
                    {
                        "id": "cap_k8s",
                        "type": "technology",
                        "display_name": "Kubernetes",
                        "canonical_name": "Kubernetes",
                        "rating": 4,
                    },
                ],
                "relationships": [
                    {
                        "source_id": "cap_k8s",
                        "type": "relevant_to",
                        "target_id": "set_sre",
                    }
                ],
            }
        }
    )

    assert [item["name"] for item in projection["all"]] == ["Kubernetes"]
    assert projection["sets"]["platform_sre"][0]["name"] == "Kubernetes"


def test_capability_set_ui_has_dedicated_editor_and_reuses_hierarchy() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "src/jaw/dashboard.html").read_text(encoding="utf-8")
    javascript = (root / "src/jaw/dashboard.js").read_text(encoding="utf-8")

    entity_select = html.split('id="capEntityType"', 1)[1].split("</select>", 1)[0]
    assert 'value="set"' not in entity_select
    assert 'id="capSetDialog"' in html
    assert 'id="capSetName"' in html
    assert 'id="capSetDocument"' in html
    assert 'id="capSetPaste"' in html
    assert "function renderSetView()" in javascript
    assert "renderProjectedHierarchy(items, sectionLevel, entityLevel)" in javascript
    assert "capHierarchyControls').hidden = !['hierarchy', 'set'].includes(capabilityView)" in javascript
    assert "openCapabilitySetDialog" in javascript
    assert "capEditSet" in javascript
    assert 'legacy-capability-tab' not in html
    assert 'id="skillsView"' not in html
    assert 'id="bulkDialog"' not in html
    assert '/api/skills' not in javascript
    assert '/api/organization' not in javascript
    assert 'skillTipsPanel' not in javascript
    assert 'renderSkills' not in javascript


def test_desktop_capability_set_selector_is_id_driven() -> None:
    root = Path(__file__).resolve().parents[1]
    main = (root / "src/jaw/main.py").read_text(encoding="utf-8")
    styles = (root / "src/jaw/desktop/styles.py").read_text(encoding="utf-8")

    assert 'setObjectName("statusCapabilitySet")' in main
    assert "QToolButton#statusCapabilitySet" in styles
    assert "QToolButton#statusRole" not in styles
    assert "currentIndexChanged.connect(self._set_paste_set)" in main
    assert "self.set_selector.findData(self.config.active_set_id)" in main
    assert "self.user_store.set_active_set_id(set_id)" in main
    assert "not capability_set.paste_enabled" in main
    assert "not capability_set.system and capability_set.paste_enabled" in main
    assert "self.user_store.set_active_set(role)" not in main


def test_capability_set_usage_flags_control_documents_and_paste(tmp_path: Path) -> None:
    store = UserDataStore(tmp_path / "jaw.db")
    store.clear_capabilities()
    capability = store.upsert_entity(
        {
            "id": "cap_k8s",
            "type": "technology",
            "canonical_name": "Kubernetes",
            "display_name": "Kubernetes",
            "rating": 4,
        }
    )
    service = CapabilityService(store)

    document_set = service.save_set(
        "",
        "Document Set",
        [capability["id"]],
        document_enabled=True,
        paste_enabled=False,
    )
    paste_set = service.save_set(
        "",
        "Paste Set",
        [capability["id"]],
        document_enabled=False,
        paste_enabled=True,
    )
    default_set = service.save_set("", "Both Set", [capability["id"]])

    by_id = {item["id"]: item for item in service.state()["sets"]}
    assert by_id[document_set]["document_enabled"] is True
    assert by_id[document_set]["paste_enabled"] is False
    assert by_id[paste_set]["document_enabled"] is False
    assert by_id[paste_set]["paste_enabled"] is True
    assert by_id[default_set]["document_enabled"] is True
    assert by_id[default_set]["paste_enabled"] is True

    projection = build_cap_projection(store.read())
    assert "document_set" in projection["sets"]
    assert "paste_set" not in projection["sets"]
    assert "both_set" in projection["sets"]
    all_names = [item["name"] for item in projection["all"]]
    assert "Kubernetes" in all_names
    assert "Document Set" not in all_names
    assert "Paste Set" not in all_names
    assert "Both Set" not in all_names

    with pytest.raises(ValueError, match="not enabled for Paste"):
        store.set_active_set_id(document_set)

    store.set_active_set_id(paste_set)
    assert store.read()["capability_model"]["active_set_id"] == paste_set

    service.save_set(
        paste_set,
        "Paste Set",
        [capability["id"]],
        document_enabled=False,
        paste_enabled=False,
    )
    assert store.read()["capability_model"]["active_set_id"] == SYSTEM_SET_ALL
