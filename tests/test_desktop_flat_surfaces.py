from __future__ import annotations

import re

from jaw.desktop.styles import STYLESHEET


def _rule(selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", STYLESHEET)
    assert match is not None, f"Missing stylesheet rule for {selector}"
    return match.group(1)


def test_internal_content_surfaces_are_borderless_by_default():
    for selector in (
        "QFrame#panel",
        "QListWidget",
        "QListWidget#captureFieldsList",
        "QListWidget#answerTitlesList",
    ):
        rule = _rule(selector)
        assert "border: none" in rule
        assert "border: 1px" not in rule


def test_flat_default_keeps_interactive_editors_visually_bounded():
    rule = _rule("QTextEdit#answerText")
    assert "border: 1px" in rule
