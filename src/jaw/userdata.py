from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .icons import infer_icon_names
from .keyboard_layouts import (
    DEFAULT_KEYBOARD_LAYOUT,
    KEYBIND_POSITION_MODEL,
    canonical_keyboard_layout,
    is_position_id,
    layout_key_bindings_to_positions,
    normalize_custom_layouts,
    resolve_keyboard_layout,
)
from .paths import database_path
from .persistence import UserRepository

USER_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone_number",
    "street_address",
    "city",
    "state",
    "zip_code",
    "country",
    "linkedin",
    "github",
    "portfolio",
    "facebook",
    "x",
)

ALL_CAPABILITIES = "All"
JOB_MATCHING_SELECTION = "Job Matching Selection"

USER_DATA_FORMAT_VERSION = 4
CAPABILITY_MODEL_VERSION = 2

SYNC_REVISION_KEYS = ("profile", "capabilities", "actions", "keybinds")

ENTITY_TYPES = {"set", "competency", "technology", "product"}
RATEABLE_ENTITY_TYPES = {"competency", "technology", "product"}
RELATIONSHIP_TYPES = {
    "relevant_to",
    "uses",
    "based_on",
    "provided_by",
    "related_to",
}

SYSTEM_SET_ALL = "__all__"

DEFAULT_VIEW_PREFERENCES = {
    "hierarchy": {
        "section_granularity": 3,
        "entity_granularity": 3,
        "l1_section_target": 6,
        "l1_section_min": 4,
        "l1_section_max": 8,
        "group_min_entities": 3,
    },
    "layout": {
        "left_pane": "fixed",
        "right_pane": "fixed",
        "show_use_guide": True,
    },
}

DEFAULT_USER_TEMPLATE_PATH = (
    Path(__file__).with_name("resources") / "default-user-v1.0.json"
)


def default_user_data_path() -> Path:
    return database_path()


def empty_keybinds() -> dict[str, Any]:
    return {
        "binding_model": KEYBIND_POSITION_MODEL,
        "configured": False,
        "base": {},
        "layer2": {},
        "layer3": {},
        "hotkey_settings": {
            "toggle": "SHIFT+SPACE",
            "window": "CTRL+SHIFT+F1",
            "disable_when_minimized": False,
            "layers": {
                "layer2": {
                    "enabled": True,
                    "hold": True,
                    "mode": "hold",
                    "hotkey": "SHIFT",
                },
                "layer3": {"enabled": True},
            },
        },
        "action_displays": {},
        "custom_layouts": {},
    }


def empty_sync_revisions() -> dict[str, int]:
    return {key: 0 for key in SYNC_REVISION_KEYS}


def _normalize_sync_revisions(raw: dict[str, Any] | None) -> dict[str, int]:
    incoming = dict(raw or {})
    return {
        key: max(0, int(incoming.get(key, 0) or 0))
        for key in SYNC_REVISION_KEYS
    }


def _capability_sync_projection(model: dict[str, Any]) -> dict[str, Any]:
    """Capability data that matters to the desktop runtime.

    View preferences are browser presentation state and active_set_id is desktop
    runtime selection, so neither should wake/reload another client merely because
    the website changed its local view.
    """
    return {
        "entities": model.get("entities", []),
        "relationships": model.get("relationships", []),
    }


def _changed_sync_categories(old: dict[str, Any], new: dict[str, Any]) -> set[str]:
    changed: set[str] = set()
    if any(
        old.get(key) != new.get(key)
        for key in ("user", "work_history", "answers", "name_format", "analysis_settings")
    ):
        changed.add("profile")
    if _capability_sync_projection(old.get("capability_model", {})) != _capability_sync_projection(new.get("capability_model", {})):
        changed.add("capabilities")
    if any(
        old.get(key) != new.get(key)
        for key in ("custom_fields", "custom_actions", "iterator_preferences")
    ):
        changed.add("actions")
    if any(old.get(key) != new.get(key) for key in ("keyboard_layout", "keybinds")):
        changed.add("keybinds")
    return changed


def initial_keybinds() -> dict[str, Any]:
    """Read-only first-run workflow defaults keyed by physical matrix position."""
    defaults = empty_keybinds()
    defaults.update(
        {
            "configured": True,
            "base": {
                'P00': 'open_dashboard',
                'P01': 'analyze_job',
                'P02': 'find_company',
                'P03': 'toggle_answers',
                'P04': 'toggle_keyboard',
                'P10': 'country',
                'P11': 'iterate_contact',
                'P12': 'previous_iterator',
                'P13': 'iterate_work_exp',
                'P14': 'iterate_links',
                'P20': 'layer3_hold',
                'P21': 'iterate_address',
                'P22': 'next_iterator',
                'P23': 'iterate_skills',
                'P24': 'smart_capture',
                'P30': 'linkedin',
                'P31': 'portfolio',
                'P32': 'full_name',
                'P33': 'phone',
                'P34': 'email',
            },
            "layer2": {
                'P00': 'cycle_date_format',
                'P01': 'cycle_name_format',
                'P10': 'address',
                'P11': 'city',
                'P12': 'move_up_or_relay',
                'P13': 'previous_work_exp',
                'P20': 'state',
                'P21': 'zip',
                'P22': 'move_down_or_relay',
                'P23': 'next_work_exp',
                'P24': 'github',
                'P30': 'facebook',
                'P31': 'x',
                'P32': 'first_name',
                'P33': 'last_name',
            },
            "layer3": {},
        }
    )
    return defaults


RETIRED_LAYER_ACTIONS = {"layer2_toggle", "layer3_toggle", "capture_qa"}


