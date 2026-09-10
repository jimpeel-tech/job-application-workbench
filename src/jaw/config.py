from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .icons import infer_icon_names
from .keyboard_layouts import (
    DEFAULT_KEYBOARD_LAYOUT,
    position_bindings_to_layout_keys,
    resolve_keyboard_layout,
)
from .model import PasteItem
from .paths import config_path as writable_config_path
from .smart_capture import (
    default_smart_capture_settings,
    normalize_smart_capture_settings,
)
from .userdata import ALL_CAPABILITIES, JOB_MATCHING_SELECTION, UserDataStore

# Capability-domain values belong to the runtime projection, not to the
# persistence implementation. Keeping them here prevents config.py from
# depending on userdata.py implementation details.
RATEABLE_ENTITY_TYPES = frozenset({"competency", "technology", "product"})
SYSTEM_SET_ALL = "__all__"

DEFAULT_OPENAI_MODEL = "gpt-5.6-terra"

RATING_GUIDANCE = {
    0: {
        "label": "Unrated",
        "description": "Not assessed",
    },
    1: {
        "label": "Conceptual",
        "description": (
            "Understand the concepts/use cases; little or no hands-on experience"
        ),
    },
    2: {
        "label": "Hands-on",
        "description": (
            "Have actually used it, but experience is limited or narrow"
        ),
    },
    3: {
        "label": "Proficient",
        "description": (
            "Can work independently on normal production tasks"
        ),
    },
    4: {
        "label": "Advanced",
        "description": (
            "Deep experience; handles complex design/troubleshooting and can guide others"
        ),
    },
    5: {
        "label": "Expert",
        "description": (
            "Extensive depth and breadth; regularly solves ambiguous/novel problems and can serve as a technical authority"
        ),
    },
}
DEFAULT_DASHBOARD_PORT = 8765
DEFAULT_MATRIX_BASE = {
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
}
DEFAULT_MATRIX_LAYER2 = {
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
}
DEFAULT_MATRIX_LAYER3: dict[str, str] = {}
DEFAULT_SEQUENCES = {
    "iterate_contact": ["first_name", "last_name", "email", "phone"],
    "iterate_address": ["address", "city", "state", "zip", "country"],
    "iterate_links": ["linkedin", "portfolio", "github", "facebook", "x"],
}
BUILTIN_ACTION_LABELS = {
    "toggle_answers": "Answers", "toggle_keyboard": "Keyboard",
    "iterate_contact": "Contact", "iterate_address": "Address", "iterate_links": "Links",
    "move_up_or_relay": "Up", "move_down_or_relay": "Down",
    "iterate_work_exp": "Work Exp", "iterate_skills": "Skills",
    "cycle_date_format": "Date", "cycle_name_format": "Name Format",
    "layer2": "Layer 2", "cycle_layers": "Cycle Layers",
    "layer3_hold": "Hold Layer 3", "previous_iterator": "Prev iterator",
    "next_iterator": "Next iterator", "previous_work_exp": "Prev Work Exp",
    "next_work_exp": "Next Work Exp", "toggle_hotkeys": "Hotkeys",
    "smart_capture": "Smart Capture", "analyze_job": "Analysis",
    "open_dashboard": "Tracker", "find_company": "Find Company",
}
DEFAULT_BEHAVIOR = {
    "auto_return_contact": False, "auto_return_address": False,
    "auto_return_links": False, "auto_return_skills": True,
    "auto_return_work_exp": True, "show_border_indicator": True,
    "show_tooltips": True, "show_layer_status": False,
    "show_keyboard": True, "hotkeys_active_on_startup": False,
    "outlook_sync_enabled": False,
    "escape_long_press_ms": 750,
    "iterator_delay_ms": 250,
}
BUILTIN_PROFILE_FIELDS = (
    {"id": "first_name", "label": "First name", "group": "Identity"},
    {"id": "last_name", "label": "Last name", "group": "Identity"},
    {"id": "full_name", "label": "Full name", "group": "Identity"},
    {"id": "email", "label": "Email", "group": "Contact"},
    {"id": "phone", "label": "Phone", "group": "Contact"},
    {"id": "address", "label": "Street address", "group": "Location"},
    {"id": "city", "label": "City", "group": "Location"},
    {"id": "state", "label": "State", "group": "Location"},
    {"id": "zip", "label": "ZIP code", "group": "Location"},
    {"id": "country", "label": "Country", "group": "Location"},
    {"id": "linkedin", "label": "LinkedIn", "group": "Links"},
    {"id": "github", "label": "GitHub", "group": "Links"},
    {"id": "portfolio", "label": "Portfolio", "group": "Links"},
    {"id": "facebook", "label": "Facebook", "group": "Links"},
    {"id": "x", "label": "X", "group": "Links"},
)


