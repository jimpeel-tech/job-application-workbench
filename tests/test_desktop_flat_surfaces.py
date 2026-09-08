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


def test_qa_answer_preview_uses_flat_surface():
    # The Q&A redesign intentionally removed the boxed answer editor surface.
    rule = _rule("QTextEdit#answerText")
    assert "background: transparent" in rule
    assert "border: none" in rule
    assert "border: 1px" not in rule
