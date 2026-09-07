from jaw.web.assets import static_asset_for


def test_workbench_drag_drop_uses_tracked_editor_position():
    javascript = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    assert "function caretRangeAtPoint(" in javascript
    assert "function mirrorCaretRect(" in javascript
    assert "function mirrorDropPoint(" in javascript
    assert "document.body.appendChild(mirror)" in javascript
    assert "editor.dataset.wbDropPosition = String(point.position)" in javascript
    assert "delete editor.dataset.wbDropPosition" in javascript
    assert "editor.setSelectionRange(position, position)" in javascript
    assert "mirror.remove()" in javascript
    assert "}, true);" in javascript


def test_workbench_drag_drop_reasserts_internal_transport_and_accepts_editor_drop():
    javascript = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    assert "{ source: 'jaw', expression: item.dataset.wbJaw }" in javascript
    assert "{ source: 'resource', resource_id: item.dataset.wbDragResource }" in javascript
    assert "event.dataTransfer.effectAllowed = 'copyMove'" in javascript
    assert "event.dataTransfer.setData('application/x-jaw-workbench'" in javascript
    assert "event.preventDefault()" in javascript
    assert "event.dataTransfer.dropEffect = 'copy'" in javascript
