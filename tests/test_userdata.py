import json
from pathlib import Path

import pytest

from jaw.config import DEFAULT_MATRIX_BASE, DEFAULT_MATRIX_LAYER2, load_config
from jaw.userdata import (
    DEFAULT_USER_TEMPLATE_PATH,
    JOB_MATCHING_SELECTION,
    SYSTEM_SET_ALL,
    UserDataStore,
    initial_keybinds,
    normalize_layer_bindings,
)


def seed(path: Path) -> UserDataStore:
    store = UserDataStore(path)
    state = store.empty_state()
    state["capability_model"] = {
        "version": 2,
        "entities": [
            {
                "id": "cap_kubernetes",
                "type": "technology",
                "canonical_name": "Kubernetes",
                "display_name": "Kubernetes",
                "aliases": ["K8s"],
                "rating": 3,
                "match_enabled": True,
                "iterator_enabled": True,
            },
            {
                "id": "cap_prometheus",
                "type": "product",
                "canonical_name": "Prometheus",
                "display_name": "Prometheus",
                "aliases": [],
                "rating": 3,
                "match_enabled": True,
                "iterator_enabled": True,
            },
        ],
        "relationships": [
            {
                "source_id": "cap_prometheus",
                "type": "uses",
                "target_id": "cap_kubernetes",
            }
        ],
        "active_set_id": SYSTEM_SET_ALL,
        "view_preferences": {
            "hierarchy": {
                "section_granularity": 3,
                "entity_granularity": 3,
                "projection": {
                    "version": 3,
                    "source": "test",
                    "tree": {
                        "name": "Capabilities",
                        "entity_ids": [],
                        "children": [
                            {
                                "name": "Platform Engineering",
                                "entity_ids": [
                                    "cap_kubernetes",
                                    "cap_prometheus",
                                ],
                                "children": [],
                            }
                        ],
                    },
                },
            },
            "layout": {
                "left_pane": "fixed",
                "right_pane": "fixed",
                "show_use_guide": True,
            },
        },
    }
    store.write(state)
    return store


def entities_by_id(store: UserDataStore) -> dict[str, dict]:
    return {
        entity["id"]: entity
        for entity in store.read()["capability_model"]["entities"]
    }


def test_cycle_layers_reserves_its_key_and_retired_toggles_are_removed():
    cleaned = normalize_layer_bindings({
        "base": {"1": "cycle_layers", "2": "layer2_toggle"},
        "layer2": {"1": "iterate_skills", "3": "layer3_toggle"},
        "layer3": {"1": "cycle_date_format"},
        "action_displays": {
            "cycle_layers": {"label": "Layers"},
            "layer2_toggle": {"label": "Layer 2"},
        },
    })

    assert cleaned["base"] == {"1": "cycle_layers"}
    assert "1" not in cleaned["layer2"]
    assert "1" not in cleaned["layer3"]
    assert "2" not in cleaned["base"]
    assert "3" not in cleaned["layer2"]
    assert "layer2_toggle" not in cleaned["action_displays"]


