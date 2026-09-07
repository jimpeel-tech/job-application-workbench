from jaw.web.assets import DASHBOARD_PAGE, static_asset_for


def test_unified_custom_workspace_is_served_after_dashboard_runtime():
    page = DASHBOARD_PAGE.read().decode("utf-8")
    assert '/custom-workspace.css' in page
    assert '/custom-workspace.js' in page
    assert page.index('/dashboard.js') < page.index('/custom-workspace.js')


def test_custom_workspace_unifies_data_actions_and_keybind_workflow():
    javascript = static_asset_for('/custom-workspace.js').read().decode('utf-8')
    stylesheet = static_asset_for('/custom-workspace.css').read().decode('utf-8')

    assert "dataTab.textContent = 'Custom'" in javascript
    assert 'actionTab.hidden = true' in javascript
    assert 'Custom Items' in javascript
    assert 'Expose as Action' in javascript
    assert 'Single Paste' in javascript
    assert 'Iterator' in javascript
    assert 'Manage in Keybinds' in javascript
    assert "api('/api/user/custom-fields'" in javascript
    assert "api('/api/user/custom-actions'" in javascript
    assert 'removeOrphanField' in javascript
    assert "location.hash !== '#user/custom-actions'" in javascript
    assert '#customActionsTab{display:none!important}' in stylesheet


def test_custom_workspace_preserves_existing_ids_and_shared_values():
    javascript = static_asset_for('/custom-workspace.js').read().decode('utf-8')

    assert "key: `action:${action.id}`" in javascript
    assert "key: `field:${field.id}`" in javascript
    assert 'referenceCount(field.id) > 1' in javascript
    assert 'Editing the value updates every action that uses it.' in javascript
    assert "actions().splice(index, 1)" in javascript
    assert "selectedKey = primary ? `field:${primary.id}` : ''" in javascript
