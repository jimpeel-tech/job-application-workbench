from pathlib import Path

from jaw.database import JobDatabase
from jaw.integrations.outlook.classifier import (
    company_names_match,
    defensible_job_match,
    likely_job_email,
    rank_candidate_jobs,
)
from jaw.integrations.outlook.graph import managed_categories
from jaw.integrations.outlook.service import OutlookSyncService, transition_for


def test_outlook_transition_policy_never_regresses_lifecycle():
    assert transition_for("application_received", "Applying") == "Applied"
    assert transition_for("application_received", "Interviewing") is None
    assert transition_for("recruiter_contact", "Applied") == "Recruiter Screen"
    assert transition_for("recruiter_contact", "Interviewing") is None
    assert transition_for("interview", "Recruiter Screen") == "Interviewing"
    assert transition_for("offer", "Interviewing") == "Offer"
    assert transition_for("rejection", "Offer") == "Rejected"
    assert transition_for("rejection", "Withdrawn") is None
    assert transition_for("rejection", "Archived") is None


def test_outlook_category_replacement_preserves_unmanaged_categories():
    assert managed_categories(["Personal", "1 Application"], "2 Rejected") == [
        "Personal",
        "2 Rejected",
    ]


def test_outlook_prefilter_and_candidate_ranking():
    message = {
        "subject": "Update on your application at Mux",
        "from": {"emailAddress": {"address": "recruiting@mux.com", "name": "Mux Recruiting"}},
        "bodyPreview": "Senior Platform Engineer",
        "body": {"content": "Thank you for your interest in the Senior Platform Engineer role."},
    }
    jobs = [
        {"id": 1, "company": "Mux", "title": "Senior Platform Engineer", "status": "Applied"},
        {"id": 2, "company": "Example", "title": "Senior Platform Engineer", "status": "Applied"},
    ]
    assert likely_job_email(message)
    assert rank_candidate_jobs(message, jobs)[0]["id"] == 1


def test_company_matching_ignores_common_legal_suffixes():
    assert company_names_match("Cisco Systems", "Cisco")
    assert company_names_match("Oracle Corporation", "Oracle")
    assert not company_names_match("Cisco Systems", "Medallia")


def test_defensible_match_blocks_role_similarity_across_companies():
    message = {
        "subject": "Next Step - Cisco Systems - Senior Site Reliability Engineer",
        "from": {"emailAddress": {"address": "recruiter@example.com", "name": "Recruiter"}},
        "bodyPreview": "Consent for submitting you to Cisco Systems",
        "body": {
            "content": "Consent for submitting you to Cisco Systems for Senior Site Reliability Engineer."
        },
    }
    medallia = {
        "id": 1,
        "company": "Medallia",
        "title": "Staff Site Reliability Engineer, GovCloud",
        "status": "Applied",
    }
    result = {
        "company": "Cisco Systems",
        "title": "Senior Site Reliability Engineer",
    }
    valid, reason = defensible_job_match(message, result, medallia, [medallia])
    assert not valid
    assert reason == "employer_mismatch"


class FakeAuth:
    def status(self):
        return {"configured": True, "connected": True, "account": "test@example.com"}


class FakeClassifier:
    def classify(self, _message, candidate_jobs):
        return {
            "classification": "rejection",
            "job_id": int(candidate_jobs[0]["id"]),
            "company": "Mux",
            "title": "Senior Platform Engineer",
            "classification_confidence": 0.99,
            "match_confidence": 0.99,
            "reason": "Explicit employer rejection.",
            "model": "fake",
        }


class FakeGraph:
    def __init__(self):
        self.categories = []
        self.summary = {
            "id": "immutable-message-1",
            "internetMessageId": "<message-1@example.com>",
            "subject": "Update on your application at Mux",
            "from": {"emailAddress": {"address": "recruiting@mux.com", "name": "Mux"}},
            "receivedDateTime": "2026-09-05T15:00:00Z",
            "bodyPreview": "Thank you for applying. We have decided not to move forward.",
            "categories": ["Personal", "1 Application"],
            "webLink": "https://outlook.office.com/mail/id/example",
        }

    def list_messages(self, _since, *, max_messages=2500):
        return [dict(self.summary)], False

    def get_message(self, _message_id):
        result = dict(self.summary)
        result["body"] = {
            "content": "Thank you for your interest in Mux. We have decided not to move forward with your application."
        }
        return result

    def set_category(self, _message_id, existing, category):
        self.categories = managed_categories(existing, category)
        return self.categories