def split_binding(binding: str) -> tuple[str, str | None]:
    """Split `action|label` while keeping plain action values compatible."""
    action, separator, label = binding.partition("|")
    return action.strip(), label.strip() if separator else None


GLOBAL_LAYER_ACTIONS = {"cycle_layers"}


def resolve_layer_binding(
    key: str,
    active_bindings: dict[str, str],
    all_layers: tuple[dict[str, str], ...],
) -> str:
    """Resolve a key while keeping layer exit controls globally reachable."""
    assignment, _label = split_binding(active_bindings.get(key, ""))
    if assignment in GLOBAL_LAYER_ACTIONS:
        return assignment
    for bindings in all_layers:
        control, _label = split_binding(bindings.get(key, ""))
        if control in GLOBAL_LAYER_ACTIONS:
            return control
    return assignment


@dataclass(frozen=True)
class WorkEntry:
    title: str
    company: str
    start: str
    end: str
    highlights: str = ""
    enabled: bool = True

    def paste_items(self, number: int) -> list[PasteItem]:
        group = f"Work {number}: {self.company}"
        return [
            PasteItem(f"Job {number} title", self.title, group, f"work.{number}.title"),
            PasteItem(f"Job {number} company", self.company, group, f"work.{number}.company"),
            PasteItem(f"Job {number} start", self.start, group, f"work.{number}.start"),
            PasteItem(f"Job {number} end", self.end, group, f"work.{number}.end"),
            PasteItem(
                f"Job {number} highlights",
                self.highlights,
                group,
                f"work.{number}.highlights",
            ),
        ]


@dataclass(frozen=True)
class AnswerEntry:
    title: str
    answer: str


@dataclass(frozen=True)
class CapabilityEntry:
    id: str
    type: str
    canonical_name: str
    display_name: str
    aliases: tuple[str, ...] = ()
    rating: int = 0
    match_enabled: bool = True
    iterator_enabled: bool = True
    document_enabled: bool = False
    paste_enabled: bool = False

    @property
    def name(self) -> str:
        return self.display_name or self.canonical_name

    @property
    def rateable(self) -> bool:
        return self.type in RATEABLE_ENTITY_TYPES


@dataclass(frozen=True)
class RelationshipEntry:
    source_id: str
    type: str
    target_id: str


@dataclass(frozen=True)
class CapabilitySetEntry:
    id: str
    name: str
    capability_ids: tuple[str, ...] = ()
    system: bool = False
    document_enabled: bool = True
    paste_enabled: bool = True


