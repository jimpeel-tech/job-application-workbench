from __future__ import annotations

import re
from typing import Any

from .capture import CaptureClassification, classify_capture

_CLASSIFIER_VERSION = "context-rules-v3"

_REQUIREMENT_HEADINGS = (
    "requirements",
    "qualifications",
    "required qualifications",
    "minimum qualifications",
    "basic qualifications",
    "what we're looking for",
    "what we’re looking for",
    "what you need",
    "what you'll bring",
    "what you’ll bring",
)
_RESPONSIBILITY_HEADINGS = (
    "responsibilities",
    "key responsibilities",
    "duties",
    "essential duties",
    "what you'll do",
    "what you’ll do",
    "what you'll be doing",
    "what you’ll be doing",
    "a day in the life",
)
_METADATA_EMPLOYMENT = re.compile(
    r"\b(?:full[- ]?time|part[- ]?time|contract(?:or)?|temporary|permanent|internship)\b",
    re.IGNORECASE,
)
_METADATA_ARRANGEMENT = re.compile(
    r"\b(?:remote|hybrid|on[- ]?site|onsite|telework|field[- ]based)\b",
    re.IGNORECASE,
)
_METADATA_PAY = re.compile(
    r"(?:\$\s*\d[\d,]*(?:\.\d+)?|\b\d{2,3}\s*[kK]\b|\b(?:salary|pay|compensation)\b)",
    re.IGNORECASE,
)
_METADATA_LOCATION = re.compile(r"\b(?:location|work location)\s*:|\b[A-Z][a-z]+,\s*[A-Z]{2}\b")
_METADATA_ID = re.compile(
    r"\b(?:job|req(?:uisition)?)\s*(?:id|#|number)\b|\bJR\d{4,}\b",
    re.IGNORECASE,
)
_METADATA_TOKEN = re.compile(
    r"(?:full[- ]?time|part[- ]?time|contract(?:or)?|temporary|permanent|"
    r"remote|hybrid|on[- ]?site|onsite|telework|field[- ]based)",
    re.IGNORECASE,
)
_APPLICATION_FORM_PROMPT = re.compile(
    r"(?:^|\b)(?:years? of experience|salary expectations?|desired (?:salary|compensation)|"
    r"work authorization(?: status)?|visa sponsorship|sponsorship required|"
    r"willing(?:ness)? to relocate|relocation willingness|notice period|available start date|"
    r"earliest start date|reason for leaving|reason for interest|professional experience with)\b",
    re.IGNORECASE,
)
_BULLET_LINE = re.compile(r"^\s*(?:[-*•▪●◦‣]|\d+[.)])\s+")
_KEY_VALUE_LINE = re.compile(
    r"^\s*[A-Za-z][A-Za-z /_-]{1,40}\s*(?::|\t|\s{2,})\s*\S"
)
_INLINE_SEPARATOR = re.compile(r"[•▪●◦‣·|]")


def classifier_version() -> str:
    return _CLASSIFIER_VERSION


def capture_metrics(content: str, sequence: int | None = None) -> dict[str, Any]:
    """Describe the raw selection before field extraction.

    These metrics are intentionally cheap and deterministic. They preserve signals
    about how browser-selected text arrived (short identity text, prose, bullets,
    key/value rows, collapsed metadata badges, and capture order) so later parsing
    and fixture review can reason about human capture behavior without changing the
    original text.
    """
    text = str(content)
    nonempty_lines = [line for line in text.splitlines() if line.strip()]
    paragraphs = [
        part for part in re.split(r"\n\s*\n", text.strip()) if part.strip()
    ]
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#./_-]*", text)
    metadata_hits = _metadata_signal_count(text)
    bullet_lines = sum(bool(_BULLET_LINE.match(line)) for line in nonempty_lines)
    key_value_lines = sum(bool(_KEY_VALUE_LINE.match(line)) for line in nonempty_lines)
    inline_separators = len(_INLINE_SEPARATOR.findall(text))
    pipe_count = text.count("|")
    tab_count = text.count("\t")
    collapsed_metadata = _has_collapsed_metadata_boundaries(text)
    size_class = _size_class(len(text), len(words))
    shape = _capture_shape(
        characters=len(text),
        lines=len(nonempty_lines),
        paragraphs=len(paragraphs),
        words=len(words),
        metadata_signals=metadata_hits,
        bullet_lines=bullet_lines,
        key_value_lines=key_value_lines,
        pipe_count=pipe_count,
        tab_count=tab_count,
    )

    metrics: dict[str, Any] = {
        "characters": len(text),
        "words": len(words),
        "lines": len(nonempty_lines),
        "paragraphs": len(paragraphs),
        "bullet_lines": bullet_lines,
        "inline_separators": inline_separators,
        "pipe_count": pipe_count,
        "tab_count": tab_count,
        "key_value_lines": key_value_lines,
        "metadata_signals": metadata_hits,
        "single_line": len(nonempty_lines) <= 1,
        "delimiter_heavy": inline_separators + tab_count >= 2,
        "collapsed_metadata_suspected": collapsed_metadata,
        "size_class": size_class,
        "shape": shape,
    }
    if sequence is not None:
        metrics["sequence"] = int(sequence)
        metrics["first_capture"] = int(sequence) == 1
    return metrics


