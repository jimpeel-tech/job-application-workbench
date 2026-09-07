from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..config import RATING_GUIDANCE
from ..userdata import UserDataStore

CAPABILITY_API_VERSION = 2
SYSTEM_SET_ALL_ID = "__all__"

CAPABILITY_SCHEMA = {
    "api_version": CAPABILITY_API_VERSION,
    "entity_types": [
        {
            "value": "competency",
            "label": "Competency",
            "rateable": True,
            "creatable": True,
            "description": "What you can do or own as a professional capability.",
        },
        {
            "value": "technology",
            "label": "Technology",
            "rateable": True,
            "creatable": True,
            "description": "A technical platform, language, protocol, or domain.",
        },
        {
            "value": "product",
            "label": "Product / Tool",
            "rateable": True,
            "creatable": True,
            "description": (
                "A specific product, managed service, implementation, or tool."
            ),
        },
        {
            "value": "set",
            "label": "Capability Set",
            "rateable": False,
            "creatable": False,
            "description": "A user-managed capability subset used as an optional iterator lens.",
        },
    ],
    "relationship_types": [
        {
            "value": "relevant_to",
            "label": "Relevant to",
            "description": "Capability → capability-set membership.",
        },
        {
            "value": "uses",
            "label": "Uses",
            "description": "The source capability uses the target capability.",
        },
        {
            "value": "based_on",
            "label": "Based on",
            "description": "The source builds on or is implemented from the target.",
        },
        {
            "value": "provided_by",
            "label": "Provided by",
            "description": "The source is provided by the target platform/provider.",
        },
        {
            "value": "related_to",
            "label": "Related to",
            "description": "General semantic adjacency without implying experience.",
        },
    ],
    "ratings": [
        {
            "value": value,
            "label": guidance["label"],
            "description": guidance["description"],
        }
        for value, guidance in RATING_GUIDANCE.items()
    ],
    "view_preferences": {
        "hierarchy": {
            "section_granularity": {"min": 1, "max": 5, "default": 3},
            "entity_granularity": {"min": 1, "max": 5, "default": 3},
            "l1_section_target": {"min": 4, "max": 8, "default": 6},
            "group_min_entities": {"min": 1, "max": 10, "default": 3},
        },
        "layout": {
            "pane_modes": ["fixed", "auto", "off"],
            "left_pane": "fixed",
            "right_pane": "fixed",
            "show_use_guide": True,
        },
    },
}


def entity_name(entity: dict[str, Any]) -> str:
    """Return the user-facing name without changing graph identity."""

    return str(entity.get("display_name") or entity.get("canonical_name") or "")


