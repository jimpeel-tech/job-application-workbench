from jaw.web.assets import static_asset_for


def test_global_template_context_menu_can_make_private_for_active_document() -> None:
    javascript = static_asset_for("/document-workbench-resources.js").read().decode("utf-8")

    assert "function templatePrivateOwner(resource)" in javascript
    assert "usage.find(document => document.id === activeDocumentId)" in javascript
    assert "Open a Document using this Template" in javascript
    assert "Detach ${templateOwner.name || 'active Document'}" in javascript
    assert "if (resource.kind === 'template') ownerId = templatePrivateOwner(resource)?.id || '';" in javascript
    assert "template_detached" in javascript
