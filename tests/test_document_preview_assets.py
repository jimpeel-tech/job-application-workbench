from jaw.web.assets import static_asset_for


def test_preview_renders_live_document_without_requiring_prior_generate():
    javascript = static_asset_for("/document-workbench-preview.js").read().decode("utf-8")

    assert "previewButton.disabled = rendering || !documentId;" in javascript
    assert "!previews.has(documentId)" not in javascript
    assert "window.open('about:blank', PREVIEW_WINDOW)" in javascript
    assert "preview: true" in javascript
    assert "working_buffers: currentWorkingBuffers()" in javascript
    assert "previewButton.addEventListener('click', preview);" in javascript
    assert "previewWindow.location.replace(url);" in javascript
