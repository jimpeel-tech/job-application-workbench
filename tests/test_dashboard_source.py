from pathlib import Path

import jaw


def _dashboard_source() -> str:
    return (Path(jaw.__file__).resolve().parent / "dashboard.html").read_text(
        encoding="utf-8"
    )


def test_dashboard_source_uses_native_documents_mount():
    dashboard = _dashboard_source()

    assert '<div id="documentsPage" class="page"></div>' in dashboard
    assert "Document Studio" not in dashboard
    assert "trackerDocumentDialog" not in dashboard


def test_dashboard_user_management_menu_is_explicit():
    dashboard = _dashboard_source()

    assert 'id="dataMenuButton">Manage User</button>' in dashboard
    assert 'id="newUserButton">+</button>' not in dashboard
    assert (
        '<div class="mini-menu" id="dataMenu">'
        '<button class="btn" id="newUserButton">Add user</button>'
        '<button class="btn" id="exportData">Export current user</button>'
        '<button class="btn" id="importData">Import user from file</button>'
        '<button class="btn" id="downloadTemplate">Download import template</button>'
        "</div>"
    ) in dashboard
