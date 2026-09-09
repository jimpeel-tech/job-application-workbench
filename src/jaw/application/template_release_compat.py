"""Version compatibility for official JAW template repository releases."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path
from typing import Any

RELEASE_REGISTRY_FORMAT_VERSION = 1
TEMPLATE_PACKAGE_FORMAT_VERSION = 1
SUPPORTED_TEMPLATE_APIS = frozenset({1})

_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_VERSION_PREFIX = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
_RANGE_CLAUSE = re.compile(r"^(>=|<=|>|<|==)?\s*(\d+\.\d+\.\d+)$")


def _source_project_version() -> str:
    project = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if not project.is_file():
        return ""
    try:
        value = tomllib.loads(project.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    project_table = value.get("project") if isinstance(value, dict) else None
    if not isinstance(project_table, dict):
        return ""
    return str(project_table.get("version") or "").strip()


def current_jaw_version() -> str:
    """Return JAW's runtime version without duplicating the release number in code.

    A source checkout prefers pyproject.toml so an editable install cannot leave stale
    distribution metadata after a version bump. Packaged builds fall back to the
    distribution metadata copied into the executable by tools/build_windows.py.
    """

    override = str(os.environ.get("JAW_VERSION") or "").strip()
    source_version = _source_project_version()
    if override:
        candidate = override
    elif source_version:
        candidate = source_version
    else:
        try:
            candidate = distribution_version("jaw")
        except PackageNotFoundError:
            candidate = ""
    match = _VERSION_PREFIX.match(str(candidate or "").strip())
    return ".".join(match.groups()) if match else "0.0.0"


JAW_VERSION = current_jaw_version()


def version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(str(value or "").strip())
    if not match:
        raise ValueError(f"Invalid major.minor.patch version: {value}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _requirement_clauses(requirement: str) -> list[tuple[str, tuple[int, int, int]]]:
    raw_clauses = [part.strip() for part in str(requirement or "").split(",") if part.strip()]
    if not raw_clauses:
        raise ValueError("Template release is missing a JAW compatibility range")
    clauses: list[tuple[str, tuple[int, int, int]]] = []
    for clause in raw_clauses:
        match = _RANGE_CLAUSE.fullmatch(clause)
        if not match:
            raise ValueError(f"Invalid JAW compatibility clause: {clause}")
        operator, required = match.groups()
        clauses.append((operator or "", version_tuple(required)))
    return clauses


def version_satisfies(version: str, requirement: str) -> bool:
    """Evaluate the small comparator grammar used by releases.json."""

    current = version_tuple(version)
    operations = {
        ">=": lambda left, right: left >= right,
        "<=": lambda left, right: left <= right,
        ">": lambda left, right: left > right,
        "<": lambda left, right: left < right,
        "==": lambda left, right: left == right,
        "": lambda left, right: left == right,
    }
    return all(
        operations[operator](current, required)
        for operator, required in _requirement_clauses(requirement)
    )


def normalize_release_registry(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    if int(value.get("registry_format") or 0) != RELEASE_REGISTRY_FORMAT_VERSION:
        raise ValueError("Unsupported template release registry format")
    raw_releases = value.get("releases")
    if not isinstance(raw_releases, Sequence) or isinstance(raw_releases, (str, bytes)):
        raise ValueError("Template release registry requires a releases list")
    if not raw_releases:
        raise ValueError("Template release registry does not contain releases")

    releases: list[dict[str, Any]] = []
    seen_versions: set[str] = set()
    for raw in raw_releases:
        if not isinstance(raw, Mapping):
            raise ValueError("Template release registry entries must be objects")
        release_version = str(raw.get("version") or "").strip()
        version_tuple(release_version)
        if release_version in seen_versions:
            raise ValueError(f"Duplicate template release version: {release_version}")
        seen_versions.add(release_version)

        reference = str(raw.get("ref") or "").strip()
        if not reference:
            raise ValueError(f"Template release {release_version} is missing ref")
        template_api = int(raw.get("template_api") or 0)
        package_format = int(raw.get("package_format") or 0)
        if template_api <= 0:
            raise ValueError(f"Template release {release_version} has invalid template_api")
        if package_format <= 0:
            raise ValueError(f"Template release {release_version} has invalid package_format")
        jaw_requirement = str(raw.get("jaw") or "").strip()
        _requirement_clauses(jaw_requirement)

        releases.append(
            {
                "version": release_version,
                "ref": reference,
                "template_api": template_api,
                "package_format": package_format,
                "jaw": jaw_requirement,
            }
        )
    return releases


def select_compatible_release(
    registry: Mapping[str, Any],
    *,
    jaw_version: str = JAW_VERSION,
    requested_version: str | None = None,
    supported_template_apis: frozenset[int] = SUPPORTED_TEMPLATE_APIS,
    package_format: int = TEMPLATE_PACKAGE_FORMAT_VERSION,
) -> dict[str, Any]:
    releases = normalize_release_registry(registry)
    compatible = [
        release
        for release in releases
        if release["template_api"] in supported_template_apis
        and release["package_format"] == package_format
        and version_satisfies(jaw_version, release["jaw"])
    ]

    requested = str(requested_version or "").strip()
    if requested:
        version_tuple(requested)
        match = next((release for release in compatible if release["version"] == requested), None)
        if match is not None:
            return match
        listed = any(release["version"] == requested for release in releases)
        if listed:
            raise ValueError(
                f"Template release {requested} is not compatible with JAW {jaw_version}"
            )
        raise ValueError(f"Template release {requested} is not listed by the official repository")

    if not compatible:
        raise ValueError(
            f"No official template release is compatible with JAW {jaw_version}, "
            f"template API {sorted(supported_template_apis)}, package format {package_format}"
        )
    return max(compatible, key=lambda release: version_tuple(str(release["version"])))


__all__ = [
    "JAW_VERSION",
    "RELEASE_REGISTRY_FORMAT_VERSION",
    "SUPPORTED_TEMPLATE_APIS",
    "TEMPLATE_PACKAGE_FORMAT_VERSION",
    "current_jaw_version",
    "normalize_release_registry",
    "select_compatible_release",
    "version_satisfies",
    "version_tuple",
]
