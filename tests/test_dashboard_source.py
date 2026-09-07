from pathlib import Path

import jaw


def test_dashboard_source_uses_native_documents_mount():
    dashboard = (Path(jaw.__file__).resolve().parent / "dashboard.html").read_text(
        encoding="utf-8"
    )

    assert '<div id="documentsPage" class="page"></div>' in dashboard
    assert "Document Studio" not in dashboard
    assert "trackerDocumentDialog" not in dashboard