class CapabilityService:
    """Coordinate capability-graph reads and mutations for application clients."""

    def __init__(self, store: UserDataStore):
        self._store = store

    @property
    def schema(self) -> dict[str, Any]:
        return CAPABILITY_SCHEMA

    def state(self) -> dict[str, Any]:
        data = self._store.read()
        model = dict(data.get("capability_model", {}))
        entities = [
            dict(entity)
            for entity in model.get("entities", data.get("entities", []))
        ]
        relationships = [
            dict(relationship)
            for relationship in model.get(
                "relationships", data.get("relationships", [])
            )
        ]
        active_set_id = str(
            model.get("active_set_id")
            or data.get("active_set_id")
            or SYSTEM_SET_ALL_ID
        )

        by_id = {
            str(entity.get("id", "")): entity
            for entity in entities
            if entity.get("id")
        }

        set_members: dict[str, list[str]] = {}
        for relationship in relationships:
            if relationship.get("type") != "relevant_to":
                continue
            source_id = str(relationship.get("source_id", ""))
            target_id = str(relationship.get("target_id", ""))
            source = by_id.get(source_id)
            target = by_id.get(target_id)
            if (
                source
                and target
                and target.get("type") == "set"
                and source.get("type") != "set"
            ):
                set_members.setdefault(target_id, []).append(source_id)

        sets = [
            {
                "id": SYSTEM_SET_ALL_ID,
                "name": "All",
                "system": True,
                "document_enabled": True,
                "paste_enabled": True,
                "capability_ids": [
                    str(entity["id"])
                    for entity in entities
                    if entity.get("type") != "set"
                    and bool(entity.get("iterator_enabled", True))
                ],
            }
        ]
        sets.extend(
            {
                "id": str(entity["id"]),
                "name": entity_name(entity),
                "system": False,
                "document_enabled": bool(entity.get("document_enabled", True)),
                "paste_enabled": bool(entity.get("paste_enabled", True)),
                "capability_ids": sorted(
                    set_members.get(str(entity["id"]), []),
                    key=lambda entity_id: entity_name(
                        by_id.get(entity_id, {})
                    ).casefold(),
                ),
            }
            for entity in sorted(
                (entity for entity in entities if entity.get("type") == "set"),
                key=lambda entity: entity_name(entity).casefold(),
            )
        )

        rateable_entities = [
            entity for entity in entities if entity.get("type") != "set"
        ]
        stats = {
            "entities": len(entities),
            "capabilities": len(rateable_entities),
            "sets": sum(entity.get("type") == "set" for entity in entities),
            "matching_enabled": sum(
                bool(entity.get("match_enabled", True))
                for entity in rateable_entities
            ),
            "unrated": sum(
                int(entity.get("rating", 0)) == 0 for entity in rateable_entities
            ),
        }

        return {
            "api_version": CAPABILITY_API_VERSION,
            "model_version": int(model.get("version", 1)),
            "entities": entities,
            "relationships": relationships,
            "sets": sets,
            "active_set_id": active_set_id,
            "view_preferences": model.get(
                "view_preferences", data.get("view_preferences", {})
            ),
            "stats": stats,
        }

    def find_entity(self, entity_id: str) -> dict[str, Any]:
        entity_id = str(entity_id).strip()
        if not entity_id:
            raise ValueError("Entity ID is required")
        for entity in self.state()["entities"]:
            if str(entity.get("id", "")) == entity_id:
                return entity
        raise ValueError(f"Unknown entity: {entity_id}")

    def names_for_ids(self, entity_ids: Iterable[object]) -> list[str]:
        state = self.state()
        by_id = {
            str(entity.get("id", "")): entity for entity in state["entities"]
        }
        names: list[str] = []
        for raw_id in entity_ids:
            entity_id = str(raw_id)
            entity = by_id.get(entity_id)
            if entity is None:
                raise ValueError(f"Unknown entity: {entity_id}")
            if entity.get("type") == "set":
                raise ValueError(f"{entity_name(entity)} is a capability set, not a capability")
            names.append(entity_name(entity))
        return names

    def upsert_entity(self, entity: dict[str, Any]) -> dict[str, Any]:
        if str(entity.get("type", "")).strip().lower() == "set":
            raise ValueError("Capability sets use the capability-set API")
        return self._store.upsert_entity(entity)

    def delete_entities(self, entity_ids: Iterable[object]) -> None:
        wanted = [
            str(entity_id).strip()
            for entity_id in entity_ids
            if str(entity_id).strip()
        ]
        if not wanted:
            raise ValueError("At least one entity ID is required")
        for entity_id in wanted:
            entity = self.find_entity(entity_id)
            if entity.get("type") == "set":
                raise ValueError("Capability sets use the capability-set API")
        self._store.delete_entities_by_id(wanted)

    def update_flags(
        self,
        entity_ids: Iterable[object],
        *,
        rating: int | None = None,
        match_enabled: bool | None = None,
        iterator_enabled: bool | None = None,
    ) -> None:
        wanted = [
            str(entity_id).strip()
            for entity_id in entity_ids
            if str(entity_id).strip()
        ]
        if not wanted:
            raise ValueError("At least one entity ID is required")

        state = self.state()
        by_id = {
            str(entity.get("id", "")): entity for entity in state["entities"]
        }

        for entity_id in wanted:
            entity = by_id.get(entity_id)
            if entity is None:
                raise ValueError(f"Unknown entity: {entity_id}")
            if entity.get("type") == "set":
                raise ValueError("Capability sets cannot be rated or enabled for matching")

            if rating is not None:
                self._store.upsert_entity(
                    {
                        "id": entity_id,
                        "type": str(entity.get("type", "technology")),
                        "rating": min(5, max(0, int(rating))),
                    }
                )

            if match_enabled is not None:
                self._store.set_entity_match_enabled(entity_id, bool(match_enabled))

            if iterator_enabled is not None:
                self._store.set_entity_iterator_enabled(
                    entity_id, bool(iterator_enabled)
                )

    def save_relationships(
        self,
        relationships: list[dict[str, Any]],
        *,
        replace: bool = False,
    ) -> None:
        self._store.save_relationships(relationships, replace=replace)

    def save_view_preferences(self, preferences: dict[str, Any]) -> None:
        self._store.save_view_preferences(preferences)

    def save_set(
        self,
        set_id: str,
        name: str,
        capability_ids: list[str],
        *,
        document_enabled: bool | None = None,
        paste_enabled: bool | None = None,
    ) -> str:
        return self._store.save_capability_set(
            set_id,
            name,
            capability_ids,
            document_enabled=document_enabled,
            paste_enabled=paste_enabled,
        )

    def delete_set(self, set_id: str) -> None:
        self._store.delete_set_by_id(set_id)

    def set_active_set(self, set_id: str) -> None:
        self._store.set_active_set_id(set_id)

    def clear(self, *, confirm: bool) -> None:
        if not confirm:
            raise ValueError("Capability clear requires confirm=true")
        self._store.clear_capabilities()

    def apply_smart_add(self, package: dict[str, Any]) -> dict[str, Any]:
        if str(package.get("format", "")) != "jaw-smart-add":
            raise ValueError("Smart Add result has an invalid format")
        if int(package.get("version", 0)) != 3:
            raise ValueError(
                "Unsupported Smart Add result version. "
                "Generate a fresh Smart Add prompt and use version 3."
            )

        raw_entities = list(package.get("entities", []))
        raw_relationships = list(package.get("relationships", []))
        raw_hierarchy = dict(package.get("hierarchy", {}))
        raw_root = raw_hierarchy.get("root")

        state = self.state()
        existing_by_id = {
            str(entity.get("id", "")): entity
            for entity in state["entities"]
            if entity.get("id") and entity.get("type") != "set"
        }
        existing_by_name: dict[str, str] = {}
        for entity_id, entity in existing_by_id.items():
            for value in (
                entity.get("canonical_name"),
                entity.get("display_name"),
                *list(entity.get("aliases", [])),
            ):
                text = str(value or "").strip()
                if text:
                    existing_by_name.setdefault(text.casefold(), entity_id)

        allowed_types = {"competency", "technology", "product"}
        allowed_relationships = {
            "uses",
            "based_on",
            "provided_by",
            "related_to",
        }

        planned_refs = set(existing_by_id)
        normalized_entities: list[dict[str, Any]] = []
        seen_refs: set[str] = set()

        for raw in raw_entities:
            if not isinstance(raw, dict):
                raise ValueError("Every Smart Add entity must be an object")
            ref = str(raw.get("ref", "")).strip()
            entity_id = str(raw.get("entity_id", "") or "").strip()
            entity_type = str(raw.get("type", "")).strip().lower()
            canonical_name = str(raw.get("canonical_name", "")).strip()
            display_name = str(raw.get("display_name", "")).strip()
            aliases = [
                str(alias).strip()
                for alias in raw.get("aliases", [])
                if str(alias).strip()
            ]

            if not ref:
                raise ValueError("Every Smart Add entity needs a ref")
            if ref in seen_refs:
                raise ValueError(f"Duplicate Smart Add ref: {ref}")
            if entity_type not in allowed_types:
                raise ValueError(
                    f"Unsupported Smart Add entity type: {entity_type}"
                )
            if not canonical_name and not display_name:
                raise ValueError(f"Smart Add entity {ref} has no name")
            if entity_id and entity_id not in existing_by_id:
                raise ValueError(f"Unknown existing entity_id: {entity_id}")
            if entity_id and ref != entity_id:
                raise ValueError(
                    "Existing entities must use their entity_id as ref"
                )
            if not entity_id and not ref.startswith("new:"):
                raise ValueError(
                    "New Smart Add entity refs must begin with "
                    f"'new:': {ref}"
                )
            if entity_id and ref.startswith("new:"):
                raise ValueError(
                    "Existing entity refs cannot begin with "
                    f"'new:': {ref}"
                )

            forbidden_aliases = {
                canonical_name.casefold(),
                display_name.casefold(),
            }
            cleaned_aliases: list[str] = []
            alias_keys: set[str] = set()
            for alias in aliases:
                key = alias.casefold()
                if not key or key in forbidden_aliases or key in alias_keys:
                    continue
                alias_keys.add(key)
                cleaned_aliases.append(alias)

            seen_refs.add(ref)
            planned_refs.add(ref)
            normalized_entities.append(
                {
                    "ref": ref,
                    "entity_id": entity_id,
                    "type": entity_type,
                    "canonical_name": canonical_name or display_name,
                    "display_name": display_name or canonical_name,
                    "aliases": cleaned_aliases,
                }
            )

        def validate_ref(value: object, label: str) -> str:
            ref = str(value or "").strip()
            if not ref or ref not in planned_refs:
                raise ValueError(
                    f"{label} references unknown entity ref: {ref}"
                )
            return ref

        normalized_relationships: list[dict[str, str]] = []
        for raw in raw_relationships:
            if not isinstance(raw, dict):
                raise ValueError(
                    "Every Smart Add relationship must be an object"
                )
            relationship_type = str(raw.get("type", "")).strip()
            if relationship_type == "relevant_to":
                raise ValueError(
                    "Smart Add v3 does not create relevant_to relationships. "
                    "Capability-set membership is managed separately."
                )
            if relationship_type not in allowed_relationships:
                raise ValueError(
                    f"Unsupported relationship type: {relationship_type}"
                )
            source_ref = validate_ref(raw.get("source_ref"), "Relationship")
            target_ref = validate_ref(raw.get("target_ref"), "Relationship")
            if source_ref == target_ref:
                raise ValueError(
                    f"Relationship cannot reference itself: {source_ref}"
                )
            normalized_relationships.append(
                {
                    "source_ref": source_ref,
                    "type": relationship_type,
                    "target_ref": target_ref,
                }
            )

        if planned_refs and not isinstance(raw_root, dict):
            raise ValueError("Smart Add v3 requires hierarchy.root")

        hierarchy_refs: list[str] = []
        category_count = 0
        max_depth = 0

        def normalize_tree_node(
            raw_node: object,
            path: tuple[str, ...],
            depth: int,
            *,
            is_root: bool = False,
        ) -> dict[str, Any]:
            nonlocal category_count, max_depth

            if not isinstance(raw_node, dict):
                raise ValueError(
                    "Every hierarchy category must be an object"
                )

            name = str(raw_node.get("name", "")).strip()
            if not name:
                raise ValueError("Hierarchy category name is required")

            entity_refs = [
                validate_ref(
                    ref,
                    f"Hierarchy category {' > '.join(path + (name,))}",
                )
                for ref in raw_node.get("entity_refs", [])
            ]

            raw_children = raw_node.get("children", [])
            if not isinstance(raw_children, list):
                raise ValueError(
                    f"Hierarchy category {name} children must be an array"
                )

            children = []
            child_names: set[str] = set()
            for raw_child in raw_children:
                child_name = (
                    str(raw_child.get("name", "")).strip()
                    if isinstance(raw_child, dict)
                    else ""
                )
                child_key = child_name.casefold()
                if child_name and child_key in child_names:
                    raise ValueError(
                        f"Duplicate child category under {name}: {child_name}"
                    )
                if child_name:
                    child_names.add(child_key)
                children.append(
                    normalize_tree_node(
                        raw_child,
                        path + (name,),
                        depth + 1,
                    )
                )

            # Entities live only on leaves so every horizontal cut of the
            # projection remains a clean partition of the canonical graph.
            if children and entity_refs:
                raise ValueError(
                    f"Hierarchy category {name} has both children and "
                    "entity_refs. Smart Add v3 requires entities to be "
                    "attached only to leaf categories."
                )
            if children and len(children) == 1 and not is_root:
                raise ValueError(
                    f"Hierarchy category {name} has only one child. "
                    "Collapse redundant single-child category chains."
                )
            if not children and not entity_refs and planned_refs:
                raise ValueError(
                    f"Leaf hierarchy category {name} contains no entities"
                )

            hierarchy_refs.extend(entity_refs)
            category_count += 1
            max_depth = max(max_depth, depth)

            return {
                "name": name,
                "entity_refs": entity_refs,
                "children": children,
            }

        normalized_root = None
        if isinstance(raw_root, dict):
            normalized_root = normalize_tree_node(
                raw_root,
                (),
                0,
                is_root=True,
            )

        duplicates = sorted(
            ref
            for ref in set(hierarchy_refs)
            if hierarchy_refs.count(ref) > 1
        )
        if duplicates:
            raise ValueError(
                "Hierarchy contains duplicate entity refs: "
                + ", ".join(duplicates[:8])
            )

        missing = sorted(planned_refs - set(hierarchy_refs))
        extra = sorted(set(hierarchy_refs) - planned_refs)
        if missing:
            raise ValueError(
                "Hierarchy is missing entity refs: " + ", ".join(missing[:8])
            )
        if extra:
            raise ValueError(
                "Hierarchy contains unknown entity refs: "
                + ", ".join(extra[:8])
            )

        ref_to_id = {entity_id: entity_id for entity_id in existing_by_id}
        added = 0
        updated = 0

        def dedupe(values: Iterable[object]) -> list[str]:
            result: list[str] = []
            seen: set[str] = set()
            for value in values:
                text = str(value or "").strip()
                key = text.casefold()
                if text and key not in seen:
                    result.append(text)
                    seen.add(key)
            return result

        for item in normalized_entities:
            existing_id = item["entity_id"]
            if not existing_id:
                existing_id = existing_by_name.get(
                    item["canonical_name"].casefold()
                ) or existing_by_name.get(item["display_name"].casefold())

            if existing_id:
                existing = existing_by_id[existing_id]
                merged_aliases = dedupe(
                    list(existing.get("aliases", [])) + item["aliases"]
                )
                result = self._store.upsert_entity(
                    {
                        "id": existing_id,
                        "type": item["type"],
                        "canonical_name": item["canonical_name"],
                        # display_name remains user-owned.
                        "aliases": merged_aliases,
                    }
                )
                ref_to_id[item["ref"]] = str(result["id"])
                updated += 1
            else:
                result = self._store.upsert_entity(
                    {
                        "type": item["type"],
                        "canonical_name": item["canonical_name"],
                        "display_name": item["display_name"],
                        "aliases": item["aliases"],
                        "rating": 0,
                        "match_enabled": True,
                        "iterator_enabled": True,
                    }
                )
                entity_id = str(result["id"])
                ref_to_id[item["ref"]] = entity_id
                existing_by_id[entity_id] = result
                for name in (
                    result.get("canonical_name"),
                    result.get("display_name"),
                    *list(result.get("aliases", [])),
                ):
                    text = str(name or "").strip()
                    if text:
                        existing_by_name.setdefault(text.casefold(), entity_id)
                added += 1

        mapped_relationships = [
            {
                "source_id": ref_to_id[item["source_ref"]],
                "type": item["type"],
                "target_id": ref_to_id[item["target_ref"]],
            }
            for item in normalized_relationships
        ]
        if mapped_relationships:
            self._store.save_relationships(mapped_relationships, replace=False)

        def map_tree_node(node: dict[str, Any]) -> dict[str, Any]:
            return {
                "name": node["name"],
                "entity_ids": [ref_to_id[ref] for ref in node["entity_refs"]],
                "children": [map_tree_node(child) for child in node["children"]],
            }

        after_entities = self.state()
        preferences = dict(after_entities.get("view_preferences", {}))
        hierarchy_preferences = dict(preferences.get("hierarchy", {}))
        hierarchy_preferences["projection"] = {
            "version": 3,
            "source": "smart-add",
            "tree": (
                map_tree_node(normalized_root) if normalized_root else None
            ),
        }
        preferences["hierarchy"] = hierarchy_preferences
        self._store.save_view_preferences(preferences)

        return {
            "ok": True,
            "summary": {
                "added": added,
                "updated": updated,
                "relationships": len(mapped_relationships),
                "categories": category_count,
                "depth": max_depth,
            },
            "capabilities": self.state(),
        }
