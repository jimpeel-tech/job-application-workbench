from types import SimpleNamespace

from jaw.main import MainWindow


class CaptureServiceStub:
    def __init__(self, session):
        self.session = session
        self.user_ids = []

    def refresh_session(self, user_id):
        self.user_ids.append(user_id)
        return self.session


def test_tracker_action_opens_dashboard_while_focused_with_hotkeys_off() -> None:
    opened = []
    window = SimpleNamespace(
        hotkeys_enabled=False,
        config=SimpleNamespace(custom_sequences={}),
        isActiveWindow=lambda: True,
        open_dashboard=lambda: opened.append(True),
    )

    MainWindow._dispatch_action(window, "open_dashboard", "G", paste=False)

    assert opened == [True]


def test_analysis_action_analyzes_all_captured_selections() -> None:
    service = CaptureServiceStub(
        {
            "phase": "job_capture",
            "events": [
                {"content": "Company: Example Corp"},
                {"content": "Platform Engineer\nBuild reliable systems."},
            ],
        }
    )
    analyzed = []
    window = SimpleNamespace(
        capture_service=service,
        _active_user_id=lambda: 12,
        _analyze_captured_job=lambda description: analyzed.append(description),
    )

    MainWindow._analyze_capture_journal(window)

    assert service.user_ids == [12]
    assert analyzed == [
        "Company: Example Corp\n\nPlatform Engineer\nBuild reliable systems."
    ]