@dataclass(frozen=True)
class AppConfig:
    profile_items: list[PasteItem] = field(default_factory=list)
    work_history: list[WorkEntry] = field(default_factory=list)
    matrix: dict[str, str] = field(default_factory=dict)
    sequences: dict[str, list[str]] = field(default_factory=dict)
    custom_sequences: dict[str, list[str]] = field(default_factory=dict)
    custom_action_types: dict[str, str] = field(default_factory=dict)
    custom_action_auto_return: dict[str, bool] = field(default_factory=dict)
    iterator_preferences: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    layer2: dict[str, str] = field(default_factory=dict)
    layer3: dict[str, str] = field(default_factory=dict)
    hotkey_settings: dict = field(default_factory=dict)

    capabilities: list[CapabilityEntry] = field(default_factory=list)
    relationships: list[RelationshipEntry] = field(default_factory=list)
    capability_sets: list[CapabilitySetEntry] = field(default_factory=list)
    active_set_id: str = SYSTEM_SET_ALL
    view_preferences: dict[str, object] = field(default_factory=dict)
    smart_capture_settings: dict[str, object] = field(
        default_factory=default_smart_capture_settings
    )

    iterator_delay_ms: int = 250
    escape_long_press_ms: int = 750
    auto_return: dict[str, bool] = field(default_factory=dict)
    hotkeys_active_on_startup: bool = False
    show_keyboard: bool = True
    show_layer_status: bool = True
    show_tooltips: bool = True
    show_border_indicator: bool = True
    action_labels: dict[str, str] = field(default_factory=dict)
    action_displays: dict[str, dict[str, str]] = field(default_factory=dict)
    answers: list[AnswerEntry] = field(default_factory=list)
    name_format: str = "first_last"
    analysis_mode: str = "local"
    analysis_provider: str = "openai"
    openai_model: str = DEFAULT_OPENAI_MODEL
    dashboard_port: int = DEFAULT_DASHBOARD_PORT

    @property
    def analysis_model(self) -> str:
        """Provider-neutral model name for the analysis layer.

        `openai_model` remains as a compatibility field until the analyzer/provider
        refactor is complete.
        """
        return self.openai_model

    @property
    def all_items(self) -> list[PasteItem]:
        items = list(self.profile_items)
        for number, entry in enumerate(self.work_history, start=1):
            items.extend(entry.paste_items(number))
        return items

    @property
    def items_by_id(self) -> dict[str, PasteItem]:
        return {item.item_id: item for item in self.all_items}

    @property
    def capability_by_id(self) -> dict[str, CapabilityEntry]:
        return {capability.id: capability for capability in self.capabilities}

    @property
    def rateable_capabilities(self) -> list[CapabilityEntry]:
        return [capability for capability in self.capabilities if capability.rateable]

    @property
    def job_matching_capabilities(self) -> list[CapabilityEntry]:
        return sorted(
            (
                capability
                for capability in self.rateable_capabilities
                if capability.match_enabled
            ),
            key=lambda capability: (-capability.rating, capability.name.casefold()),
        )

    @property
    def active_set(self) -> CapabilitySetEntry | None:
        if self.active_set_id == SYSTEM_SET_ALL:
            return next((capability_set for capability_set in self.capability_sets if capability_set.id == SYSTEM_SET_ALL), None)
        return next((capability_set for capability_set in self.capability_sets if capability_set.id == self.active_set_id), None)

    @property
    def active_sets(self) -> list[str]:
        """Names exposed to the desktop capability-set selector."""
        capability_set = self.active_set
        return [capability_set.name if capability_set else ALL_CAPABILITIES]

    @property
    def effective_capabilities(self) -> list[CapabilityEntry]:
        candidates = [
            capability
            for capability in self.rateable_capabilities
            if capability.iterator_enabled
        ]

        if self.active_set_id == SYSTEM_SET_ALL:
            selected_ids = {capability.id for capability in candidates}
        else:
            selected_ids = {
                relationship.source_id
                for relationship in self.relationships
                if relationship.type == "relevant_to"
                and relationship.target_id == self.active_set_id
            }

        return sorted(
            (
                capability
                for capability in candidates
                if capability.id in selected_ids
            ),
            key=lambda capability: (-capability.rating, capability.name.casefold()),
        )

    @property
    def effective_skills(self) -> list[str]:
        """Names used by the current desktop paste iterator."""
        return [capability.name for capability in self.effective_capabilities]


def default_config_path() -> Path:
    """Return JAW's writable configuration path."""
    return writable_config_path()


