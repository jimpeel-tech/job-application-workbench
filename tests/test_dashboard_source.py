from pathlib import Path

import jaw


def _dashboard_source() -> str:
    return (Path(jaw.__file__).resolve().parent / "dashboard.html").read_text(
        encoding="utf-8"
    )


def _dashboard_css_source() -> str:
    return (Path(jaw.__file__).resolve().parent / "dashboard.css").read_text(
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


def test_capability_add_control_stays_on_one_line():
    css = _dashboard_css_source()

    assert ".cap-add-wrap{position:relative;flex:0 0 auto}" in css
    assert (
        ".cap-add-wrap>#capAddEntity{display:inline-flex;align-items:center;"
        "justify-content:center;gap:3px;white-space:nowrap;padding:6px 9px;"
        "font-size:12px}"
    ) in css
