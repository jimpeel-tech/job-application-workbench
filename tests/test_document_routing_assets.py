from jaw.web.assets import static_asset_for


def test_document_routing_ui_is_resizable_and_user_defined() -> None:
    javascript = static_asset_for("/document-generation-commands.js").read().decode("utf-8")
    stylesheet = static_asset_for("/document-generation-commands.css").read().decode("utf-8")

    assert "DEFAULT_RULES" not in javascript
    assert "data-add-rule" in javascript
    assert "data-delete-rule" in javascript
    assert "data-move-rule" in javascript
    assert "default_document_ids" in javascript
    assert "document_ids" in javascript
    assert "data-route-document" in javascript
    assert "generated_documents" in javascript
    assert "Outputs can include both a resume and cover letter" in javascript
    assert "resize:both" in stylesheet
    assert ".jaw-doc-routing-rule" in stylesheet
    assert ".jaw-doc-output-picker" in stylesheet
    assert 'popover="auto"' in javascript
    assert "popovertarget" in javascript
    assert "positionOutputMenu" in javascript
    assert ":popover-open" in javascript
    assert "showGenerationError" in javascript
    assert "commandNotice" in javascript
    assert ".jaw-doc-output-menu[popover]" in stylesheet
    assert "position:fixed" in stylesheet
    assert ".jaw-doc-command-notice" in stylesheet