def ensure_config_file(path: str | Path | None = None) -> Path:
    """Create or normalize JAW's small writable runtime-preferences file."""
    config_path = Path(path) if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    behavior = dict(DEFAULT_BEHAVIOR)
    smart_capture = default_smart_capture_settings()
    if config_path.exists():
        try:
            with config_path.open("rb") as config_file:
                stored = tomllib.load(config_file)
            stored_behavior = stored.get("behavior", {})
            behavior.update(
                {key: stored_behavior[key] for key in DEFAULT_BEHAVIOR if key in stored_behavior}
            )
            smart_capture = normalize_smart_capture_settings(
                stored.get("smart_capture", {})
            )
        except (OSError, tomllib.TOMLDecodeError, TypeError, ValueError):
            pass
    cleaned = _behavior_config_text(behavior, smart_capture)
    if not config_path.exists() or config_path.read_text(encoding="utf-8") != cleaned:
        config_path.write_text(cleaned, encoding="utf-8")
    return config_path


def _behavior_config_text(
    behavior: dict,
    smart_capture: dict | None = None,
) -> str:
    lines = [
        "# JAW runtime preferences.",
        "# User data, keybinds, layouts, and analysis settings live in SQLite.",
        "# Built-in initialization defaults are read-only application code.",
        "",
        "[behavior]",
    ]
    for key, default in DEFAULT_BEHAVIOR.items():
        value = behavior.get(key, default)
        rendered = str(value).lower() if isinstance(default, bool) else str(int(value))
        lines.append(f"{key} = {rendered}")

    capture = normalize_smart_capture_settings(smart_capture)
    lines.extend(("", "[smart_capture]"))
    lines.append(
        "field_order = ["
        + ", ".join(json.dumps(value) for value in capture["field_order"])
        + "]"
    )
    lines.append(
        "visible_fields = ["
        + ", ".join(json.dumps(value) for value in capture["visible_fields"])
        + "]"
    )
    for key in (
        "show_empty_fields",
        "focus_mode",
        "fill_missing",
        "report_disagreements",
        "warn_non_remote",
        "warn_on_call",
        "warn_travel",
        "warn_sponsorship",
        "dev",
    ):
        lines.append(f"{key} = {str(bool(capture[key])).lower()}")
    lines.append(f"analysis_mode = {json.dumps(str(capture['analysis_mode']))}")
    lines.append(f"ollama_model = {json.dumps(str(capture['ollama_model']))}")
    return "\n".join(lines) + "\n"


def _capability_entry(raw: dict) -> CapabilityEntry:
    entity_type = str(raw.get("type", "technology"))
    rateable = entity_type in RATEABLE_ENTITY_TYPES
    return CapabilityEntry(
        id=str(raw.get("id", "")),
        type=entity_type,
        canonical_name=str(raw.get("canonical_name", "")),
        display_name=str(
            raw.get("display_name")
            or raw.get("canonical_name")
            or ""
        ),
        aliases=tuple(str(alias) for alias in raw.get("aliases", [])),
        rating=int(raw.get("rating", 0)) if rateable else 0,
        match_enabled=bool(raw.get("match_enabled", True)) if rateable else False,
        iterator_enabled=bool(raw.get("iterator_enabled", True)) if rateable else False,
        document_enabled=(
            bool(raw.get("document_enabled", True)) if entity_type == "set" else False
        ),
        paste_enabled=(
            bool(raw.get("paste_enabled", True)) if entity_type == "set" else False
        ),
    )


def _relationship_entry(raw: dict) -> RelationshipEntry:
    return RelationshipEntry(
        source_id=str(raw.get("source_id", "")),
        type=str(raw.get("type", "")),
        target_id=str(raw.get("target_id", "")),
    )


