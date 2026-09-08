from __future__ import annotations

from typing import Any

DEFAULT_KEYBOARD_LAYOUT = "qwerty"

BUILTIN_KEYBOARD_LAYOUTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "qwerty": (
        ("1", "2", "3", "4", "5"),
        ("Q", "W", "E", "R", "T"),
        ("A", "S", "D", "F", "G"),
        ("Z", "X", "C", "V", "B"),
    ),
    "colemak-dh": (
        ("1", "2", "3", "4", "5"),
        ("Q", "W", "F", "P", "B"),
        ("A", "R", "S", "T", "G"),
        ("Z", "X", "C", "D", "V"),
    ),
}

BUILTIN_KEYBOARD_LAYOUT_LABELS = {
    "qwerty": "QWERTY",
    "colemak-dh": "Colemak-DH",
}

KEYBIND_POSITION_MODEL = "physical-v1"


def position_id(row: int, column: int) -> str:
    """Stable identifier for one physical cell in JAW's 4x5 matrix."""
    if not 0 <= row < 4 or not 0 <= column < 5:
        raise ValueError("Keyboard position is outside the 4x5 matrix")
    return f"P{row}{column}"


def is_position_id(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return (
        len(text) == 3
        and text.startswith("P")
        and text[1].isdigit()
        and text[2].isdigit()
        and 0 <= int(text[1]) < 4
        and 0 <= int(text[2]) < 5
    )


def layout_key_bindings_to_positions(
    bindings: Any,
    rows: list[list[str]],
) -> dict[str, str]:
    """Convert legacy key-name bindings to stable physical matrix positions."""
    incoming = {
        str(key).strip().upper(): str(action)
        for key, action in dict(bindings or {}).items()
    }
    result: dict[str, str] = {}
    for row_index in range(4):
        row = rows[row_index] if row_index < len(rows) else []
        for column_index in range(5):
            key = str(row[column_index] if column_index < len(row) else "").strip().upper()
            action = incoming.get(key, "") if key else ""
            if action:
                result[position_id(row_index, column_index)] = action
    return result


def position_bindings_to_layout_keys(
    bindings: Any,
    rows: list[list[str]],
) -> dict[str, str]:
    """Materialize physical bindings as the key names of a selected layout."""
    incoming = {
        str(slot).strip().upper(): str(action)
        for slot, action in dict(bindings or {}).items()
        if is_position_id(slot)
    }
    result: dict[str, str] = {}
    for row_index in range(4):
        row = rows[row_index] if row_index < len(rows) else []
        for column_index in range(5):
            key = str(row[column_index] if column_index < len(row) else "").strip().upper()
            action = incoming.get(position_id(row_index, column_index), "")
            if key and action:
                result[key] = action
    return result


def normalize_layout_rows(rows: Any) -> list[list[str]]:
    """Normalize a custom 4x5 matrix and remove duplicate physical keys."""
    if not isinstance(rows, list):
        return []

    normalized: list[list[str]] = []
    seen: set[str] = set()
    for source in rows[:4]:
        if not isinstance(source, list):
            continue
        row: list[str] = []
        for raw in source[:5]:
            value = str(raw).strip().upper()
            if len(value) != 1 or not value.isalnum() or value in seen:
                value = ""
            if value:
                seen.add(value)
            row.append(value)
        normalized.append(row)
    return normalized


def normalize_custom_layouts(raw: Any) -> dict[str, list[list[str]]]:
    """Keep only user-created layouts; built-in names are reserved."""
    if not isinstance(raw, dict):
        return {}

    result: dict[str, list[list[str]]] = {}
    used_names: set[str] = set()
    for raw_name, rows in raw.items():
        name = str(raw_name).strip()
        folded = name.casefold()
        if not name or folded in BUILTIN_KEYBOARD_LAYOUTS or folded in used_names:
            continue
        normalized = normalize_layout_rows(rows)
        if normalized and any(key for row in normalized for key in row):
            result[name] = normalized
            used_names.add(folded)
    return result


def canonical_keyboard_layout(
    value: Any,
    custom_layouts: Any = None,
) -> str | None:
    """Return the canonical built-in or custom layout name, or None if unsupported."""
    name = str(value or "").strip()
    folded = name.casefold()
    if folded in BUILTIN_KEYBOARD_LAYOUTS:
        return folded

    for custom_name in normalize_custom_layouts(custom_layouts):
        if custom_name.casefold() == folded:
            return custom_name
    return None


def resolve_keyboard_layout(
    value: Any,
    custom_layouts: Any = None,
) -> list[list[str]]:
    """Resolve a selected layout, falling back safely to QWERTY."""
    custom = normalize_custom_layouts(custom_layouts)
    selected = canonical_keyboard_layout(value, custom) or DEFAULT_KEYBOARD_LAYOUT
    if selected in BUILTIN_KEYBOARD_LAYOUTS:
        return [list(row) for row in BUILTIN_KEYBOARD_LAYOUTS[selected]]

    resolved: list[list[str]] = []
    source_rows = custom[selected]
    for row_index in range(4):
        source = list(source_rows[row_index]) if row_index < len(source_rows) else []
        resolved.append((source[:5] + [""] * 5)[:5])
    return resolved
