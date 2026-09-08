from __future__ import annotations

import json
from urllib.request import urlopen

import pytest

from jaw.database import JobDatabase
from jaw.keyboard_layouts import (
    BUILTIN_KEYBOARD_LAYOUTS,
    DEFAULT_KEYBOARD_LAYOUT,
    KEYBIND_POSITION_MODEL,
    canonical_keyboard_layout,
    layout_key_bindings_to_positions,
    normalize_custom_layouts,
    position_bindings_to_layout_keys,
    resolve_keyboard_layout,
)
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer


def test_qwerty_is_the_first_run_default(tmp_path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    data = store.read()

    assert data["keyboard_layout"] == DEFAULT_KEYBOARD_LAYOUT == "qwerty"
    assert resolve_keyboard_layout(data["keyboard_layout"])[1] == ["Q", "W", "E", "R", "T"]


def test_builtin_layout_catalog_contains_qwerty_and_colemak_dh():
    assert list(BUILTIN_KEYBOARD_LAYOUTS) == ["qwerty", "colemak-dh"]
    assert resolve_keyboard_layout("qwerty")[2] == ["A", "S", "D", "F", "G"]
    assert resolve_keyboard_layout("colemak-dh")[1] == ["Q", "W", "F", "P", "B"]
    assert resolve_keyboard_layout("missing") == resolve_keyboard_layout("qwerty")


def test_reserved_builtin_names_are_not_custom_layouts():
    rows = [["1", "2", "3", "4", "5"], ["Q", "W", "E", "R", "T"], ["A", "S", "D", "F", "G"], ["Z", "X", "C", "V", "B"]]
    custom = normalize_custom_layouts(
        {
            "QWERTY": rows,
            "colemak-dh": rows,
            "My Grid": rows,
        }
    )

    assert list(custom) == ["My Grid"]
    assert canonical_keyboard_layout("my grid", custom) == "My Grid"


def test_custom_layout_normalization_deduplicates_physical_keys():
    custom = normalize_custom_layouts(
        {
            "Duplicate": [
                ["1", "1", "3", "4", "5"],
                ["Q", "W", "E", "R", "T"],
                ["A", "S", "D", "F", "G"],
                ["Z", "X", "C", "V", "B"],
            ]
        }
    )

    assert custom["Duplicate"][0] == ["1", "", "3", "4", "5"]


def test_persistence_strips_old_builtin_custom_copies(tmp_path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    data = store.read()
    rows = resolve_keyboard_layout("qwerty")
    data["keybinds"]["custom_layouts"] = {
        "colemak-dh": rows,
        "Personal": rows,
    }
    store.write(data)

    saved = store.read()
    assert "colemak-dh" not in saved["keybinds"]["custom_layouts"]
    assert "Personal" in saved["keybinds"]["custom_layouts"]


def test_deleting_selected_custom_layout_falls_back_to_qwerty(tmp_path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    payload = store.read()["keybinds"]
    payload["custom_layouts"] = {"Personal": resolve_keyboard_layout("colemak-dh")}
    store.save_keybinds(payload)
    store.set_keyboard_layout("Personal")
    assert store.read()["keyboard_layout"] == "Personal"

    payload = store.read()["keybinds"]
    payload["custom_layouts"] = {}
    store.save_keybinds(payload)

    assert store.read()["keyboard_layout"] == "qwerty"


def test_invalid_layout_selection_is_rejected(tmp_path):
    store = UserDataStore(tmp_path / "data" / "jaw.db")
    with pytest.raises(ValueError, match="Unsupported keyboard layout"):
        store.set_keyboard_layout("dvorak")


def test_keybind_api_publishes_builtin_layout_catalog(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    database = JobDatabase(database_path)
    UserDataStore(database_path)
    server = DashboardServer(database, port=0, user_data_path=database_path)
    server.start()
    try:
        with urlopen(f"{server.url}/api/keybinds", timeout=5) as response:
            payload = json.load(response)
    finally:
        server.stop()

    assert payload["default_layout"] == "qwerty"
    assert payload["keyboard_layout"] == "qwerty"
    assert payload["builtin_layout_labels"] == {
        "qwerty": "QWERTY",
        "colemak-dh": "Colemak-DH",
    }
    assert payload["builtin_layouts"]["qwerty"][1] == ["Q", "W", "E", "R", "T"]
    assert payload["builtin_layouts"]["colemak-dh"][1] == ["Q", "W", "F", "P", "B"]
    assert "qwerty" not in payload["custom_layouts"]
    assert "colemak-dh" not in payload["custom_layouts"]


def test_physical_bindings_materialize_at_same_positions_across_layouts():
    slots = {
        "P12": "previous_iterator",
        "P13": "iterate_work_exp",
        "P23": "iterate_skills",
        "P24": "smart_capture",
    }
    qwerty = position_bindings_to_layout_keys(
        slots,
        resolve_keyboard_layout("qwerty"),
    )
    colemak = position_bindings_to_layout_keys(
        slots,
        resolve_keyboard_layout("colemak-dh"),
    )

    assert qwerty == {
        "E": "previous_iterator",
        "R": "iterate_work_exp",
        "F": "iterate_skills",
        "G": "smart_capture",
    }
    assert colemak == {
        "F": "previous_iterator",
        "P": "iterate_work_exp",
        "T": "iterate_skills",
        "G": "smart_capture",
    }
    assert layout_key_bindings_to_positions(
        colemak,
        resolve_keyboard_layout("colemak-dh"),
    ) == slots


def test_switching_layout_changes_runtime_keys_not_persisted_positions(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    store = UserDataStore(database_path)
    before = store.read()["keybinds"]
    assert before["binding_model"] == KEYBIND_POSITION_MODEL
    assert before["base"]["P12"] == "previous_iterator"
    assert before["base"]["P13"] == "iterate_work_exp"

    store.set_keyboard_layout("colemak-dh")
    after = store.read()
    assert after["keyboard_layout"] == "colemak-dh"
    assert after["keybinds"]["base"] == before["base"]

    from jaw.config import load_config

    config = load_config(tmp_path / "config.toml")
    assert config.matrix["F"].partition("|")[0] == "previous_iterator"
    assert config.matrix["P"].partition("|")[0] == "iterate_work_exp"
    assert config.matrix["T"].partition("|")[0] == "iterate_skills"
    assert config.matrix["G"].partition("|")[0] == "smart_capture"