def _build_capability_sets(
    capabilities: list[CapabilityEntry],
    relationships: list[RelationshipEntry],
) -> list[CapabilitySetEntry]:
    by_id = {capability.id: capability for capability in capabilities}
    rateable = [capability for capability in capabilities if capability.rateable]

    all_capabilities = tuple(
        capability.id for capability in rateable if capability.iterator_enabled
    )
    matching_capabilities = tuple(
        capability.id for capability in rateable if capability.match_enabled
    )

    capability_sets = [
        CapabilitySetEntry(
            id=SYSTEM_SET_ALL,
            name=ALL_CAPABILITIES,
            capability_ids=all_capabilities,
            system=True,
            document_enabled=True,
            paste_enabled=True,
        ),
        CapabilitySetEntry(
            id=JOB_MATCHING_SELECTION,
            name=JOB_MATCHING_SELECTION,
            capability_ids=matching_capabilities,
            system=True,
            document_enabled=False,
            paste_enabled=False,
        ),
    ]

    relevant: dict[str, list[str]] = {}
    for relationship in relationships:
        if relationship.type != "relevant_to":
            continue
        source = by_id.get(relationship.source_id)
        target = by_id.get(relationship.target_id)
        if source and source.rateable and target and target.type == "set":
            relevant.setdefault(target.id, []).append(source.id)

    set_entities = sorted(
        (
            capability
            for capability in capabilities
            if capability.type == "set"
        ),
        key=lambda capability: capability.name.casefold(),
    )

    for capability_set in set_entities:
        capability_ids = tuple(
            capability_id
            for capability_id in relevant.get(capability_set.id, [])
            if capability_id in by_id and by_id[capability_id].rateable
        )
        capability_sets.append(
            CapabilitySetEntry(
                id=capability_set.id,
                name=capability_set.name,
                capability_ids=capability_ids,
                system=False,
                document_enabled=capability_set.document_enabled,
                paste_enabled=capability_set.paste_enabled,
            )
        )

    return capability_sets


