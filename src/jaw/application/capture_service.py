from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from ..capture import JOB_EXTRACTOR_VERSION, CaptureClassification, extract_job_fields
from ..capture_context import (
    capture_metrics,
    classifier_version,
    classify_capture_context,
    normalize_capture_for_parser,
)


class CaptureRepository(Protocol):
    def get_or_create_capture_session(self, user_id: int) -> dict[str, Any]: ...

    def start_capture_session(self, user_id: int) -> int: ...

    def add_capture(
        self,
        user_id: int,
        content: str,
        *,
        content_type: str = "unclassified",
        classification_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def classify_capture_event(
        self,
        session_id: int,
        event_id: int,
        content_type: str,
        metadata: dict[str, Any],
    ) -> None: ...

    def update_capture_metadata(
        self,
        session_id: int,
        event_id: int,
        metadata: dict[str, Any],
    ) -> None: ...

    def add_question(
        self,
        job_id: int,
        question: str,
        suggested_answer: str = "",
    ) -> int: ...

    def submit_answer(self, question_id: int, answer: str) -> None: ...


class CaptureValidationError(ValueError):
    """Selected clipboard content cannot be accepted by Smart Capture."""


@dataclass(frozen=True)
class CaptureAcceptance:
    session: dict[str, Any]
    classification: CaptureClassification


_EXTRACTABLE_JOB_CONTEXTS = {
    "job_title",
    "company",
    "job_metadata",
    "job_description",
    "requirements",
    "responsibilities",
}


class CaptureService:
    """Coordinate Smart Capture classification, extraction, and persistence."""

    def __init__(
        self,
        repository: CaptureRepository,
        answer_matcher: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.answer_matcher = answer_matcher or (lambda _question: "")

    @staticmethod
    def normalize_selection(content: str) -> str:
        normalized = str(content).replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise CaptureValidationError("Capture failed · No selected text was copied")
        if "\x00" in normalized or len(normalized) > 200_000:
            raise CaptureValidationError(
                "Capture failed · Selection is not valid text or is too large"
            )
        return normalized

    def reset_session(self, user_id: int) -> int:
        return self.repository.start_capture_session(user_id)

    def accept_text(self, user_id: int, content: str) -> CaptureAcceptance:
        normalized = self.normalize_selection(content)
        current = self.repository.get_or_create_capture_session(user_id)
        previous_events = list(current.get("events", []))
        classification = classify_capture_context(
            normalized,
            str(current.get("phase", "job_capture")),
            previous_events,
        )
        metadata = self._build_capture_metadata(
            normalized,
            classification,
            sequence=len(previous_events) + 1,
        )

        session = self.repository.add_capture(
            user_id,
            normalized,
            content_type=classification.content_type,
            classification_status=(
                "pending" if classification.content_type == "unclassified" else "classified"
            ),
            metadata=metadata,
        )
        self._record_application_capture(session, classification.content_type)
        return CaptureAcceptance(session=session, classification=classification)

    def refresh_session(self, user_id: int) -> dict[str, Any]:
        session = self.repository.get_or_create_capture_session(user_id)
        previous: list[dict[str, Any]] = []
        changed = False
        for sequence, original_event in enumerate(session.get("events", []), start=1):
            event = dict(original_event)
            content = str(event.get("content", ""))
            if event.get("classification_status") == "pending":
                result = classify_capture_context(
                    content,
                    str(session.get("phase", "job_capture")),
                    previous,
                )
                if result.content_type != "unclassified":
                    metadata = self._build_capture_metadata(
                        content,
                        result,
                        sequence=sequence,
                    )
                    self.repository.classify_capture_event(
                        int(session["id"]),
                        int(event["id"]),
                        result.content_type,
                        metadata,
                    )
                    event.update(
                        content_type=result.content_type,
                        classification_status="classified",
                        metadata=metadata,
                    )
                    changed = True

            content_type = str(event.get("content_type", "unclassified"))
            if content_type in _EXTRACTABLE_JOB_CONTEXTS:
                metadata = self.capture_metadata(event)
                extraction = metadata.get("extraction", {})
                parser_content = normalize_capture_for_parser(content, content_type)
                normalized_content = str(metadata.get("normalized_content", content))
                stale_extraction = (
                    not isinstance(extraction, dict)
                    or extraction.get("extractor") != JOB_EXTRACTOR_VERSION
                    or extraction.get("capture_context") != content_type
                    or normalized_content != parser_content
                    or metadata.get("classifier") != classifier_version()
                )
                if stale_extraction:
                    result = CaptureClassification(
                        content_type,
                        float(metadata.get("confidence", 0.0)),
                        str(metadata.get("reason", "existing classification")),
                    )
                    refreshed_metadata = self._build_capture_metadata(
                        content,
                        result,
                        sequence=sequence,
                    )
                    self.repository.update_capture_metadata(
                        int(session["id"]),
                        int(event["id"]),
                        refreshed_metadata,
                    )
                    event["metadata"] = refreshed_metadata
                    changed = True
            previous.append(event)

        return self.repository.get_or_create_capture_session(user_id) if changed else session

    def _build_capture_metadata(
        self,
        content: str,
        classification: CaptureClassification,
        *,
        sequence: int,
    ) -> dict[str, Any]:
        content_type = classification.content_type
        parser_content = normalize_capture_for_parser(content, content_type)
        metadata: dict[str, Any] = {
            "classifier": classifier_version(),
            "confidence": classification.confidence,
            "reason": classification.reason,
            "metrics": capture_metrics(content, sequence),
        }
        if parser_content != content:
            metadata["normalized_content"] = parser_content
        if content_type in _EXTRACTABLE_JOB_CONTEXTS:
            extraction = extract_job_fields(parser_content)
            extraction["capture_context"] = content_type
            metadata["extraction"] = extraction
        return metadata

    def _record_application_capture(
        self,
        session: dict[str, Any],
        content_type: str,
    ) -> None:
        job_id = session.get("job_id")
        if session.get("phase") != "application" or job_id is None:
            return
        events = list(session.get("events", []))
        if not events:
            return

        current = events[-1]
        metadata = self.capture_metadata(current)
        if content_type == "application_question":
            question = str(current["content"])
            question_id = self.repository.add_question(
                int(job_id),
                question,
                self.answer_matcher(question),
            )
            metadata["question_id"] = question_id
            self.repository.update_capture_metadata(
                int(session["id"]),
                int(current["id"]),
                metadata,
            )
            return
        if content_type != "application_answer":
            return

        for event in reversed(events[:-1]):
            if event.get("content_type") != "application_question":
                continue
            question_id = self.capture_metadata(event).get("question_id")
            if question_id:
                self.repository.submit_answer(
                    int(question_id),
                    str(current["content"]),
                )
                metadata["question_id"] = int(question_id)
                self.repository.update_capture_metadata(
                    int(session["id"]),
                    int(current["id"]),
                    metadata,
                )
            break

    @staticmethod
    def capture_metadata(event: dict[str, Any]) -> dict[str, Any]:
        raw = event.get("metadata", "{}")
        if isinstance(raw, dict):
            return dict(raw)
        try:
            parsed = json.loads(str(raw))
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
