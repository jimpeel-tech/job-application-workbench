from __future__ import annotations

from inspect import getsource
from pathlib import Path
from types import SimpleNamespace

import jaw
from jaw.config import BUILTIN_ACTION_LABELS
from jaw.main import MainWindow


class BrowserStub:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def open(self, url: str) -> bool:
        self.urls.append(url)
        return True


class StatusStub:
    def __init__(self) -> None:
        self.messages: list[tuple[object, ...]] = []

    def showMessage(self, *args) -> None:
        self.messages.append(args)


class LookupHarness:
    def __init__(self) -> None:
        self.browser = BrowserStub()
        self.dashboard = SimpleNamespace(url="http://127.0.0.1:8765")
        self.status = StatusStub()

    def statusBar(self) -> StatusStub:
        return self.status


def test_find_company_action_is_registered_and_dispatched() -> None:
    assert BUILTIN_ACTION_LABELS["find_company"] == "Find Company"
    source = getsource(MainWindow._dispatch_action)
    assert 'action == "find_company"' in source
    assert "self.find_company_in_tracker(key)" in source


def test_company_lookup_opens_tracker_with_normalized_search() -> None:
    harness = LookupHarness()

    MainWindow._open_company_in_tracker(harness, "  Cisco   Meraki  ")

    assert harness.browser.urls == [
        "http://127.0.0.1:8765/?q=Cisco+Meraki#tracker"
    ]
    assert harness.status.messages[-1] == ("Tracker search · Cisco Meraki", 2400)


def test_company_lookup_requires_a_company_sized_selection() -> None:
    harness = LookupHarness()

    MainWindow._open_company_in_tracker(harness, "   ")
    MainWindow._open_company_in_tracker(harness, "x" * 121)

    assert harness.browser.urls == []
    assert "highlight a company name first" in harness.status.messages[0][0]
    assert "select only the company name" in harness.status.messages[1][0]


def test_tracker_launch_query_seeds_existing_search_box() -> None:
    dashboard = (Path(jaw.__file__).resolve().parent / "dashboard.js").read_text(
        encoding="utf-8"
    )

    assert "const launchSearch = new URLSearchParams(location.search).get('q')" in dashboard
    assert "if (launchSearch) $('search').value = launchSearch" in dashboard
    assert "loadJobs()" in dashboard