def load_config(path: str | Path | None = None, *, user_id: int | None = None) -> AppConfig:
    config_path = ensure_config_file(path)
    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)
    smart_capture_settings = normalize_smart_capture_settings(
        raw.get("smart_capture", {})
    )

    profile_items = [
        PasteItem(
            label=str(item["label"]),
            value="",
            group=str(item.get("group", "Profile")),
            item_id=str(item["id"]),
        )
        for item in BUILTIN_PROFILE_FIELDS
    ]
    work_history: list[WorkEntry] = []
    matrix = dict(DEFAULT_MATRIX_BASE)
    sequences = {key: list(values) for key, values in DEFAULT_SEQUENCES.items()}
    layer2 = dict(DEFAULT_MATRIX_LAYER2)
    layer3 = dict(DEFAULT_MATRIX_LAYER3)
    keyboard_layout = DEFAULT_KEYBOARD_LAYOUT
    keyboard_custom_layouts: dict[str, list[list[str]]] = {}
    hotkey_settings = {
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
    }

    capabilities: list[CapabilityEntry] = []
    relationships: list[RelationshipEntry] = []
    capability_sets: list[CapabilitySetEntry] = [
        CapabilitySetEntry(id=SYSTEM_SET_ALL, name=ALL_CAPABILITIES, system=True),
        CapabilitySetEntry(id=JOB_MATCHING_SELECTION, name=JOB_MATCHING_SELECTION, system=True),
    ]
    active_set_id = SYSTEM_SET_ALL
    view_preferences: dict[str, object] = {}

    custom_sequences: dict[str, list[str]] = {}
    custom_action_labels: dict[str, str] = {}
    custom_action_types: dict[str, str] = {}
    custom_action_auto_return: dict[str, bool] = {}
    iterator_preferences: dict[str, dict[str, list[str]]] = {}

    user_database_path = config_path.parent / "data" / "jaw.db"
    user_store = UserDataStore(user_database_path)
    user_data: dict = {}

    if user_database_path.exists():
        user_data = user_store.read(user_id=user_id)

        user_values = dict(user_data.get("user", {}))
        user_values["phone"] = user_values.get("phone_number", "")
        user_values["address"] = user_values.get("street_address", "")
        user_values["zip"] = user_values.get("zip_code", "")
        user_values["full_name"] = " ".join(
            value
            for value in (
                user_values.get("first_name", ""),
                user_values.get("last_name", ""),
            )
            if value
        )

        profile_items = [
            PasteItem(
                label=item.label,
                value=user_values.get(item.item_id, item.value),
                group=item.group,
                item_id=item.item_id,
            )
            for item in profile_items
        ]

        profile_items.extend(
            PasteItem(
                label=str(field.get("label", field.get("id", "Custom field"))),
                value=str(field.get("value", "")),
                group="Custom",
                item_id=str(field.get("id", "")),
            )
            for field in user_data.get("custom_fields", [])
            if field.get("id")
        )

        custom_fields_by_id = {
            str(field.get("id", "")): field
            for field in user_data.get("custom_fields", [])
            if field.get("id")
        }

        for action in user_data.get("custom_actions", []):
            action_id = str(action.get("id", ""))
            label = str(action.get("label", "")).strip()
            field_ids = [
                str(field_id)
                for field_id in action.get("field_ids", [])
                if str(field_id) in custom_fields_by_id
            ]

            if not action_id or not label:
                continue

            custom_action_labels[action_id] = label
            custom_action_types[action_id] = str(action.get("type", "single"))
            custom_action_auto_return[action_id] = bool(action.get("auto_return", False))

            if action.get("type") == "iterator":
                custom_sequences[action_id] = field_ids
            else:
                field = custom_fields_by_id.get(field_ids[0]) if field_ids else None
                profile_items.append(
                    PasteItem(
                        label=label,
                        value=str(field.get("value", "")) if field else "",
                        group="Custom Actions",
                        item_id=action_id,
                    )
                )

        work_history = [
            WorkEntry(
                title=str(entry.get("title", "")),
                company=str(entry.get("company", "")),
                start=str(entry.get("start", "")),
                end=str(entry.get("end", "")),
                highlights=str(entry.get("highlights", "")).strip(),
                enabled=bool(entry.get("enabled", True)),
            )
            for entry in user_data.get("work_history", [])
        ]

        iterator_preferences = {
            str(action): {
                "order": [str(item) for item in value.get("order", [])],
                "disabled": [str(item) for item in value.get("disabled", [])],
            }
            for action, value in user_data.get("iterator_preferences", {}).items()
            if isinstance(value, dict)
        }

        capability_model = dict(user_data.get("capability_model", {}))
        capabilities = [
            _capability_entry(entity)
            for entity in capability_model.get("entities", user_data.get("entities", []))
        ]
        relationships = [
            _relationship_entry(relationship)
            for relationship in capability_model.get(
                "relationships", user_data.get("relationships", [])
            )
        ]
        active_set_id = str(
            capability_model.get("active_set_id", SYSTEM_SET_ALL)
            or SYSTEM_SET_ALL
        )
        view_preferences = dict(
            capability_model.get(
                "view_preferences", user_data.get("view_preferences", {})
            )
        )
        capability_sets = _build_capability_sets(capabilities, relationships)

        valid_set_ids = {
            capability_set.id
            for capability_set in capability_sets
            if capability_set.id == SYSTEM_SET_ALL
            or (not capability_set.system and capability_set.paste_enabled)
        }
        if active_set_id not in valid_set_ids:
            active_set_id = SYSTEM_SET_ALL

        name_format = (
            "full" if user_data.get("name_format") == "full" else "first_last"
        )
        sequences["Q"] = (
            ["full_name", "email", "phone"]
            if name_format == "full"
            else ["first_name", "last_name", "email", "phone"]
        )
    else:
        name_format = "first_last"

    profile_values = {
        item.item_id: item.value.strip()
        for item in profile_items
    }
    for sequence_key in ("Q", "A", "LINKS"):
        sequences[sequence_key] = [
            item_id
            for item_id in sequences.get(sequence_key, [])
            if profile_values.get(item_id, "")
        ]

    behavior = raw.get("behavior", {})
    iterator_delay_ms = int(
        behavior.get(
            "iterator_delay_ms",
            DEFAULT_BEHAVIOR["iterator_delay_ms"],
        )
    )
    escape_long_press_ms = max(
        100,
        int(
            behavior.get(
                "escape_long_press_ms",
                DEFAULT_BEHAVIOR["escape_long_press_ms"],
            )
        ),
    )
    auto_return = {
        category: bool(
            behavior.get(
                f"auto_return_{category}",
                DEFAULT_BEHAVIOR[f"auto_return_{category}"],
            )
        )
        for category in ("contact", "address", "links", "skills", "work_exp")
    }
    hotkeys_active_on_startup = bool(
        behavior.get(
            "hotkeys_active_on_startup",
            DEFAULT_BEHAVIOR["hotkeys_active_on_startup"],
        )
    )
    show_keyboard = bool(
        behavior.get("show_keyboard", DEFAULT_BEHAVIOR["show_keyboard"])
    )
    show_layer_status = bool(
        behavior.get("show_layer_status", DEFAULT_BEHAVIOR["show_layer_status"])
    )
    show_tooltips = bool(
        behavior.get("show_tooltips", DEFAULT_BEHAVIOR["show_tooltips"])
    )
    show_border_indicator = bool(
        behavior.get(
            "show_border_indicator",
            DEFAULT_BEHAVIOR["show_border_indicator"],
        )
    )

    action_labels = dict(BUILTIN_ACTION_LABELS)
    action_labels.update(custom_action_labels)

    action_displays: dict[str, dict[str, str]] = {}
    binding_labels: dict[str, str] = {}
    for default_layer in (matrix, layer2, layer3):
        for binding in default_layer.values():
            action, label = split_binding(str(binding))
            if action and label:
                binding_labels[action] = label

    if user_database_path.exists():
        keybinds = user_data.get("keybinds", {})
        keyboard_layout = str(
            user_data.get("keyboard_layout") or DEFAULT_KEYBOARD_LAYOUT
        )
        keyboard_custom_layouts = dict(keybinds.get("custom_layouts", {}))
        if keybinds.get("configured"):
            matrix = {
                str(key).upper(): str(value)
                for key, value in keybinds["base"].items()
            }
            layer2 = {
                str(key).upper(): str(value)
                for key, value in keybinds["layer2"].items()
            }
            layer3 = {
                str(key).upper(): str(value)
                for key, value in keybinds.get("layer3", {}).items()
            }
            stored_hotkeys = keybinds.get("hotkey_settings", {})
            hotkey_settings = {
                **hotkey_settings,
                **stored_hotkeys,
                "layers": {
                    name: {
                        **hotkey_settings["layers"][name],
                        **stored_hotkeys.get("layers", {}).get(name, {}),
                    }
                    for name in ("layer2", "layer3")
                },
            }

        for action, display in keybinds.get("action_displays", {}).items():
            action_displays[str(action)] = {
                "label": str(display.get("label", "")),
                "icons": infer_icon_names(str(action), display),
            }
            label = str(display.get("label", "")).strip()
            if label:
                action_labels[str(action)] = label
                binding_labels[str(action)] = label

        def labeled(bindings: dict[str, str]) -> dict[str, str]:
            return {
                key: (
                    f"{action}|{binding_labels.get(action) or action_labels.get(action, '')}"
                    if action
                    and action != "layer2"
                    and "|" not in action
                    and (action in binding_labels or action in action_labels)
                    else action
                )
                for key, action in bindings.items()
            }

        matrix = labeled(matrix)
        layer2 = labeled(layer2)
        layer3 = labeled(layer3)

    assigned_actions = {
        split_binding(binding)[0]
        for bindings in (matrix, layer2, layer3)
        for binding in bindings.values()
    }
    if "analyze_job" not in assigned_actions and not matrix.get("P01"):
        matrix["P01"] = "analyze_job|Analysis"
    action_displays.setdefault(
        "analyze_job", {"label": "Analysis", "icons": ["analysis"]}
    )

    answers: list[AnswerEntry] = []
    if user_database_path.exists():
        answers = [
            AnswerEntry(
                title=str(entry.get("title", "")),
                answer=str(entry.get("answer", "")).strip(),
            )
            for entry in user_data.get("answers", [])
            if entry.get("title")
        ]

    analysis_settings = (
        user_data.get("analysis_settings", {})
        if user_database_path.exists()
        else {}
    )
    analysis_mode = str(analysis_settings.get("mode", "local")).lower()
    if analysis_mode not in {"local", "generative"}:
        analysis_mode = "local"
    analysis_provider = str(
        analysis_settings.get("provider", "openai")
    ).lower()
    openai_model = str(
        analysis_settings.get("model", DEFAULT_OPENAI_MODEL)
    )

    layout_rows = resolve_keyboard_layout(
        keyboard_layout,
        keyboard_custom_layouts,
    )
    matrix = position_bindings_to_layout_keys(matrix, layout_rows)
    layer2 = position_bindings_to_layout_keys(layer2, layout_rows)
    layer3 = position_bindings_to_layout_keys(layer3, layout_rows)

    return AppConfig(
        profile_items=profile_items,
        work_history=work_history,
        matrix=matrix,
        sequences=sequences,
        custom_sequences=custom_sequences,
        custom_action_types=custom_action_types,
        custom_action_auto_return=custom_action_auto_return,
        iterator_preferences=iterator_preferences,
        layer2=layer2,
        layer3=layer3,
        hotkey_settings=hotkey_settings,
        capabilities=capabilities,
        relationships=relationships,
        capability_sets=capability_sets,
        active_set_id=active_set_id,
        view_preferences=view_preferences,
        smart_capture_settings=smart_capture_settings,
        iterator_delay_ms=iterator_delay_ms,
        escape_long_press_ms=escape_long_press_ms,
        auto_return=auto_return,
        hotkeys_active_on_startup=hotkeys_active_on_startup,
        show_keyboard=show_keyboard,
        show_layer_status=show_layer_status,
        show_tooltips=show_tooltips,
        show_border_indicator=show_border_indicator,
        action_labels=action_labels,
        action_displays=action_displays,
        answers=answers,
        name_format=name_format,
        analysis_mode=analysis_mode,
        analysis_provider=analysis_provider,
        openai_model=openai_model,
        dashboard_port=DEFAULT_DASHBOARD_PORT,
    )