def test_outlook_sync_updates_jaw_once_and_records_provenance(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    job_id = database.create_job("Mux Senior Platform Engineer", user_id=4)
    database.update_identity(job_id, "Mux", "Senior Platform Engineer", user_id=4)
    database.set_status(job_id, "Applied", user_id=4)

    graph = FakeGraph()
    service = OutlookSyncService(
        database,
        auth=FakeAuth(),
        classifier=FakeClassifier(),
        graph_factory=lambda _auth: graph,
    )

    result = service.sync(4, days=365)
    assert result["updated"] == 1
    assert result["categorized"] == 1
    assert database.get_job(job_id, user_id=4)["status"] == "Rejected"
    assert graph.categories == ["Personal", "2 Rejected"]

    with database.connect() as connection:
        event = connection.execute(
            "SELECT event_type,source,source_ref,details FROM application_events "
            "WHERE job_id=? AND source='outlook'",
            (job_id,),
        ).fetchone()
        assert event["event_type"] == "Rejected"
        assert event["source_ref"] == "immutable-message-1"
        assert "Outlook" in event["details"]

    second = service.sync(4, days=365)
    assert second["updated"] == 0
    assert second["skipped"] == 1
    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM application_events WHERE job_id=? AND source='outlook'",
            (job_id,),
        ).fetchone()[0]
    assert count == 1


def test_outlook_reset_restores_status_and_allows_reprocessing(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    job_id = database.create_job("Mux Senior Platform Engineer", user_id=4)
    database.update_identity(job_id, "Mux", "Senior Platform Engineer", user_id=4)
    database.set_status(job_id, "Applied", user_id=4)
    graph = FakeGraph()
    service = OutlookSyncService(
        database,
        auth=FakeAuth(),
        classifier=FakeClassifier(),
        graph_factory=lambda _auth: graph,
    )

    service.sync(4, days=365)
    reset = service.reset(4)
    assert reset["messages_reset"] == 1
    assert reset["events_removed"] == 1
    assert reset["statuses_restored"] == 1
    assert database.get_job(job_id, user_id=4)["status"] == "Applied"

    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM application_events WHERE job_id=? AND source='outlook'",
            (job_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM outlook_messages WHERE user_id=4"
        ).fetchone()[0] == 0

    again = service.sync(4, days=365)
    assert again["updated"] == 1
    assert database.get_job(job_id, user_id=4)["status"] == "Rejected"


class CrossCompanyClassifier:
    def classify(self, _message, candidate_jobs):
        return {
            "classification": "recruiter_contact",
            "job_id": int(candidate_jobs[0]["id"]),
            "company": "Cisco Systems",
            "title": "Senior Site Reliability Engineer",
            "classification_confidence": 0.99,
            "match_confidence": 0.99,
            "reason": "Recruiter contact about Cisco Systems.",
            "model": "fake",
        }


class CrossCompanyGraph(FakeGraph):
    def __init__(self):
        super().__init__()
        self.summary.update(
            {
                "id": "cisco-message-1",
                "internetMessageId": "<cisco-1@example.com>",
                "subject": "Next Step, Consent for submitting you to Cisco Systems",
                "bodyPreview": "Senior Site Reliability Engineer - 58122-1",
                "categories": [],
            }
        )

    def get_message(self, _message_id):
        result = dict(self.summary)
        result["body"] = {
            "content": "Consent for submitting you to Cisco Systems for Senior Site Reliability Engineer - 58122-1."
        }
        return result


def test_outlook_sync_sends_cross_company_model_match_to_review(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    job_id = database.create_job("Medallia Staff SRE", user_id=4)
    database.update_identity(job_id, "Medallia", "Staff Site Reliability Engineer, GovCloud", user_id=4)
    database.set_status(job_id, "Applied", user_id=4)
    graph = CrossCompanyGraph()
    service = OutlookSyncService(
        database,
        auth=FakeAuth(),
        classifier=CrossCompanyClassifier(),
        graph_factory=lambda _auth: graph,
    )

    result = service.sync(4, days=365)
    assert result["updated"] == 0
    assert result["review"] == 1
    assert database.get_job(job_id, user_id=4)["status"] == "Applied"
    assert graph.categories == ["9 Review"]
    with database.connect() as connection:
        row = connection.execute(
            "SELECT job_id,decision,match_confidence,metadata FROM outlook_messages WHERE user_id=4"
        ).fetchone()
        assert row["job_id"] is None
        assert row["decision"] == "review"
        assert row["match_confidence"] == 0.0
        assert '"match_validation": "employer_mismatch"' in row["metadata"]
