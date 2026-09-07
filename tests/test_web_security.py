import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from jaw.database import JobDatabase
from jaw.userdata import UserDataStore
from jaw.webapp import DashboardServer


@pytest.fixture
def dashboard(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"
    server = DashboardServer(
        JobDatabase(database_path),
        port=0,
        user_data_path=database_path,
    )
    UserDataStore(database_path)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def test_dashboard_rejects_non_loopback_bind(tmp_path):
    database_path = tmp_path / "data" / "jaw.db"

    with pytest.raises(ValueError, match="loopback"):
        DashboardServer(JobDatabase(database_path), host="0.0.0.0", port=0)


def test_dashboard_rejects_non_loopback_host_header(dashboard):
    request = Request(
        f"{dashboard.url}/api/user-data",
        headers={"Host": f"evil.example:{dashboard.port}"},
    )

    with pytest.raises(HTTPError) as exc_info:
        urlopen(request, timeout=3)

    assert exc_info.value.code == 403


def test_dashboard_rejects_cross_site_mutation_origin(dashboard):
    request = Request(
        f"{dashboard.url}/api/user/save",
        data=json.dumps({}).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": "https://evil.example",
        },
    )

    with pytest.raises(HTTPError) as exc_info:
        urlopen(request, timeout=3)

    assert exc_info.value.code == 403


def test_dashboard_accepts_same_origin_mutation(dashboard):
    request = Request(
        f"{dashboard.url}/api/user/save",
        data=json.dumps({}).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": dashboard.url,
        },
    )

    with urlopen(request, timeout=3) as response:
        assert response.status == 200
        assert json.load(response) == {"ok": True}


def test_dashboard_accepts_direct_client_without_origin(dashboard):
    request = Request(
        f"{dashboard.url}/api/user/save",
        data=json.dumps({}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    with urlopen(request, timeout=3) as response:
        assert response.status == 200
        assert json.load(response) == {"ok": True}
