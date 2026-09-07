"""Outlook-to-JAW synchronization orchestration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ...database import JobDatabase
from .auth import OutlookAuth
from .classifier import (
    OutlookEmailClassifier,
    defensible_job_match,
    likely_job_email,
    rank_candidate_jobs,
)
from .graph import OutlookGraphClient

CLASSIFICATION_CONFIDENCE = 0.90
MATCH_CONFIDENCE = 0.90

CATEGORY_BY_CLASSIFICATION = {
    "application_received": "1 Application",
    "rejection": "2 Rejected",
    "recruiter_contact": "3 Recruiter",
    "interview": "4 Interview",
    "offer": "5 Offer",
}
EVENT_BY_CLASSIFICATION = {
    "application_received": "Application received",
    "rejection": "Rejected",
    "recruiter_contact": "Recruiter contact",
    "interview": "Interview",
    "offer": "Offer",
}


def transition_for(classification: str, current_status: str) -> str | None:
    """Return a safe forward lifecycle transition, never a regression."""
    if current_status in {"Rejected", "Withdrawn", "Archived"}:
        return None
    if classification == "application_received":
        return "Applied" if current_status in {
            "Captured",
            "Reviewing",
            "Interested",
            "Applying",
        } else None
    if classification == "recruiter_contact":
        return "Recruiter Screen" if current_status == "Applied" else None
    if classification == "interview":
        return "Interviewing" if current_status in {"Applied", "Recruiter Screen"} else None
    if classification == "offer":
        return "Offer" if current_status in {"Applied", "Recruiter Screen", "Interviewing"} else None
    if classification == "rejection":
        return "Rejected"
    return None


def _sender_address(message: dict[str, Any]) -> str:
    sender = message.get("from", {})
    email = sender.get("emailAddress", {}) if isinstance(sender, dict) else {}
    return str(email.get("address", "")) if isinstance(email, dict) else ""


class OutlookSyncService:
    def __init__(
        self,
        database: JobDatabase,
        *,
        auth: OutlookAuth | None = None,
        classifier: OutlookEmailClassifier | None = None,
        graph_factory: Callable[[OutlookAuth], OutlookGraphClient] | None = None,
    ) -> None:
        self.database = database
        self.auth = auth or OutlookAuth()
        self.classifier = classifier or OutlookEmailClassifier()
        self.graph_factory = graph_factory or OutlookGraphClient

    def status(self, user_id: int) -> dict[str, Any]:
        state = self.database.outlook_repository.sync_state(user_id)
        review = self.database.outlook_repository.recent_review(user_id, limit=8)
        return {
            "auth": self.auth.status(),
            "sync": state,
            "review": review,
            "categories": [
                "1 Application",
                "2 Rejected",
                "3 Recruiter",
                "4 Interview",
                "5 Offer",
                "9 Review",
            ],
        }

    def start_auth(self) -> dict[str, Any]:
        return self.auth.start_device_flow()

    def complete_auth(self) -> dict[str, Any]:
        return self.auth.complete_device_flow()

    def disconnect(self) -> None:
        self.auth.disconnect()

    def reset(self, user_id: int) -> dict[str, Any]:
        """Undo JAW-side Outlook test changes so messages can be safely reprocessed."""
        result = self.database.outlook_repository.reset(user_id)
        return {"ok": True, **result}

    def sync(
        self,
        user_id: int,
        *,
        days: int = 30,
        max_messages: int = 2500,
    ) -> dict[str, Any]:
        days = max(1, min(int(days), 730))
        max_messages = max(1, min(int(max_messages), 5000))
        graph = self.graph_factory(self.auth)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        messages, truncated = graph.list_messages(since, max_messages=max_messages)
        jobs = self.database.list_jobs(sort="updated_at", order="desc", user_id=user_id)
        jobs_by_id = {int(job["id"]): job for job in jobs}

        scanned = updated = categorized = review = ignored = skipped = errors = 0
        message_errors: list[str] = []

        # Graph returns newest first. Lifecycle transitions must be evaluated oldest first
        # so an old acknowledgement can never be applied after a newer interview/rejection.
        for summary in reversed(messages):
            message_id = str(summary.get("id", ""))
            if not message_id:
                continue
            if self.database.outlook_repository.is_processed(user_id, message_id):
                skipped += 1
                continue
            scanned += 1
            sender = _sender_address(summary)
            subject = str(summary.get("subject", ""))
            received_at = str(summary.get("receivedDateTime", ""))
            internet_message_id = str(summary.get("internetMessageId", ""))

            if not likely_job_email(summary):
                self.database.outlook_repository.record_decision(
                    user_id=user_id,
                    message_id=message_id,
                    internet_message_id=internet_message_id,
                    received_at=received_at,
                    sender=sender,
                    subject=subject,
                    classification="other",
                    decision="ignored",
                    metadata={"prefilter": "not_job"},
                )
                ignored += 1
                continue

            try:
                message = graph.get_message(message_id)
                candidates = rank_candidate_jobs(message, jobs)
                result = self.classifier.classify(message, candidates)
                classification = str(result["classification"])
                class_conf = float(result["classification_confidence"])
                match_conf = float(result["match_confidence"])
                job_id = int(result.get("job_id", 0) or 0)
                job = jobs_by_id.get(job_id)

                if job is not None:
                    valid_match, validation = defensible_job_match(
                        message,
                        result,
                        job,
                        jobs,
                    )
                else:
                    valid_match, validation = False, "no_matching_jaw_job"
                result["match_validation"] = validation
                if not valid_match:
                    if job_id:
                        result["model_job_id"] = job_id
                    result["job_id"] = 0
                    result["match_confidence"] = 0.0
                    job_id = 0
                    job = None
                    match_conf = 0.0

                if classification == "other":
                    self.database.outlook_repository.record_decision(
                        user_id=user_id,
                        message_id=message_id,
                        internet_message_id=internet_message_id,
                        received_at=received_at,
                        sender=sender,
                        subject=subject,
                        classification=classification,
                        job_id=job_id if job else None,
                        classification_confidence=class_conf,
                        match_confidence=match_conf,
                        decision="ignored",
                        metadata=result,
                    )
                    ignored += 1
                    continue

                actionable = (
                    classification in CATEGORY_BY_CLASSIFICATION
                    and class_conf >= CLASSIFICATION_CONFIDENCE
                    and job is not None
                    and match_conf >= MATCH_CONFIDENCE
                )
                if actionable:
                    category = CATEGORY_BY_CLASSIFICATION[classification]
                    new_status = transition_for(classification, str(job.get("status", "")))
                    graph.set_category(message_id, message.get("categories", []), category)
                    details = f"Outlook · {subject or '(no subject)'}"
                    metadata = dict(result)
                    metadata.update(
                        {
                            "web_link": str(message.get("webLink", "")),
                            "previous_status": str(job.get("status", "")),
                            "new_status": new_status or "",
                        }
                    )
                    recorded = self.database.outlook_repository.record_decision(
                        user_id=user_id,
                        message_id=message_id,
                        internet_message_id=internet_message_id,
                        received_at=received_at,
                        sender=sender,
                        subject=subject,
                        classification=classification,
                        category=category,
                        job_id=job_id,
                        classification_confidence=class_conf,
                        match_confidence=match_conf,
                        decision="updated" if new_status else "categorized",
                        event_type=EVENT_BY_CLASSIFICATION[classification],
                        event_details=details,
                        new_status=new_status,
                        metadata=metadata,
                    )
                    if recorded:
                        categorized += 1
                        if new_status:
                            updated += 1
                            job["status"] = new_status
                    continue

                graph.set_category(message_id, message.get("categories", []), "9 Review")
                review_job_id = job_id if job is not None and match_conf >= MATCH_CONFIDENCE else None
                review_metadata = dict(result)
                review_metadata["web_link"] = str(message.get("webLink", ""))
                self.database.outlook_repository.record_decision(
                    user_id=user_id,
                    message_id=message_id,
                    internet_message_id=internet_message_id,
                    received_at=received_at,
                    sender=sender,
                    subject=subject,
                    classification=classification,
                    category="9 Review",
                    job_id=review_job_id,
                    classification_confidence=class_conf,
                    match_confidence=match_conf,
                    decision="review",
                    metadata=review_metadata,
                )
                review += 1
            except RuntimeError as error:
                errors += 1
                message_errors.append(f"{subject or message_id}: {error}")
                if len(message_errors) >= 8:
                    break

        self.database.outlook_repository.set_sync_state(
            user_id,
            scanned=scanned,
            updated=updated,
            categorized=categorized,
            review=review,
            ignored=ignored,
            skipped=skipped,
            errors=errors,
            truncated=truncated,
            error="; ".join(message_errors[:3]),
        )
        return {
            "ok": errors == 0,
            "days": days,
            "scanned": scanned,
            "updated": updated,
            "categorized": categorized,
            "review": review,
            "ignored": ignored,
            "skipped": skipped,
            "errors": errors,
            "truncated": truncated,
            "message_errors": message_errors,
        }


__all__ = [
    "CATEGORY_BY_CLASSIFICATION",
    "CLASSIFICATION_CONFIDENCE",
    "EVENT_BY_CLASSIFICATION",
    "MATCH_CONFIDENCE",
    "OutlookSyncService",
    "transition_for",
]