def save_behavior_settings(
    auto_return: dict[str, bool],
    iterator_delay_ms: int,
    escape_long_press_ms: int = 750,
    show_keyboard: bool = True,
    show_layer_status: bool = True,
    show_tooltips: bool = True,
    show_border_indicator: bool = True,
    hotkeys_active_on_startup: bool = False,
    smart_capture_settings: dict | None = None,
    path: str | Path | None = None,
) -> None:
    """Persist runtime-adjustable desktop behavior and Smart Capture settings."""
    config_path = Path(path) if path else default_config_path()
    values = {
        "iterator_delay_ms": iterator_delay_ms,
        "escape_long_press_ms": max(100, escape_long_press_ms),
        "hotkeys_active_on_startup": hotkeys_active_on_startup,
        "show_keyboard": show_keyboard,
        "show_layer_status": show_layer_status,
        "show_tooltips": show_tooltips,
        "show_border_indicator": show_border_indicator,
        **{
            f"auto_return_{category}": enabled
            for category, enabled in auto_return.items()
        },
    }
    stored_behavior: dict = {}
    if config_path.exists():
        try:
            with config_path.open("rb") as config_file:
                stored = tomllib.load(config_file)
            stored_behavior = dict(stored.get("behavior", {}))
            if smart_capture_settings is None:
                smart_capture_settings = stored.get("smart_capture", {})
        except (OSError, tomllib.TOMLDecodeError):
            smart_capture_settings = smart_capture_settings or None
    values["outlook_sync_enabled"] = bool(
        stored_behavior.get(
            "outlook_sync_enabled",
            DEFAULT_BEHAVIOR["outlook_sync_enabled"],
        )
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _behavior_config_text(values, smart_capture_settings),
        encoding="utf-8",
    )
