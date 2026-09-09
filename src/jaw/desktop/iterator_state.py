from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TypeVar

IteratorPreferences = Mapping[str, Mapping[str, Sequence[str]]]
MutableIteratorPreferences = dict[str, dict[str, list[str]]]

_T = TypeVar("_T")


def clone_iterator_preferences(
    preferences: IteratorPreferences,
) -> MutableIteratorPreferences:
    """Return the persisted iterator shape without sharing mutable lists."""
    return {
        action: {
            "order": list(value.get("order", [])),
            "disabled": list(value.get("disabled", [])),
        }
        for action, value in preferences.items()
    }


def ordered_iterator_sequence(
    preferences: IteratorPreferences,
    action: str,
    sequence: Sequence[str],
) -> list[str]:
    """Apply a saved order while retaining new and removing stale items."""
    preference = preferences.get(action, {})
    configured = list(dict.fromkeys(sequence))
    saved = [item for item in preference.get("order", []) if item in configured]
    return saved + [item for item in configured if item not in saved]


def disabled_iterator_items(
    preferences: IteratorPreferences,
    action: str,
) -> set[str]:
    return set(preferences.get(action, {}).get("disabled", []))


def enabled_iterator_sequence(
    preferences: IteratorPreferences,
    action: str,
    sequence: Sequence[str],
) -> list[str]:
    disabled = disabled_iterator_items(preferences, action)
    return [
        item
        for item in ordered_iterator_sequence(preferences, action, sequence)
        if item not in disabled
    ]


def enabled_position_for_item(
    preferences: IteratorPreferences,
    action: str,
    displayed_items: Sequence[str],
    item_id: str,
) -> int | None:
    """Map a clicked display item to its logical enabled iterator position."""
    disabled = disabled_iterator_items(preferences, action)
    enabled = [item for item in displayed_items if item and item not in disabled]
    try:
        return enabled.index(item_id)
    except ValueError:
        return None


def iterator_preview_rows(
    values: Sequence[str],
    current_index: int,
    radius: int = 2,
) -> tuple[tuple[str, int], ...]:
    """Return a bounded, non-wrapping preview around the active iterator item."""
    if not values or current_index < 0 or current_index >= len(values):
        return ()
    radius = max(0, int(radius))
    start = max(0, current_index - radius)
    stop = min(len(values), current_index + radius + 1)
    return tuple((str(values[index]), index - current_index) for index in range(start, stop))


def toggle_iterator_item(
    preferences: IteratorPreferences,
    action: str,
    item_id: str,
) -> MutableIteratorPreferences:
    """Toggle an item without mutating the configuration currently in use."""
    updated = clone_iterator_preferences(preferences)
    preference = updated.setdefault(action, {"order": [], "disabled": []})
    disabled = set(preference["disabled"])
    if item_id in disabled:
        disabled.remove(item_id)
    else:
        disabled.add(item_id)
    preference["disabled"] = list(disabled)
    return updated


def set_iterator_order(
    preferences: IteratorPreferences,
    action: str,
    order: Sequence[str],
) -> MutableIteratorPreferences:
    """Store a displayed order without changing its enablement state."""
    updated = clone_iterator_preferences(preferences)
    preference = updated.setdefault(action, {"order": [], "disabled": []})
    preference["order"] = list(order)
    return updated


def cyclic_enabled_index(
    values: Sequence[_T],
    current: int,
    direction: int,
    is_enabled: Callable[[_T], bool],
) -> int | None:
    """Find an enabled value in either direction, wrapping once."""
    count = len(values)
    if not count or direction == 0:
        return None
    step = 1 if direction > 0 else -1
    for offset in range(1, count + 1):
        index = (current + step * offset) % count
        if is_enabled(values[index]):
            return index
    return None


def next_cyclic_index(
    values: Sequence[_T],
    current: int,
    is_enabled: Callable[[_T], bool],
) -> int | None:
    """Find the next enabled value, wrapping once through the sequence."""
    return cyclic_enabled_index(values, current, 1, is_enabled)
