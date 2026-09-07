from __future__ import annotations

import re
from typing import Any

from .capture import CaptureClassification, classify_capture

_CLASSIFIER_VERSION = "context-rules-v2"

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


def classifier_version() -> str:
    return _CLASSIFIER_VERSION


def capture_metrics(content: str, sequence: int | None = None) -> dict[str, Any]:
    text = str(content)
    nonempty_lines = [line for line in text.splitlines() if line.strip()]
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#./_-]*", text)
    metadata_hits = _metadata_signal_count(text)
    metrics: dict[str, Any] = {
        "characters": len(text),
        "words": len(words),
        "lines": len(nonempty_lines),
        "metadata_signals": metadata_hits,
        "single_line": len(nonempty_lines) <= 1,
    }
    if sequence is not None:
        metrics["sequence"] = int(sequence)
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