def test_first_run_uses_seeded_demo_template(tmp_path: Path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    data = store.read()
    template = json.loads(
        DEFAULT_USER_TEMPLATE_PATH.read_text(encoding="utf-8")
    )

    assert data["active_user_name"] == "Ol Sarge"
    assert template["version"] == 4
    assert data["capability_model"]["version"] == 2
    assert data["capability_model"]["entities"] == []
    assert data["capability_model"]["relationships"] == []
    assert data["capability_model"]["active_set_id"] == SYSTEM_SET_ALL
    assert data["user"] == template["user"]
    assert [entry["company"] for entry in data["work_history"]] == [
        "Reveille Systems",
        "Maroon Stack Labs",
        "Brazos Byteworks",
    ]
    assert data["work_history"] == template["work_history"]
    assert data["custom_fields"] == []
    assert data["custom_actions"] == []
    assert data["iterator_preferences"] == {}
    assert data["answers"] == []
    assert data["keyboard_layout"] == "qwerty"
    assert data["keybinds"]["binding_model"] == "physical-v1"

    expected_base = {'P00': 'open_dashboard', 'P01': 'analyze_job', 'P02': 'find_company', 'P03': 'toggle_answers', 'P04': 'toggle_keyboard', 'P10': 'country', 'P11': 'iterate_contact', 'P12': 'previous_iterator', 'P13': 'iterate_work_exp', 'P14': 'iterate_links', 'P20': 'layer3_hold', 'P21': 'iterate_address', 'P22': 'next_iterator', 'P23': 'iterate_skills', 'P24': 'smart_capture', 'P30': 'linkedin', 'P31': 'portfolio', 'P32': 'full_name', 'P33': 'phone', 'P34': 'email'}
    expected_layer2 = {'P00': 'cycle_date_format', 'P01': 'cycle_name_format', 'P10': 'address', 'P11': 'city', 'P12': 'move_up_or_relay', 'P13': 'previous_work_exp', 'P20': 'state', 'P21': 'zip', 'P22': 'move_down_or_relay', 'P23': 'next_work_exp', 'P24': 'github', 'P30': 'facebook', 'P31': 'x', 'P32': 'first_name', 'P33': 'last_name'}
    assert data["keybinds"]["base"] == expected_base
    assert data["keybinds"]["layer2"] == expected_layer2
    assert data["keybinds"]["layer3"] == {}
    assert DEFAULT_MATRIX_BASE == expected_base
    assert DEFAULT_MATRIX_LAYER2 == expected_layer2
    assert initial_keybinds()["base"] == expected_base
    assert initial_keybinds()["layer2"] == expected_layer2

    displays = data["keybinds"]["action_displays"]
    assert displays["find_company"] == {"label": "Search", "icons": ["brief"]}
    assert displays["analyze_job"]["icons"] == ["brief"]
    assert displays["toggle_answers"]["icons"] == ["paste"]
    assert displays["previous_work_exp"]["icons"] == ["iterate", "arrow_up"]
    assert displays["next_work_exp"]["icons"] == ["iterate", "arrow_down"]

    # First-run state remains stable after persistence.
    persisted = UserDataStore(store.path).read()
    assert persisted["user"] == template["user"]
    assert persisted["work_history"] == template["work_history"]
    assert persisted["capability_model"]["entities"] == []
    assert persisted["keybinds"]["base"] == expected_base


def test_default_bindings_do_not_reference_retired_actions(tmp_path: Path):
    data = UserDataStore(tmp_path / "data" / "jaw.db").read()
    obsolete = {
        "select_titles", "select_job_info", "iterate_job_info", "exit_edit",
        "toggle_move", "set_iterator", "reset_workflow",
    }
    keybinds = data["keybinds"]
    assigned = {
        action
        for layer in ("base", "layer2", "layer3")
        for action in keybinds[layer].values()
    }
    assert not assigned & obsolete
    assert not set(keybinds.get("action_displays", {})) & obsolete


def test_database_schema_version_is_set(tmp_path: Path):
    import sqlite3

    from jaw.paths import DATABASE_SCHEMA_VERSION

    path = tmp_path / "data" / "jaw.db"
    UserDataStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == DATABASE_SCHEMA_VERSION


def test_hierarchy_projection_changes_do_not_mutate_the_capability_graph(
    tmp_path: Path,
):
    store = seed(tmp_path / "data" / "jaw.db")
    before = store.read()["capability_model"]
    projection = before["view_preferences"]["hierarchy"]["projection"]

    store.save_view_preferences({
        "hierarchy": {
            "section_granularity": 5,
            "entity_granularity": 1,
            "projection": projection,
        },
        "layout": {
            "left_pane": "auto",
            "right_pane": "off",
            "show_use_guide": False,
        },
    })
    after = store.read()["capability_model"]

    assert after["entities"] == before["entities"]
    assert after["relationships"] == before["relationships"]
    assert after["view_preferences"]["hierarchy"]["projection"] == projection
    assert after["view_preferences"]["hierarchy"]["section_granularity"] == 5
    assert after["view_preferences"]["hierarchy"]["entity_granularity"] == 1

    leaf_ids = projection["tree"]["children"][0]["entity_ids"]
    assert set(leaf_ids) == {"cap_kubernetes", "cap_prometheus"}


def test_analysis_settings_are_per_user(tmp_path: Path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    store.save_analysis_settings("local", "openai", "gpt-5.6-luna")
    assert store.read()["analysis_settings"] == {
        "mode": "local",
        "provider": "openai",
        "model": "gpt-5.6-luna",
    }
    second_id = store.create_user("Second", False)
    store.switch_user(second_id)
    assert store.read()["analysis_settings"] == {
        "mode": "generative",
        "provider": "openai",
        "model": "gpt-5.6-terra",
    }


def test_analysis_settings_accept_local_ollama_provider(tmp_path: Path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")

    store.save_analysis_settings("generative", "ollama", "qwen3:14b")

    assert store.read()["analysis_settings"] == {
        "mode": "generative",
        "provider": "ollama",
        "model": "qwen3:14b",
    }


def test_name_format_is_saved_per_user(tmp_path: Path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    assert store.read()["name_format"] == "first_last"
    store.set_name_format("full")
    assert store.read()["name_format"] == "full"
    second_id = store.create_user("Second", False)
    store.switch_user(second_id)
    assert store.read()["name_format"] == "first_last"


def test_rating_matching_and_iterator_state_are_independent(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    store.upsert_entity({"id": "cap_kubernetes", "rating": 5})
    store.set_entity_match_enabled("cap_kubernetes", False)

    kubernetes = entities_by_id(store)["cap_kubernetes"]
    assert kubernetes["rating"] == 5
    assert kubernetes["match_enabled"] is False
    assert kubernetes["iterator_enabled"] is True

    store.set_entity_iterator_enabled("cap_kubernetes", False)
    kubernetes = entities_by_id(store)["cap_kubernetes"]
    assert kubernetes["rating"] == 5
    assert kubernetes["match_enabled"] is False
    assert kubernetes["iterator_enabled"] is False

    prometheus = entities_by_id(store)["cap_prometheus"]
    assert prometheus["match_enabled"] is True
    assert prometheus["iterator_enabled"] is True


def test_upsert_rename_keeps_stable_entity_id_and_relationships(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    before = list(store.read()["relationships"])

    updated = store.upsert_entity({
        "id": "cap_prometheus",
        "display_name": "Prometheus Server",
        "aliases": ["Prom"],
    })

    assert updated["id"] == "cap_prometheus"
    assert updated["canonical_name"] == "Prometheus"
    assert updated["display_name"] == "Prometheus Server"
    assert store.read()["relationships"] == before


def test_sets_and_capabilities_have_independent_name_namespaces(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    capability = store.upsert_entity({
        "id": "cap_sre",
        "type": "competency",
        "canonical_name": "Site Reliability Engineering",
        "display_name": "Site Reliability Engineering",
        "aliases": ["SRE"],
    })
    capability_set = store.upsert_entity({
        "id": "set_sre",
        "type": "set",
        "canonical_name": "SRE",
        "display_name": "SRE",
    })

    assert capability["id"] != capability_set["id"]
    assert entities_by_id(store)["cap_sre"]["aliases"] == ["SRE"]
    assert entities_by_id(store)["set_sre"]["display_name"] == "SRE"


def test_set_membership_uses_entity_ids_and_cascades_on_delete(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    store.upsert_entity({
        "id": "set_platform",
        "type": "set",
        "canonical_name": "Platform Engineer",
        "display_name": "Platform Engineer",
    })
    store.save_capability_set(
        "set_platform",
        "Platform Engineer",
        ["cap_kubernetes", "cap_prometheus"],
    )
    store.set_active_set_id("set_platform")

    store.upsert_entity({
        "id": "cap_kubernetes",
        "display_name": "Kubernetes Platform",
    })
    data = store.read()
    membership = {
        relationship["source_id"]
        for relationship in data["relationships"]
        if relationship["type"] == "relevant_to"
        and relationship["target_id"] == "set_platform"
    }
    assert membership == {"cap_kubernetes", "cap_prometheus"}
    assert data["capability_model"]["active_set_id"] == "set_platform"

    store.delete_entities_by_id(["cap_prometheus"])
    data = store.read()
    assert "cap_prometheus" not in {entity["id"] for entity in data["entities"]}
    assert all(
        relationship["source_id"] != "cap_prometheus"
        and relationship["target_id"] != "cap_prometheus"
        for relationship in data["relationships"]
    )
    remaining_members = {
        relationship["source_id"]
        for relationship in data["relationships"]
        if relationship["type"] == "relevant_to"
        and relationship["target_id"] == "set_platform"
    }
    assert remaining_members == {"cap_kubernetes"}
    assert entities_by_id(store)["cap_kubernetes"]["display_name"] == "Kubernetes Platform"


def test_config_uses_sibling_user_data(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    store = seed(tmp_path / "data" / "jaw.db")
    store.save_user({
        "first_name": "Jane", "last_name": "Example",
        "phone_number": "555-555-0100", "country": "United States",
    })
    sre_set_id = store.save_capability_set("", "SRE", ["cap_kubernetes"])
    store.set_active_set_id(sre_set_id)
    store.save_custom_fields([
        {"id": "clearance", "label": "Clearance", "value": "Public Trust"},
        {"id": "sponsorship", "label": "Sponsorship", "value": "Not required"},
    ])
    store.save_custom_actions([
        {
            "id": "custom_action_clearance", "label": "Paste Clearance",
            "type": "single", "field_ids": ["clearance"],
        },
        {
            "id": "custom_action_application", "label": "Application Data",
            "type": "iterator", "field_ids": ["clearance", "sponsorship"],
            "auto_return": True,
        },
    ])
    config = load_config(config_path)
    assert config.active_sets == ["SRE"]
    assert config.effective_skills == ["Kubernetes"]
    values = {item.item_id: item.value for item in config.profile_items}
    assert values["first_name"] == "Jane"
    assert values["last_name"] == "Example"
    assert values["full_name"] == "Jane Example"
    assert values["phone"] == "555-555-0100"
    assert values["country"] == "United States"
    assert values["custom_action_clearance"] == "Public Trust"
    assert config.custom_sequences["custom_action_application"] == [
        "clearance", "sponsorship",
    ]
    assert config.action_labels["custom_action_application"] == "Application Data"
    assert config.custom_action_auto_return["custom_action_application"] is True
    store.set_name_format("full")
    full_name_config = load_config(config_path)
    assert full_name_config.name_format == "full"
    assert full_name_config.sequences["Q"] == ["full_name", "phone"]


def test_multiple_users_are_isolated(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    original_id = store.read()["active_user_id"]
    second_id = store.create_user("Test User")
    assert store.read()["active_user_id"] == second_id
    assert [
        entity for entity in store.read()["entities"] if entity["type"] != "set"
    ] == []
    store.switch_user(original_id)
    assert {
        entity["display_name"]
        for entity in store.read()["entities"]
        if entity["type"] != "set"
    } == {"Kubernetes", "Prometheus"}


def test_bulk_add_and_merge_import_preserve_graph_identity(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    grafana = store.upsert_entity({
        "type": "product",
        "canonical_name": "Grafana",
        "display_name": "Grafana",
    })
    loki = store.upsert_entity({
        "type": "technology",
        "canonical_name": "Loki",
        "display_name": "Loki",
    })
    grafana_id = grafana["id"]
    loki_id = loki["id"]
    store.save_relationships([{
        "source_id": grafana_id,
        "type": "related_to",
        "target_id": loki_id,
    }])
    exported = store.export_data()
    store.delete_entities_by_id([grafana_id, loki_id])
    store.import_data(exported, "merge")
    store.import_data(exported, "merge")

    restored = store.read()["capability_model"]
    assert {grafana_id, loki_id} <= {
        entity["id"] for entity in restored["entities"]
    }
    assert restored["relationships"].count({
        "source_id": grafana_id,
        "type": "related_to",
        "target_id": loki_id,
    }) == 1


def test_version_4_export_restores_complete_user_workspace(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    store.save_user({"first_name": "Example", "email": "example@example.test"})
    store.save_custom_fields([{
        "id": "clearance", "label": "Clearance", "value": "Public Trust",
        "type": "multi",
    }])
    store.save_custom_actions([{
        "id": "custom_action_clearance", "label": "Clearance Details",
        "type": "single", "field_ids": ["clearance"], "auto_return": True,
    }])
    store.save_work_history([{
        "title": "SRE", "company": "Example", "start": "2024", "end": "2025",
        "highlights": "Improved reliability",
    }])
    store.save_answers([{"title": "Why us?", "answer": "Because..."}])
    store.save_analysis_settings("local", "openai", "gpt-5.6-luna")
    store.set_name_format("full")
    store.set_keyboard_layout("qwerty")
    store.save_keybinds({"base": {"q": "custom_action_clearance"}})

    exported = store.export_data()
    assert exported["format"] == "jaw-user-data"
    assert exported["version"] == 4
    assert "capability_model" in exported
    assert "sections" not in exported
    assert "skills" not in exported
    assert "roles" not in exported

    restored_store = UserDataStore(tmp_path / "restored" / "jaw.db")
    restored_store.import_data(exported, "replace")
    restored = restored_store.export_data()
    for key in (
        "capability_model",
        "user",
        "custom_fields",
        "custom_actions",
        "work_history",
        "answers",
        "analysis_settings",
        "name_format",
        "keyboard_layout",
        "keybinds",
    ):
        assert restored[key] == exported[key]


def test_per_user_profile_work_answers_and_layout(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    store.save_custom_fields([{"id": "clearance", "label": "Clearance", "value": "Public Trust"}])
    store.save_work_history([{
        "title": "SRE", "company": "Example", "start": "2024", "end": "2025",
        "highlights": "Improved reliability",
    }])
    store.save_answers([{"title": "Why us?", "answer": "Because..."}])
    store.set_keyboard_layout("qwerty")
    data = store.read()
    assert data["custom_fields"][0]["id"] == "clearance"
    assert data["work_history"][0]["title"] == "SRE"
    assert data["answers"][0]["title"] == "Why us?"
    assert data["keyboard_layout"] == "qwerty"


def test_iterator_order_disabled_state_and_work_enabled_state_are_persistent(
    tmp_path: Path,
):
    store = seed(tmp_path / "data" / "jaw.db")
    store.save_iterator_preferences({
        "iterate_address": {
            "order": ["zip", "address", "city", "state", "country"],
            "disabled": ["country"],
        }
    })
    store.save_work_history([{
        "title": "SRE",
        "company": "Example",
        "start": "2024",
        "end": "2025",
        "highlights": "Improved reliability",
        "enabled": False,
    }])

    reloaded = UserDataStore(store.path).read()
    assert reloaded["iterator_preferences"]["iterate_address"] == {
        "order": ["zip", "address", "city", "state", "country"],
        "disabled": ["country"],
    }
    assert reloaded["work_history"][0]["enabled"] is False


def test_keybinds_are_saved_per_user_and_allow_custom_layouts(tmp_path: Path):
    store = seed(tmp_path / "data" / "jaw.db")
    store.save_keybinds({
        "base": {"q": "first_name", "w": "iterate_work_exp"},
        "layer2": {"space": "toggle_hotkeys"},
        "layer3": {"q": "email"},
        "hotkey_settings": {
            "toggle": "ALT+F12",
            "window": "CTRL+SHIFT+F1",
            "disable_when_minimized": True,
            "layers": {
                "layer2": {
                    "enabled": False, "hold": False,
                    "mode": "hold", "hotkey": "SHIFT",
                },
                "layer3": {"enabled": False, "mode": "toggle", "hotkey": "CTRL+3"},
            },
        },
        "action_displays": {
            "first_name": {"label": "Given name", "icons": ["paste"]},
        },
        "custom_layouts": {"My Layout": [["1", "2", "3", "4", "5"], ["Q", "W", "E", "R", "T"], ["A", "S", "D", "F", "G"], ["Z", "X", "C", "V", "B"]]},
    })
    store.set_keyboard_layout("My Layout")

    data = store.read()
    assert data["keybinds"]["configured"] is True
    assert data["keybinds"]["base"] == {"P10": "first_name", "P11": "iterate_work_exp"}
    assert data["keybinds"]["layer2"] == {}
    assert data["keybinds"]["layer3"] == {"P10": "email"}
    assert data["keybinds"]["hotkey_settings"]["layers"] == {
        "layer2": {
            "enabled": False, "hold": False,
            "mode": "hold", "hotkey": "SHIFT",
        },
        "layer3": {"enabled": False},
    }
    assert data["keybinds"]["hotkey_settings"]["disable_when_minimized"] is True
    assert data["keybinds"]["action_displays"]["first_name"]["label"] == "Given name"
    assert data["keybinds"]["action_displays"]["first_name"]["icons"] == ["paste"]
    assert data["keybinds"]["custom_layouts"]["My Layout"] == [
        ["1", "2", "3", "4", "5"],
        ["Q", "W", "E", "R", "T"],
        ["A", "S", "D", "F", "G"],
        ["Z", "X", "C", "V", "B"],
    ]
    assert data["keyboard_layout"] == "My Layout"


def test_custom_field_id_is_generated_when_hidden_ui_omits_it(tmp_path: Path):
    store = UserDataStore(tmp_path / "users.db")
    store.save_custom_fields([{"label": "Favorite editor", "value": "VS Code"}])

    field = store.read()["custom_fields"][0]
    assert field["id"].startswith("custom_")
    assert field["label"] == "Favorite editor"


def test_custom_data_labels_are_case_insensitively_unique(tmp_path: Path):
    store = UserDataStore(tmp_path / "users.db")
    try:
        store.save_custom_fields([
            {"label": "Work Authorization", "value": "Yes"},
            {"label": " work authorization ", "value": "No"},
        ])
    except ValueError as error:
        assert "already in use" in str(error)
    else:
        raise AssertionError("Custom Data labels must be unique")


def test_custom_data_and_action_may_share_a_label(tmp_path: Path):
    store = UserDataStore(tmp_path / "users.db")
    store.save_custom_actions([{
        "id": "custom_action_details", "label": "Application Details",
        "type": "single", "field_ids": [],
    }])
    store.save_custom_fields([{
        "id": "details", "label": "application details", "value": "Text",
    }])
    data = store.read()
    assert data["custom_fields"][0]["label"] == "application details"
    assert data["custom_actions"][0]["label"] == "Application Details"


def test_custom_data_types_and_action_rename_keep_stable_id(tmp_path: Path):
    store = UserDataStore(tmp_path / "users.db")
    store.save_custom_fields([
        {"id": "short_value", "label": "Short", "value": "one line", "type": "single"},
        {"id": "long_value", "label": "Long", "value": "first\nsecond", "type": "multi"},
    ])
    store.save_custom_actions([{
        "id": "custom_action_stable", "label": "My Details",
        "type": "iterator", "field_ids": ["short_value", "long_value"],
    }])
    store.save_keybinds({"base": {"q": "custom_action_stable"}})
    store.save_custom_actions([{
        "id": "custom_action_stable", "label": "Application Details",
        "type": "iterator", "field_ids": ["short_value", "long_value"],
    }])

    data = store.read()
    assert [field["type"] for field in data["custom_fields"]] == ["single", "multi"]
    assert data["custom_actions"] == [{
        "id": "custom_action_stable", "label": "Application Details",
        "type": "iterator", "field_ids": ["short_value", "long_value"],
        "auto_return": False,
    }]
    assert data["keybinds"]["base"]["P10"] == "custom_action_stable"


def test_custom_action_labels_are_unique_and_delete_cleans_bindings(tmp_path: Path):
    store = UserDataStore(tmp_path / "users.db")
    store.save_custom_fields([
        {"id": "first", "label": "First", "value": "1"},
        {"id": "second", "label": "Second", "value": "2"},
    ])
    try:
        store.save_custom_actions([
            {"label": "Details", "type": "single", "field_ids": ["first"]},
            {"label": "details", "type": "single", "field_ids": ["second"]},
        ])
    except ValueError:
        pass
    else:
        raise AssertionError("Custom action labels must be case-insensitively unique")

    store.save_custom_actions([{
        "id": "custom_action_delete", "label": "Details",
        "type": "single", "field_ids": ["first", "second"],
    }])
    assert store.read()["custom_actions"][0]["field_ids"] == ["first"]
    store.set_custom_action_auto_returns({"custom_action_delete": True})
    assert store.read()["custom_actions"][0]["auto_return"] is True
    store.save_keybinds({"base": {"q": "custom_action_delete"}})
    store.save_custom_actions([])
    assert "Q" not in store.read()["keybinds"]["base"]


def test_custom_action_rejects_reserved_label_and_field_delete_cascades(tmp_path: Path):
    store = UserDataStore(tmp_path / "users.db")
    store.save_custom_fields([
        {"id": "first", "label": "First", "value": "1"},
        {"id": "second", "label": "Second", "value": "2"},
    ])
    try:
        store.save_custom_actions(
            [{"label": "Brief", "type": "iterator", "field_ids": ["first"]}],
            {"Brief"},
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Built-in action labels must be reserved")

    store.save_custom_actions([{
        "id": "custom_action_fields", "label": "Details",
        "type": "iterator", "field_ids": ["first", "second"],
    }])
    store.save_keybinds({
        "base": {"q": "first", "w": "custom_action_fields"},
        "action_displays": {"first": {"label": "First", "icons": []}},
    })
    store.save_custom_fields([
        {"id": "second", "label": "Second", "value": "2"},
    ])
    data = store.read()
    assert data["custom_actions"][0]["field_ids"] == ["second"]
    assert data["keybinds"]["base"] == {"P11": "custom_action_fields"}
    assert "first" not in data["keybinds"]["action_displays"]


def test_system_selections_map_to_independent_entity_flags(tmp_path: Path):
    store = seed(tmp_path / "matching.db")
    grafana = store.upsert_entity({
        "type": "product",
        "canonical_name": "Grafana",
        "display_name": "Grafana",
    })

    for entity_id in ("cap_kubernetes", "cap_prometheus", grafana["id"]):
        store.set_entity_iterator_enabled(entity_id, False)
        store.set_entity_match_enabled(entity_id, False)
    store.set_entity_iterator_enabled("cap_kubernetes", True)
    store.set_entity_match_enabled("cap_prometheus", True)

    by_name = {
        entity["display_name"]: entity
        for entity in store.read()["entities"]
        if entity["type"] != "set"
    }
    assert by_name["Kubernetes"]["iterator_enabled"] is True
    assert by_name["Kubernetes"]["match_enabled"] is False
    assert by_name["Prometheus"]["iterator_enabled"] is False
    assert by_name["Prometheus"]["match_enabled"] is True
    assert by_name["Grafana"]["iterator_enabled"] is False
    assert by_name["Grafana"]["match_enabled"] is False

    with pytest.raises(ValueError, match="set_id does not reference"):
        store.set_active_set_id(JOB_MATCHING_SELECTION)