def normalize_layer_bindings(keybinds: dict[str, Any]) -> dict[str, Any]:
    """Remove retired toggles and reserve Cycle Layers' key across all layers."""
    normalized = dict(keybinds)
    layers: dict[str, dict[str, str]] = {}

    for layer in ("base", "layer2", "layer3"):
        layers[layer] = {
            str(key).upper(): str(action)
            for key, action in dict(keybinds.get(layer, {})).items()
            if str(action).partition("|")[0] not in RETIRED_LAYER_ACTIONS
        }
        for key, action in list(layers[layer].items()):
            action_id, separator, label = action.partition("|")
            if action_id == "brief_job":
                layers[layer][key] = "smart_capture" + (
                    f"|{label}" if separator and label else ""
                )

    cycle_owners: dict[str, str] = {}
    for layer in ("base", "layer2", "layer3"):
        for key, action in list(layers[layer].items()):
            if action.partition("|")[0] != "cycle_layers":
                continue
            if key in cycle_owners:
                del layers[layer][key]
            else:
                cycle_owners[key] = layer

    for key, owner in cycle_owners.items():
        for layer in layers:
            if layer != owner:
                layers[layer].pop(key, None)

    normalized.update(layers)

    displays = dict(normalized.get("action_displays", {}))
    for action in RETIRED_LAYER_ACTIONS:
        displays.pop(action, None)
    normalized["action_displays"] = displays
    normalized["custom_layouts"] = normalize_custom_layouts(
        normalized.get("custom_layouts", {})
    )
    return normalized


def _normalize_keybind_storage(
    raw_keybinds: Any,
    keyboard_layout: Any,
) -> tuple[str, dict[str, Any]]:
    """Normalize persisted bindings to layout-independent physical positions."""
    normalized = normalize_layer_bindings(dict(raw_keybinds or {}))
    custom_layouts = normalized.get("custom_layouts", {})
    selected = (
        canonical_keyboard_layout(keyboard_layout, custom_layouts)
        or DEFAULT_KEYBOARD_LAYOUT
    )

    keys = [
        str(key).strip().upper()
        for layer in ("base", "layer2", "layer3")
        for key in normalized.get(layer, {})
    ]
    already_positioned = (
        normalized.get("binding_model") == KEYBIND_POSITION_MODEL
        or (bool(keys) and all(is_position_id(key) for key in keys))
    )
    if not already_positioned:
        rows = resolve_keyboard_layout(selected, custom_layouts)
        for layer in ("base", "layer2", "layer3"):
            normalized[layer] = layout_key_bindings_to_positions(
                normalized.get(layer, {}),
                rows,
            )

    normalized["binding_model"] = KEYBIND_POSITION_MODEL
    return selected, normalized


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _dedupe_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _normalize_view_preferences(raw: dict[str, Any] | None) -> dict[str, Any]:
    incoming = dict(raw or {})
    hierarchy = dict(DEFAULT_VIEW_PREFERENCES["hierarchy"])
    hierarchy.update(dict(incoming.get("hierarchy", {})))

    for key in ("section_granularity", "entity_granularity"):
        hierarchy[key] = min(5, max(1, int(hierarchy.get(key, 3))))

    hierarchy["l1_section_min"] = max(
        1, int(hierarchy.get("l1_section_min", 4))
    )
    hierarchy["l1_section_max"] = max(
        hierarchy["l1_section_min"],
        int(hierarchy.get("l1_section_max", 8)),
    )
    hierarchy["l1_section_target"] = min(
        hierarchy["l1_section_max"],
        max(
            hierarchy["l1_section_min"],
            int(hierarchy.get("l1_section_target", 6)),
        ),
    )
    hierarchy["group_min_entities"] = min(
        10, max(1, int(hierarchy.get("group_min_entities", 3)))
    )

    layout = dict(DEFAULT_VIEW_PREFERENCES["layout"])
    layout.update(dict(incoming.get("layout", {})))
    allowed_pane_modes = {"fixed", "auto", "off"}
    for key in ("left_pane", "right_pane"):
        mode = str(layout.get(key, "fixed")).strip().lower()
        layout[key] = mode if mode in allowed_pane_modes else "fixed"
    layout["show_use_guide"] = bool(layout.get("show_use_guide", True))

    return {"hierarchy": hierarchy, "layout": layout}


def _normalize_entity(
    raw: dict[str, Any],
    default_type: str = "technology",
) -> dict[str, Any]:
    entity_type = str(
        raw.get("type") or raw.get("entity_type") or default_type
    ).strip().lower()
    if entity_type not in ENTITY_TYPES:
        entity_type = default_type if default_type in ENTITY_TYPES else "technology"

    display_name = str(
        raw.get("display_name")
        or raw.get("name")
        or raw.get("canonical_name")
        or ""
    ).strip()
    canonical_name = str(
        raw.get("canonical_name") or display_name
    ).strip()

    if not display_name and canonical_name:
        display_name = canonical_name
    if not canonical_name and display_name:
        canonical_name = display_name

    entity_id = str(
        raw.get("id") or raw.get("entity_id") or _new_id("ent")
    ).strip()

    aliases = _dedupe_strings(raw.get("aliases", []))
    excluded_aliases = {
        display_name.casefold(),
        canonical_name.casefold(),
    }
    aliases = [
        alias
        for alias in aliases
        if alias.casefold() not in excluded_aliases
    ]

    entity: dict[str, Any] = {
        "id": entity_id,
        "type": entity_type,
        "canonical_name": canonical_name,
        "display_name": display_name,
        "aliases": aliases,
    }

    if entity_type in RATEABLE_ENTITY_TYPES:
        entity["rating"] = min(
            5, max(0, int(raw.get("rating", 0)))
        )
        entity["match_enabled"] = bool(raw.get("match_enabled", True))
        entity["iterator_enabled"] = bool(
            raw.get("iterator_enabled", True)
        )
    elif entity_type == "set":
        entity["document_enabled"] = bool(raw.get("document_enabled", True))
        entity["paste_enabled"] = bool(raw.get("paste_enabled", True))

    return entity


def _normalize_relationship(
    raw: dict[str, Any],
) -> dict[str, str] | None:
    source_id = str(
        raw.get("source_id") or raw.get("source") or ""
    ).strip()
    target_id = str(
        raw.get("target_id") or raw.get("target") or ""
    ).strip()
    relationship_type = str(
        raw.get("type") or raw.get("relationship") or ""
    ).strip()

    if (
        not source_id
        or not target_id
        or relationship_type not in RELATIONSHIP_TYPES
    ):
        return None

    return {
        "source_id": source_id,
        "type": relationship_type,
        "target_id": target_id,
    }


