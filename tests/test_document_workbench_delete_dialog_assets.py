from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workbench_delete_uses_native_dialog_not_browser_confirm() -> None:
    javascript = (ROOT / "src/jaw/document_workbench_resources.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "src/jaw/document_workbench_resources.css").read_text(encoding="utf-8")

    assert "window.confirm" not in javascript
    assert "requestDelete(resource, message, displayTitle = '')" in javascript
    assert "await requestDelete(resource, message, title)" in javascript
    assert "data-wb-delete-cancel" in javascript
    assert "data-wb-delete-accept" in javascript
    assert ".wb-delete-overlay" in stylesheet
    assert ".wb-delete-actions .danger" in stylesheet
