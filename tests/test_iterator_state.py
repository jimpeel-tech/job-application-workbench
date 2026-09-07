from jaw.desktop.iterator_state import (
    clone_iterator_preferences,
    cyclic_enabled_index,
    disabled_iterator_items,
    enabled_iterator_sequence,
    next_cyclic_index,
    ordered_iterator_sequence,
    set_iterator_order,
    toggle_iterator_item,
)


def test_saved_order_is_a_projection_over_the_current_sequence() -> None:
    preferences = {
        "contact": {
            "order": ["email", "removed", "first_name"],
            "disabled": [],
        }
    }

    assert ordered_iterator_sequence(
        preferences,
        "contact",
        ["first_name", "last_name", "email", "email"],
    ) == ["email", "first_name", "last_name"]


def test_enabled_sequence_respects_order_and_disabled_items() -> None:
    preferences = {
        "links": {
            "order": ["github", "linkedin", "portfolio"],
            "disabled": ["linkedin", "stale"],
        }
    }

    assert disabled_iterator_items(preferences, "links") == {"linkedin", "stale"}
    assert enabled_iterator_sequence(
        preferences,
        "links",
        ["linkedin", "portfolio", "github"],
    ) == ["github", "portfolio"]


def test_toggle_returns_an_independent_preference_snapshot() -> None:
    original = {
        "contact": {"order": ["email"], "disabled": ["phone"]},
        "links": {"order": [], "disabled": []},
    }

    disabled = toggle_iterator_item(original, "contact", "email")
    enabled = toggle_iterator_item(disabled, "contact", "phone")

    assert original["contact"]["disabled"] == ["phone"]
    assert disabled_iterator_items(disabled, "contact") == {"phone", "email"}
    assert disabled_iterator_items(enabled, "contact") == {"email"}
    assert enabled["links"] == original["links"]
    assert enabled["links"] is not original["links"]


def test_set_order_preserves_disabled_items_without_mutating_source() -> None:
    original = {"address": {"order": ["city"], "disabled": ["country"]}}

    updated = set_iterator_order(original, "address", ["zip", "city"])

    assert original["address"]["order"] == ["city"]
    assert updated["address"] == {
        "order": ["zip", "city"],
        "disabled": ["country"],
    }
    assert clone_iterator_preferences(updated) == updated


def test_next_cyclic_index_wraps_and_can_return_current_item() -> None:
    values = [False, True, False]

    assert next_cyclic_index(values, 1, bool) == 1
    assert next_cyclic_index(values, 2, bool) == 1


def test_next_cyclic_index_returns_none_when_no_value_is_enabled() -> None:
    assert next_cyclic_index([], 0, bool) is None
    assert next_cyclic_index([False, False], 0, bool) is None


def test_cyclic_enabled_index_moves_both_directions_and_skips_disabled() -> None:
    values = [True, False, True]

    assert cyclic_enabled_index(values, 0, 1, bool) == 2
    assert cyclic_enabled_index(values, 0, -1, bool) == 2
    assert cyclic_enabled_index(values, 2, -1, bool) == 0
    assert cyclic_enabled_index(values, 2, 1, bool) == 0
    assert cyclic_enabled_index(values, 0, 0, bool) is None