def _empty_capability_model() -> dict[str, Any]:
    return {
        "version": CAPABILITY_MODEL_VERSION,
        "entities": [],
        "relationships": [],
        "active_set_id": SYSTEM_SET_ALL,
        "view_preferences": _normalize_view_preferences(None),
    }


def _entity_name(entity: dict[str, Any]) -> str:
    return str(
        entity.get("display_name")
        or entity.get("canonical_name")
        or ""
    )


def _is_rateable(entity: dict[str, Any]) -> bool:
    return str(entity.get("type", "")) in RATEABLE_ENTITY_TYPES


def _entity_lookup(
    entities: Iterable[dict[str, Any]],
    *,
    set_scope: bool | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Return ID and name lookups, optionally scoped to sets or capabilities.

    Capability sets intentionally live in a separate naming namespace from rateable
    capabilities. A set named ``SRE`` must be able to coexist with a
    capability whose alias is ``SRE``.
    """
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, str] = {}

    for entity in entities:
        entity_id = str(entity.get("id", ""))
        if not entity_id:
            continue
        by_id[entity_id] = entity

        is_set = str(entity.get("type", "")).strip().lower() == "set"
        if set_scope is not None and is_set != set_scope:
            continue

        for value in (
            entity.get("display_name"),
            entity.get("canonical_name"),
            *entity.get("aliases", []),
        ):
            text = str(value or "").strip()
            if text:
                by_name.setdefault(text.casefold(), entity_id)

    return by_id, by_name


def _normalize_capability_model(raw: dict[str, Any] | None) -> dict[str, Any]:
    incoming = dict(raw or {})

    entities: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    names: dict[tuple[str, str], str] = {}

    for raw_entity in incoming.get("entities", []):
        entity = _normalize_entity(dict(raw_entity))
        if not _entity_name(entity):
            continue

        if entity["id"] in used_ids:
            entity["id"] = _new_id("ent")

        namespace = "set" if entity["type"] == "set" else "capability"
        duplicate_id = (
            names.get((namespace, entity["canonical_name"].casefold()))
            or names.get((namespace, entity["display_name"].casefold()))
        )
        if duplicate_id:
            existing = next(
                item for item in entities if item["id"] == duplicate_id
            )
            existing["aliases"] = _dedupe_strings(
                existing.get("aliases", [])
                + entity.get("aliases", [])
                + [entity["display_name"]]
            )
            if _is_rateable(existing) and _is_rateable(entity):
                existing["rating"] = max(
                    int(existing.get("rating", 0)),
                    int(entity.get("rating", 0)),
                )
                existing["match_enabled"] = bool(
                    existing.get("match_enabled", True)
                    or entity.get("match_enabled", True)
                )
                existing["iterator_enabled"] = bool(
                    existing.get("iterator_enabled", True)
                    or entity.get("iterator_enabled", True)
                )
            continue

        used_ids.add(entity["id"])
        entities.append(entity)
        names[(namespace, entity["canonical_name"].casefold())] = entity["id"]
        names[(namespace, entity["display_name"].casefold())] = entity["id"]

    valid_ids = {entity["id"] for entity in entities}
    relationships: list[dict[str, str]] = []
    seen_relationships: set[tuple[str, str, str]] = set()

    for raw_relationship in incoming.get("relationships", []):
        relationship = _normalize_relationship(dict(raw_relationship))
        if relationship is None:
            continue
        key = (
            relationship["source_id"],
            relationship["type"],
            relationship["target_id"],
        )
        if (
            relationship["source_id"] in valid_ids
            and relationship["target_id"] in valid_ids
            and key not in seen_relationships
        ):
            relationships.append(relationship)
            seen_relationships.add(key)

    active_set_id = str(
        incoming.get("active_set_id")
        or SYSTEM_SET_ALL
    )
    if (
        active_set_id != SYSTEM_SET_ALL
        and not any(
            entity["id"] == active_set_id and entity["type"] == "set"
            for entity in entities
        )
    ):
        active_set_id = SYSTEM_SET_ALL

    return {
        "version": CAPABILITY_MODEL_VERSION,
        "entities": sorted(
            entities,
            key=lambda entity: (
                entity["type"] == "set",
                _entity_name(entity).casefold(),
            ),
        ),
        "relationships": relationships,
        "active_set_id": active_set_id,
        "view_preferences": _normalize_view_preferences(
            incoming.get("view_preferences")
        ),
    }


@dataclass
class UserDataStore:
    path: Path
    user_id: int | None = None

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self._repository = UserRepository(self.path)

        with self._repository.transaction() as repository:
            repository.initialize_schema()

            if not repository.count_users():
                state = self._initial_state()
                user = state.get("user", {})
                display = " ".join(
                    value
                    for value in (
                        user.get("first_name", ""),
                        user.get("last_name", ""),
                    )
                    if value
                ).strip() or "Default"

                user_id = repository.create_user(
                    display,
                    self._stored_state(state),
                )
                repository.set_preference(
                    "active_user_id", str(user_id)
                )

    @classmethod
    def _initial_state(cls) -> dict[str, Any]:
        """Load the packaged first-run template when possible."""
        try:
            incoming = json.loads(
                DEFAULT_USER_TEMPLATE_PATH.read_text(encoding="utf-8")
            )
            return cls._external_to_state(incoming)
        except (
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ):
            return cls.empty_state()

    @staticmethod
    def empty_state() -> dict[str, Any]:
        return {
            "sync_revisions": empty_sync_revisions(),
            "capability_model": _empty_capability_model(),
            "user": {
                field: "" for field in USER_FIELDS
            },
            "custom_fields": [],
            "custom_actions": [],
            "work_history": [],
            "iterator_preferences": {},
            "answers": [],
            "analysis_settings": {
                "mode": "generative",
                "provider": "openai",
                "model": "gpt-5.6-terra",
            },
            "name_format": "first_last",
            "keyboard_layout": DEFAULT_KEYBOARD_LAYOUT,
            "keybinds": initial_keybinds(),
        }

    @classmethod
    def _external_to_state(
        cls,
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        base = cls.empty_state()

        for field in USER_FIELDS:
            base["user"][field] = str(
                incoming.get("user", {}).get(field, "")
            )

        for key in (
            "custom_fields",
            "custom_actions",
            "work_history",
            "iterator_preferences",
            "answers",
            "analysis_settings",
            "keybinds",
        ):
            if key in incoming:
                base[key] = incoming[key]

        if "name_format" in incoming:
            base["name_format"] = incoming["name_format"]
        if "keyboard_layout" in incoming:
            base["keyboard_layout"] = incoming["keyboard_layout"]

        base["capability_model"] = _normalize_capability_model(
            incoming.get("capability_model")
        )
        return cls._stored_state(base)

    @staticmethod
    def _stored_state(data: dict[str, Any]) -> dict[str, Any]:
        model = _normalize_capability_model(
            data.get("capability_model")
        )
        keyboard_layout, keybinds = _normalize_keybind_storage(
            data.get("keybinds", empty_keybinds()),
            data.get("keyboard_layout", DEFAULT_KEYBOARD_LAYOUT),
        )

        return {
            "sync_revisions": _normalize_sync_revisions(data.get("sync_revisions")),
            "capability_model": model,
            "user": {
                field: str(
                    data.get("user", {}).get(field, "")
                )
                for field in USER_FIELDS
            },
            "custom_fields": data.get("custom_fields", []),
            "custom_actions": data.get("custom_actions", []),
            "work_history": data.get("work_history", []),
            "iterator_preferences": data.get(
                "iterator_preferences", {}
            ),
            "answers": data.get("answers", []),
            "analysis_settings": data.get(
                "analysis_settings",
                {
                    "mode": "generative",
                    "provider": "openai",
                    "model": "gpt-5.6-terra",
                },
            ),
            "name_format": (
                "full"
                if data.get("name_format") == "full"
                else "first_last"
            ),
            "keyboard_layout": keyboard_layout,
            "keybinds": keybinds,
        }

    def read(self, user_id: int | None = None) -> dict[str, Any]:
        with self._repository.transaction() as repository:
            requested_id = self.user_id if user_id is None else user_id
            active_id = (
                int(requested_id)
                if requested_id is not None
                else repository.active_user_id()
            )
            row = repository.get_user(active_id)

            if row is None and requested_id is None:
                row = repository.first_user()

            if row is None:
                if requested_id is not None:
                    raise ValueError(f"User {int(requested_id)} does not exist")
                raise ValueError("No users exist")

            raw = row.data

            state = self._stored_state(raw)
            if state != raw:
                repository.update_user(row.id, state)

            users = [
                {"id": item.id, "name": item.name}
                for item in repository.list_users()
            ]

        model = state["capability_model"]
        return {
            **state,
            "entities": list(model["entities"]),
            "relationships": list(model["relationships"]),
            "view_preferences": dict(model["view_preferences"]),
            "active_user_id": row.id,
            "active_user_name": row.name,
            "users": users,
        }

    def read_sync_revisions(self, user_id: int | None = None) -> dict[str, int]:
        """Return lightweight per-user revision counters without materializing config."""
        with self._repository.transaction() as repository:
            requested_id = self.user_id if user_id is None else user_id
            target_id = (
                int(requested_id)
                if requested_id is not None
                else repository.active_user_id()
            )
            row = repository.get_user(target_id)
            if row is None:
                raise ValueError(f"User {target_id} does not exist")
            return _normalize_sync_revisions(row.data.get("sync_revisions"))

    def write(self, data: dict[str, Any], user_id: int | None = None) -> None:
        incoming = self._stored_state(data)

        with self._repository.transaction() as repository:
            requested_id = self.user_id if user_id is None else user_id
            target_id = (
                int(requested_id)
                if requested_id is not None
                else repository.active_user_id()
            )
            row = repository.get_user(target_id)
            if row is None:
                raise ValueError(f"User {target_id} does not exist")

            previous = self._stored_state(row.data)
            revisions = _normalize_sync_revisions(previous.get("sync_revisions"))
            for category in _changed_sync_categories(previous, incoming):
                revisions[category] += 1
            incoming["sync_revisions"] = revisions

            repository.update_user(target_id, incoming)

    def create_user(
        self,
        name: str,
        clone_current: bool = False,
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("User name is required")

        state = (
            self._stored_state(self.read())
            if clone_current
            else self._stored_state(self.empty_state())
        )

        with self._repository.transaction() as repository:
            user_id = repository.create_user(name, state)
            repository.set_preference("active_user_id", str(user_id))
            return user_id

    def switch_user(self, user_id: int) -> None:
        with self._repository.transaction() as repository:
            if not repository.user_exists(user_id):
                raise ValueError("User not found")

            repository.set_preference("active_user_id", str(user_id))

    def delete_user(self, user_id: int) -> None:
        with self._repository.transaction() as repository:
            if repository.count_users() <= 1:
                raise ValueError("At least one user is required")

            repository.delete_user(user_id)
            users = repository.list_users()
            repository.set_preference("active_user_id", str(users[0].id))

    def export_data(self) -> dict[str, Any]:
        data = self.read()
        return {
            "format": "jaw-user-data",
            "version": USER_DATA_FORMAT_VERSION,
            "user_name": data["active_user_name"],
            **self._stored_state(data),
        }

    @classmethod
    def template_data(cls) -> dict[str, Any]:
        state = cls.empty_state()
        return {
            "format": "jaw-user-data",
            "version": USER_DATA_FORMAT_VERSION,
            "user_name": "Example User",
            **cls._stored_state(state),
        }

    def import_data(
        self,
        incoming: dict[str, Any],
        mode: str = "merge",
    ) -> None:
        if incoming.get("format") not in (
            None,
            "jaw-user-data",
        ):
            raise ValueError("Unsupported import format")

        imported = self._external_to_state(incoming)

        if mode == "replace":
            self.write(imported)
            return

        if mode != "merge":
            raise ValueError("Import mode must be merge or replace")

        data = self.read()

        for field, value in imported["user"].items():
            if value:
                data["user"][field] = value

        for key in (
            "custom_fields",
            "custom_actions",
            "work_history",
            "answers",
        ):
            if imported.get(key):
                data[key] = imported[key]

        current_model = data["capability_model"]
        incoming_model = imported["capability_model"]

        current_by_id, current_by_name = _entity_lookup(
            current_model["entities"]
        )

        for raw_entity in incoming_model["entities"]:
            entity = _normalize_entity(raw_entity)
            existing_id = (
                entity["id"]
                if entity["id"] in current_by_id
                else current_by_name.get(
                    entity["canonical_name"].casefold()
                )
                or current_by_name.get(
                    entity["display_name"].casefold()
                )
            )

            if existing_id:
                existing = current_by_id[existing_id]
                existing["aliases"] = _dedupe_strings(
                    existing.get("aliases", [])
                    + entity.get("aliases", [])
                )
                # User-owned state stays authoritative on merge.
                if existing.get("type") != "set":
                    existing.setdefault(
                        "rating",
                        int(entity.get("rating", 0)),
                    )
                    existing.setdefault(
                        "match_enabled",
                        bool(
                            entity.get(
                                "match_enabled",
                                True,
                            )
                        ),
                    )
                    existing.setdefault(
                        "iterator_enabled",
                        bool(
                            entity.get(
                                "iterator_enabled",
                                True,
                            )
                        ),
                    )
                continue

            current_model["entities"].append(entity)
            current_by_id[entity["id"]] = entity
            current_by_name[
                entity["canonical_name"].casefold()
            ] = entity["id"]
            current_by_name[
                entity["display_name"].casefold()
            ] = entity["id"]

        valid_ids = {
            entity["id"]
            for entity in current_model["entities"]
        }
        existing_relationships = {
            (
                item["source_id"],
                item["type"],
                item["target_id"],
            )
            for item in current_model["relationships"]
        }

        for raw_relationship in incoming_model["relationships"]:
            relationship = _normalize_relationship(
                raw_relationship
            )
            if relationship is None:
                continue

            key = (
                relationship["source_id"],
                relationship["type"],
                relationship["target_id"],
            )
            if (
                relationship["source_id"] in valid_ids
                and relationship["target_id"] in valid_ids
                and key not in existing_relationships
            ):
                current_model["relationships"].append(
                    relationship
                )
                existing_relationships.add(key)

        data["capability_model"] = _normalize_capability_model(
            current_model
        )
        self.write(data)

    # ------------------------------------------------------------------
    # Capability model API
    # ------------------------------------------------------------------

    def upsert_entity(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = self.read()
        model = data["capability_model"]
        by_id, _ = _entity_lookup(model["entities"])

        requested_id = str(
            payload.get("id")
            or payload.get("entity_id")
            or ""
        ).strip()
        requested_type = str(payload.get("type") or "").strip().lower()
        if requested_type and requested_type not in ENTITY_TYPES:
            raise ValueError(f"Unsupported entity type: {requested_type}")

        existing_id = requested_id if requested_id in by_id else None

        # New entities resolve names only inside their semantic namespace.
        # Capability sets and capabilities may intentionally share names/aliases.
        if existing_id is None and not requested_id:
            set_scope = requested_type == "set" if requested_type else None
            _, scoped_names = _entity_lookup(
                model["entities"],
                set_scope=set_scope,
            )
            lookup_name = str(
                payload.get("canonical_name")
                or payload.get("display_name")
                or payload.get("name")
                or ""
            ).strip().casefold()
            if lookup_name:
                existing_id = scoped_names.get(lookup_name)

        if existing_id:
            existing = by_id[existing_id]
            entity_type = requested_type or str(existing["type"]).strip().lower()
            if entity_type not in ENTITY_TYPES:
                raise ValueError(f"Unsupported entity type: {entity_type}")

            existing_is_set = str(existing.get("type", "")).lower() == "set"
            requested_is_set = entity_type == "set"
            if existing_is_set != requested_is_set:
                raise ValueError(
                    "Capability sets cannot be converted to or from capabilities. "
                    "Create a separate entity instead."
                )

            existing["type"] = entity_type

            if payload.get("canonical_name"):
                existing["canonical_name"] = str(payload["canonical_name"]).strip()
            if payload.get("display_name") or payload.get("name"):
                existing["display_name"] = str(
                    payload.get("display_name") or payload.get("name")
                ).strip()
            if "aliases" in payload:
                existing["aliases"] = _dedupe_strings(payload.get("aliases", []))

            if entity_type in RATEABLE_ENTITY_TYPES:
                if "rating" in payload:
                    existing["rating"] = min(5, max(0, int(payload.get("rating", 0))))
                else:
                    existing.setdefault("rating", 0)
                if "match_enabled" in payload:
                    existing["match_enabled"] = bool(payload["match_enabled"])
                else:
                    existing.setdefault("match_enabled", True)
                if "iterator_enabled" in payload:
                    existing["iterator_enabled"] = bool(payload["iterator_enabled"])
                else:
                    existing.setdefault("iterator_enabled", True)
            else:
                existing.pop("rating", None)
                existing.pop("match_enabled", None)
                existing.pop("iterator_enabled", None)
            entity = existing
        else:
            entity = _normalize_entity(payload)
            if not _entity_name(entity):
                raise ValueError("Entity name is required")
            model["entities"].append(entity)

        data["capability_model"] = _normalize_capability_model(model)
        self.write(data)
        return next(
            item
            for item in data["capability_model"]["entities"]
            if item["id"] == entity["id"]
        )

    def set_entity_match_enabled(
        self,
        entity_id: str,
        enabled: bool,
    ) -> None:
        data = self.read()
        entity = self._entity_by_id(
            data["capability_model"], entity_id
        )
        if not _is_rateable(entity):
            raise ValueError(
                "Only rateable capabilities can participate in matching"
            )
        entity["match_enabled"] = bool(enabled)
        self.write(data)

    def set_entity_iterator_enabled(
        self,
        entity_id: str,
        enabled: bool,
    ) -> None:
        data = self.read()
        entity = self._entity_by_id(
            data["capability_model"], entity_id
        )
        if not _is_rateable(entity):
            raise ValueError(
                "Only rateable capabilities can participate in the skill iterator"
            )
        entity["iterator_enabled"] = bool(enabled)
        self.write(data)

    def save_relationships(
        self,
        relationships: list[dict[str, Any]],
        replace: bool = False,
    ) -> None:
        data = self.read()
        model = data["capability_model"]
        valid_ids = {
            entity["id"] for entity in model["entities"]
        }

        normalized: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()

        if not replace:
            for existing in model["relationships"]:
                key = (
                    existing["source_id"],
                    existing["type"],
                    existing["target_id"],
                )
                normalized.append(existing)
                seen.add(key)

        for raw in relationships:
            relationship = _normalize_relationship(raw)
            if relationship is None:
                raise ValueError(
                    "Invalid relationship. Expected source_id, type, and target_id."
                )

            if (
                relationship["source_id"] not in valid_ids
                or relationship["target_id"] not in valid_ids
            ):
                raise ValueError(
                    "Relationship references an unknown entity"
                )

            key = (
                relationship["source_id"],
                relationship["type"],
                relationship["target_id"],
            )
            if key not in seen:
                normalized.append(relationship)
                seen.add(key)

        model["relationships"] = normalized
        self.write(data)

    def save_view_preferences(
        self,
        preferences: dict[str, Any],
    ) -> None:
        data = self.read()
        data["capability_model"]["view_preferences"] = (
            _normalize_view_preferences(preferences)
        )
        self.write(data)

    def clear_capabilities(self) -> None:
        """Delete only capability/set graph data; preserve all other user data."""
        data = self.read()
        data["capability_model"] = _empty_capability_model()
        self.write(data)

    def delete_entities_by_id(self, entity_ids: Iterable[str]) -> None:
        """Delete rateable capabilities by stable ID and cascade relationships."""
        data = self.read()
        model = data["capability_model"]
        removed_ids = {
            str(entity_id).strip()
            for entity_id in entity_ids
            if str(entity_id).strip()
        }
        if not removed_ids:
            return

        by_id, _ = _entity_lookup(model["entities"])
        if any(
            by_id.get(entity_id, {}).get("type") == "set"
            for entity_id in removed_ids
        ):
            raise ValueError("Capability sets use delete_set_by_id")

        model["entities"] = [
            entity
            for entity in model["entities"]
            if entity["id"] not in removed_ids
        ]
        model["relationships"] = [
            relationship
            for relationship in model["relationships"]
            if relationship["source_id"] not in removed_ids
            and relationship["target_id"] not in removed_ids
        ]
        data["capability_model"] = _normalize_capability_model(model)
        self.write(data)

    def save_capability_set(
        self,
        set_id: str,
        name: str,
        capability_ids: list[str],
        *,
        document_enabled: bool | None = None,
        paste_enabled: bool | None = None,
    ) -> str:
        """Create or update a capability set and its stable-ID membership."""
        data = self.read()
        model = data["capability_model"]
        by_id, set_names = _entity_lookup(model["entities"], set_scope=True)

        set_id = str(set_id).strip()
        name = str(name).strip()
        if not name:
            raise ValueError("Choose a capability-set name")
        if set_id == SYSTEM_SET_ALL:
            raise ValueError("All Capabilities is managed by iterator flags")

        conflicting_id = set_names.get(name.casefold())
        if conflicting_id and conflicting_id != set_id:
            raise ValueError(f"Another capability set already uses the name {name}")

        if set_id:
            capability_set = by_id.get(set_id)
            if not capability_set or capability_set.get("type") != "set":
                raise ValueError("set_id does not reference a capability set")
        else:
            set_id = _new_id("set")
            capability_set = _normalize_entity(
                {
                    "id": set_id,
                    "type": "set",
                    "canonical_name": name,
                    "display_name": name,
                }
            )
            model["entities"].append(capability_set)
            by_id[set_id] = capability_set

        capability_set["display_name"] = name
        capability_set["canonical_name"] = name
        if document_enabled is not None:
            capability_set["document_enabled"] = bool(document_enabled)
        else:
            capability_set.setdefault("document_enabled", True)
        if paste_enabled is not None:
            capability_set["paste_enabled"] = bool(paste_enabled)
        else:
            capability_set.setdefault("paste_enabled", True)

        selected: list[str] = []
        seen: set[str] = set()
        for raw_id in capability_ids:
            capability_id = str(raw_id).strip()
            capability = by_id.get(capability_id)
            if capability and _is_rateable(capability) and capability_id not in seen:
                selected.append(capability_id)
                seen.add(capability_id)

        model["relationships"] = [
            relationship
            for relationship in model["relationships"]
            if not (
                relationship["type"] == "relevant_to"
                and relationship["target_id"] == set_id
            )
        ]
        model["relationships"].extend(
            {
                "source_id": capability_id,
                "type": "relevant_to",
                "target_id": set_id,
            }
            for capability_id in selected
        )

        if (
            not capability_set.get("paste_enabled", True)
            and model.get("active_set_id") == set_id
        ):
            model["active_set_id"] = SYSTEM_SET_ALL

        data["capability_model"] = _normalize_capability_model(model)
        self.write(data)
        return set_id

    def delete_set_by_id(self, set_id: str) -> None:
        data = self.read()
        model = data["capability_model"]
        set_id = str(set_id).strip()
        if not set_id or set_id == SYSTEM_SET_ALL:
            raise ValueError("All cannot be deleted")

        by_id, _ = _entity_lookup(model["entities"])
        capability_set = by_id.get(set_id)
        if not capability_set or capability_set.get("type") != "set":
            return

        model["entities"] = [
            entity for entity in model["entities"] if entity["id"] != set_id
        ]
        model["relationships"] = [
            relationship
            for relationship in model["relationships"]
            if relationship["source_id"] != set_id
            and relationship["target_id"] != set_id
        ]
        if model.get("active_set_id") == set_id:
            model["active_set_id"] = SYSTEM_SET_ALL
        data["capability_model"] = _normalize_capability_model(model)
        self.write(data)

    def set_active_set_id(self, set_id: str) -> None:
        data = self.read()
        model = data["capability_model"]
        set_id = str(set_id).strip() or SYSTEM_SET_ALL
        if set_id == SYSTEM_SET_ALL:
            model["active_set_id"] = SYSTEM_SET_ALL
            self.write(data)
            return

        by_id, _ = _entity_lookup(model["entities"])
        capability_set = by_id.get(set_id)
        if not capability_set or capability_set.get("type") != "set":
            raise ValueError("set_id does not reference a capability set")
        if not capability_set.get("paste_enabled", True):
            raise ValueError("Capability set is not enabled for Paste")
        model["active_set_id"] = set_id
        self.write(data)

    # ------------------------------------------------------------------
    # Existing non-capability user data
    # ------------------------------------------------------------------

    def save_user(self, values: dict[str, Any]) -> None:
        data = self.read()
        data["user"] = {
            field: str(
                values.get(
                    field,
                    data.get("user", {}).get(field, ""),
                )
            ).strip()
            for field in USER_FIELDS
        }
        self.write(data)

    def save_custom_fields(
        self,
        fields: list[dict[str, Any]],
    ) -> None:
        data = self.read()
        cleaned = []
        used: set[str] = set()
        labels: set[str] = set()

        old_field_ids = {
            str(field.get("id", ""))
            for field in data.get("custom_fields", [])
            if field.get("id")
        }

        for field in fields:
            label = str(field.get("label", "")).strip()
            value = str(field.get("value", ""))
            normalized = label.casefold()

            if label and normalized in labels:
                raise ValueError(
                    f"Label '{label}' is already in use"
                )

            field_id = (
                str(field.get("id", ""))
                .strip()
                .lower()
                .replace(" ", "_")
            )
            if not field_id or field_id in used:
                field_id = f"custom_{uuid.uuid4().hex}"

            if label:
                field_type = str(
                    field.get("type", "single")
                ).lower()
                cleaned.append(
                    {
                        "id": field_id,
                        "label": label,
                        "value": value,
                        "type": (
                            "multi"
                            if field_type == "multi"
                            else "single"
                        ),
                    }
                )
                used.add(field_id)
                labels.add(normalized)

        valid_ids = {
            field["id"] for field in cleaned
        }

        for action in data.get("custom_actions", []):
            action["field_ids"] = [
                field_id
                for field_id in action.get(
                    "field_ids", []
                )
                if field_id in valid_ids
            ]

        keybinds = data.get("keybinds", {})
        for layer in ("base", "layer2", "layer3"):
            bindings = keybinds.get(layer, {})
            keybinds[layer] = {
                key: value
                for key, value in bindings.items()
                if str(value).partition("|")[0]
                not in old_field_ids
            }

        displays = keybinds.get(
            "action_displays", {}
        )
        keybinds["action_displays"] = {
            action_id: display
            for action_id, display in displays.items()
            if action_id not in old_field_ids
        }

        data["keybinds"] = keybinds
        data["custom_fields"] = cleaned
        self.write(data)

    def save_custom_actions(
        self,
        actions: list[dict[str, Any]],
        reserved_labels: set[str] | None = None,
    ) -> None:
        data = self.read()
        field_ids = {
            field["id"]
            for field in data.get("custom_fields", [])
        }
        cleaned = []
        labels: set[str] = {
            str(label).strip().casefold()
            for label in (reserved_labels or set())
        }
        used_ids: set[str] = set()

        for action in actions:
            label = str(
                action.get("label", "")
            ).strip()
            normalized = label.casefold()

            if not label:
                continue

            if normalized in labels:
                raise ValueError(
                    f"Action label '{label}' must be unique"
                )

            action_id = str(
                action.get("id", "")
            ).strip()
            if not action_id or action_id in used_ids:
                action_id = (
                    f"custom_action_{uuid.uuid4().hex}"
                )

            action_type = str(
                action.get("type", "single")
            ).lower()

            selected = [
                str(field_id)
                for field_id in action.get(
                    "field_ids", []
                )
                if str(field_id) in field_ids
            ]
            if action_type == "single":
                selected = selected[:1]

            cleaned.append(
                {
                    "id": action_id,
                    "label": label,
                    "type": (
                        "iterator"
                        if action_type == "iterator"
                        else "single"
                    ),
                    "field_ids": selected,
                    "auto_return": bool(
                        action.get(
                            "auto_return", False
                        )
                    ),
                }
            )
            labels.add(normalized)
            used_ids.add(action_id)

        removed = {
            str(action.get("id", ""))
            for action in data.get(
                "custom_actions", []
            )
        } - used_ids

        keybinds = data.get("keybinds", {})
        for layer in ("base", "layer2", "layer3"):
            bindings = keybinds.get(layer, {})
            keybinds[layer] = {
                key: value
                for key, value in bindings.items()
                if str(value).partition("|")[0]
                not in removed
            }

        displays = keybinds.get(
            "action_displays", {}
        )

        for action in cleaned:
            display = displays.get(action["id"])
            if isinstance(display, dict):
                display["label"] = ""

        keybinds["action_displays"] = {
            action_id: display
            for action_id, display in displays.items()
            if action_id not in removed
        }

        data["keybinds"] = keybinds
        data["custom_actions"] = cleaned
        self.write(data)

    def set_custom_action_auto_returns(
        self,
        values: dict[str, bool],
    ) -> None:
        data = self.read()

        for action in data.get(
            "custom_actions", []
        ):
            action_id = str(
                action.get("id", "")
            )
            if action_id in values:
                action["auto_return"] = bool(
                    values[action_id]
                )

        self.write(data)

    def save_work_history(
        self,
        entries: list[dict[str, Any]],
    ) -> None:
        data = self.read()
        data["work_history"] = [
            {
                **{
                    key: str(entry.get(key, ""))
                    for key in (
                        "title",
                        "company",
                        "start",
                        "end",
                        "highlights",
                    )
                },
                "enabled": bool(
                    entry.get("enabled", True)
                ),
            }
            for entry in entries
            if entry.get("title")
            or entry.get("company")
        ]
        self.write(data)

    def save_iterator_preferences(
        self,
        preferences: dict[
            str, dict[str, list[str]]
        ],
    ) -> None:
        data = self.read()
        data["iterator_preferences"] = {
            str(action): {
                "order": [
                    str(item)
                    for item in value.get(
                        "order", []
                    )
                ],
                "disabled": [
                    str(item)
                    for item in value.get(
                        "disabled", []
                    )
                ],
            }
            for action, value in preferences.items()
        }
        self.write(data)

    def save_answers(
        self,
        answers: list[dict[str, Any]],
    ) -> None:
        data = self.read()
        data["answers"] = [
            {
                "title": str(
                    item.get("title", "")
                ),
                "answer": str(
                    item.get("answer", "")
                ),
            }
            for item in answers
            if item.get("title")
        ]
        self.write(data)

    def set_keyboard_layout(
        self,
        layout: str,
    ) -> None:
        data = self.read()
        custom = data.get("keybinds", {}).get("custom_layouts", {})
        selected = canonical_keyboard_layout(layout, custom)
        if selected is None:
            raise ValueError("Unsupported keyboard layout")
        data["keyboard_layout"] = selected
        self.write(data)

    def save_keybinds(
        self,
        payload: dict[str, Any],
    ) -> None:
        data = self.read()
        cleaned = empty_keybinds()
        cleaned["configured"] = True
        cleaned["custom_layouts"] = normalize_custom_layouts(
            payload.get("custom_layouts", {})
        )
        requested_layout = payload.get("keyboard_layout")
        if requested_layout is None:
            selected_layout = (
                canonical_keyboard_layout(
                    data.get("keyboard_layout"),
                    cleaned["custom_layouts"],
                )
                or DEFAULT_KEYBOARD_LAYOUT
            )
        else:
            selected_layout = canonical_keyboard_layout(
                requested_layout,
                cleaned["custom_layouts"],
            )
            if selected_layout is None:
                raise ValueError("Unsupported keyboard layout")
        layout_rows = resolve_keyboard_layout(
            selected_layout,
            cleaned["custom_layouts"],
        )

        for layer in (
            "base",
            "layer2",
            "layer3",
        ):
            incoming_bindings = {
                str(key).strip().upper(): str(action)
                for key, action in dict(
                    payload.get(layer, {})
                ).items()
            }
            if any(is_position_id(key) for key in incoming_bindings):
                cleaned[layer] = {
                    key: action
                    for key, action in incoming_bindings.items()
                    if is_position_id(key)
                }
            else:
                cleaned[layer] = layout_key_bindings_to_positions(
                    incoming_bindings,
                    layout_rows,
                )

        defaults = empty_keybinds()[
            "hotkey_settings"
        ]
        incoming = payload.get(
            "hotkey_settings", {}
        )

        cleaned["hotkey_settings"] = {
            "toggle": str(
                incoming.get(
                    "toggle",
                    defaults["toggle"],
                )
            ).upper(),
            "window": str(
                incoming.get(
                    "window",
                    defaults["window"],
                )
            ).upper(),
            "disable_when_minimized": bool(
                incoming.get(
                    "disable_when_minimized",
                    False,
                )
            ),
            "layers": {},
        }

        incoming_layers = dict(
            incoming.get("layers", {})
        )
        layer2 = dict(
            incoming_layers.get("layer2", {})
        )
        layer3 = dict(
            incoming_layers.get("layer3", {})
        )

        cleaned["hotkey_settings"]["layers"][
            "layer2"
        ] = {
            "enabled": bool(
                layer2.get("enabled", True)
            ),
            "hold": bool(
                layer2.get("hold", True)
            ),
            "mode": "hold",
            "hotkey": "SHIFT",
        }
        cleaned["hotkey_settings"]["layers"][
            "layer3"
        ] = {
            "enabled": bool(
                layer3.get("enabled", True)
            ),
        }

        cleaned["action_displays"] = {
            str(action): {
                "label": str(
                    value.get("label", "")
                ),
                "icons": infer_icon_names(
                    str(action),
                    value,
                ),
            }
            for action, value in dict(
                payload.get(
                    "action_displays", {}
                )
            ).items()
            if isinstance(value, dict)
        }

        data["keyboard_layout"] = selected_layout
        data["keybinds"] = normalize_layer_bindings(cleaned)
        self.write(data)

    def save_analysis_settings(
        self,
        mode: str,
        provider: str,
        model: str,
    ) -> None:
        mode = str(mode).strip().lower()
        provider = str(
            provider
        ).strip().lower()
        model = str(model).strip()

        if mode not in {
            "local",
            "generative",
        }:
            raise ValueError(
                "Analysis mode must be local or generative"
            )

        if provider not in {"openai", "ollama"}:
            raise ValueError(
                "Analysis provider must be OpenAI or Ollama"
            )

        if not model:
            raise ValueError(
                "A model is required"
            )

        data = self.read()
        data["analysis_settings"] = {
            "mode": mode,
            "provider": provider,
            "model": model,
        }
        self.write(data)

    def set_name_format(
        self,
        name_format: str,
    ) -> None:
        if name_format not in {
            "full",
            "first_last",
        }:
            raise ValueError(
                "Name format must be full or first_last"
            )

        data = self.read()
        data["name_format"] = name_format
        self.write(data)

    @staticmethod
    def _entity_by_id(
        model: dict[str, Any],
        entity_id: str,
    ) -> dict[str, Any]:
        try:
            return next(
                entity
                for entity in model["entities"]
                if entity["id"] == entity_id
            )
        except StopIteration as error:
            raise ValueError(
                f"Unknown entity: {entity_id}"
            ) from error