def normalize_capture_for_parser(content: str, content_type: str) -> str:
    """Return parser-oriented text without altering the persisted raw capture."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n").strip()
    if content_type != "job_metadata" or "\n" in text:
        return text

    # Browser selection can collapse adjacent DOM badges into one string, e.g.
    # ``Full-TimeRemote$200,000 - $250,000 /yr``. Split only on vocabulary we
    # already understand; do not apply generic CamelCase splitting.
    parts: list[str] = []
    cursor = 0
    matches = list(_METADATA_TOKEN.finditer(text))
    if not matches:
        return text

    for match in matches:
        if match.start() > cursor:
            prefix = text[cursor : match.start()]
            if prefix.strip():
                parts.append(prefix.strip())
        parts.append(match.group(0).strip())
        cursor = match.end()

    tail = text[cursor:]
    if tail.strip():
        parts.append(tail.strip())

    expanded: list[str] = []
    for part in parts:
        if "$" in part and not part.lstrip().startswith("$"):
            before, marker, after = part.partition("$")
            if before.strip():
                expanded.append(before.strip())
            expanded.append(f"{marker}{after}".strip())
        else:
            expanded.append(part)

    return "\n".join(value for value in expanded if value)


def classify_capture_context(
    content: str,
    phase: str,
    previous_events: list[dict[str, Any]] | None = None,
) -> CaptureClassification:
    """Classify capture context using structure, vocabulary, size, and order signals."""
    text = " ".join(str(content).split())
    lowered = text.casefold()
    previous_events = previous_events or []

    if phase == "application":
        legacy = classify_capture(content, phase, previous_events)
        if legacy.content_type == "application_question":
            return legacy
        if len(text) <= 600 and _APPLICATION_FORM_PROMPT.search(text):
            return CaptureClassification(
                "application_question",
                0.88,
                "application form prompt vocabulary",
            )
        return legacy

    requirement_hit = _starts_with_heading(lowered, _REQUIREMENT_HEADINGS)
    responsibility_hit = _starts_with_heading(lowered, _RESPONSIBILITY_HEADINGS)
    if requirement_hit and not responsibility_hit and len(text) >= 45:
        return CaptureClassification(
            "requirements",
            0.91,
            "requirements heading and supporting content",
        )
    if responsibility_hit and not requirement_hit and len(text) >= 45:
        return CaptureClassification(
            "responsibilities",
            0.91,
            "responsibilities heading and supporting content",
        )

    metadata_signals = _metadata_signal_count(text)
    if metadata_signals >= 2 and len(text) <= 320:
        confidence = min(0.96, 0.78 + (metadata_signals * 0.05))
        return CaptureClassification(
            "job_metadata",
            confidence,
            f"{metadata_signals} explicit job-metadata signals",
        )

    # Keep the proven legacy title/company/description rules as the conservative
    # fallback while the richer context layer learns from fixtures.
    return classify_capture(content, phase, previous_events)


def _starts_with_heading(lowered: str, headings: tuple[str, ...]) -> bool:
    return any(
        lowered == heading or lowered.startswith(f"{heading} ") or lowered.startswith(f"{heading}:")
        for heading in headings
    )


def _metadata_signal_count(text: str) -> int:
    # Word boundaries work for ordinary prose, but browser selection can collapse
    # adjacent DOM badges (``Full-TimeRemote``). Reuse the boundary-free tokenizer
    # so those known tokens still contribute independent metadata signals.
    tokens = [match.group(0) for match in _METADATA_TOKEN.finditer(text)]
    employment_hit = bool(_METADATA_EMPLOYMENT.search(text)) or any(
        _METADATA_EMPLOYMENT.fullmatch(token) for token in tokens
    )
    arrangement_hit = bool(_METADATA_ARRANGEMENT.search(text)) or any(
        _METADATA_ARRANGEMENT.fullmatch(token) for token in tokens
    )
    signals = (
        employment_hit,
        arrangement_hit,
        bool(_METADATA_PAY.search(text)),
        bool(_METADATA_LOCATION.search(text)),
        bool(_METADATA_ID.search(text)),
    )
    return sum(signals)


def _has_collapsed_metadata_boundaries(text: str) -> bool:
    """Detect adjacent known metadata tokens without assuming generic CamelCase."""
    if "\n" in text:
        return False
    matches = list(_METADATA_TOKEN.finditer(text))
    if len(matches) < 2:
        return False
    for previous, current in zip(matches, matches[1:]):
        between = text[previous.end() : current.start()]
        if between == "":
            return True
    return False


def _size_class(characters: int, words: int) -> str:
    if characters <= 120 and words <= 20:
        return "short"
    if characters <= 900 and words <= 150:
        return "medium"
    return "long"


def _capture_shape(
    *,
    characters: int,
    lines: int,
    paragraphs: int,
    words: int,
    metadata_signals: int,
    bullet_lines: int,
    key_value_lines: int,
    pipe_count: int,
    tab_count: int,
) -> str:
    """Assign a broad structural prior; this is evidence, not final classification."""
    if key_value_lines >= 2 or tab_count >= 2 or (pipe_count >= 2 and lines <= 8):
        return "table_like"
    if metadata_signals >= 2 and characters <= 400:
        return "metadata_like"
    if (
        characters <= 120
        and lines <= 3
        and words <= 18
        and metadata_signals <= 1
    ):
        return "identity_like"
    if characters >= 220 or lines >= 4 or paragraphs >= 2 or bullet_lines >= 2:
        return "description_like"
    return "unknown"
