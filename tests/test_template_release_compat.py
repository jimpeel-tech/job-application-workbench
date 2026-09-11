from __future__ import annotations

import pytest

from jaw.application.template_release_compat import (
    select_compatible_release,
    version_satisfies,
)


def _registry(*releases: dict) -> dict:
    return {"registry_format": 1, "releases": list(releases)}


def _release(
    version: str,
    *,
    ref: str | None = None,
    template_api: int = 1,
    package_format: int = 1,
    jaw: str = ">=0.1.0,<0.2.0",
) -> dict:
    return {
        "version": version,
        "ref": ref or f"v{version}",
        "template_api": template_api,
        "package_format": package_format,
        "jaw": jaw,
    }


def test_version_range_supports_release_registry_comparators() -> None:
    assert version_satisfies("0.1.0", ">=0.1.0,<0.2.0") is True
    assert version_satisfies("0.1.9", ">=0.1.0,<0.2.0") is True
    assert version_satisfies("0.2.0", ">=0.1.0,<0.2.0") is False
    assert version_satisfies("1.4.2", "==1.4.2") is True


def test_selects_newest_release_compatible_with_running_jaw() -> None:
    registry = _registry(
        _release("0.1.0"),
        _release("0.1.2"),
        _release("0.2.0", template_api=2, jaw=">=0.2.0,<0.3.0"),
    )

    selected = select_compatible_release(
        registry,
        jaw_version="0.1.5",
        supported_template_apis=frozenset({1}),
        package_format=1,
    )

    assert selected["version"] == "0.1.2"
    assert selected["ref"] == "v0.1.2"
    assert selected["template_api"] == 1


def test_template_api_can_keep_old_and_new_contracts_compatible() -> None:
    registry = _registry(
        _release("0.1.5", template_api=1, jaw=">=0.1.0,<0.3.0"),
        _release("0.2.1", template_api=2, jaw=">=0.2.0,<0.3.0"),
    )

    selected = select_compatible_release(
        registry,
        jaw_version="0.2.4",
        supported_template_apis=frozenset({1, 2}),
        package_format=1,
    )

    assert selected["version"] == "0.2.1"
    assert selected["template_api"] == 2


def test_incompatible_explicit_release_is_rejected() -> None:
    registry = _registry(
        _release("0.1.0"),
        _release("0.2.0", template_api=2, jaw=">=0.2.0,<0.3.0"),
    )

    with pytest.raises(ValueError, match="not compatible with JAW 0.1.7"):
        select_compatible_release(
            registry,
            jaw_version="0.1.7",
            requested_version="0.2.0",
            supported_template_apis=frozenset({1}),
            package_format=1,
        )


def test_no_compatible_release_has_actionable_error() -> None:
    registry = _registry(
        _release("0.2.0", template_api=2, jaw=">=0.2.0,<0.3.0"),
    )

    with pytest.raises(ValueError, match="No official template release is compatible"):
        select_compatible_release(
            registry,
            jaw_version="0.1.9",
            supported_template_apis=frozenset({1}),
            package_format=1,
        )


def test_registry_rejects_invalid_jaw_range_even_after_false_first_clause() -> None:
    registry = _registry(
        _release("0.1.0", jaw=">=9.0.0,definitely-not-a-range"),
    )

    with pytest.raises(ValueError, match="Invalid JAW compatibility clause"):
        select_compatible_release(
            registry,
            jaw_version="0.1.0",
            supported_template_apis=frozenset({1}),
            package_format=1,
        )
