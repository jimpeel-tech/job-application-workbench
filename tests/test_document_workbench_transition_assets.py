from jaw.web.assets import DASHBOARD_PAGE, static_asset_for


def test_transition_assets_are_served_and_loaded_in_editor_order():
    dashboard = DASHBOARD_PAGE.read().decode("utf-8")
    loader = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    assert '/document-workbench-transitions.css' in dashboard
    assert static_asset_for("/document-workbench-transitions.css") is not None
    assert static_asset_for("/document-workbench-transitions.js") is not None

    editor = loader.index("'/document-workbench-editor.js'")
    transitions = loader.index("'/document-workbench-transitions.js'")
    preview = loader.index("'/document-workbench-preview.js'")
    assert editor < transitions < preview


def test_transition_script_holds_graph_changes_until_explicit_action():
    javascript = static_asset_for("/document-workbench-transitions.js").read().decode("utf-8")

    assert "Update ${kindLabel}" in javascript
    assert "Create ${esc(kindLabel)}" in javascript
    assert "data-wb-reference-cancel" in javascript
    assert "cancelPendingEdit" in javascript
    assert "event.stopImmediatePropagation()" in javascript
    assert "'Validating update…'" in javascript
    assert "'create', 'preview'" in javascript
    assert "data-choice=\"stage\"" in javascript
    assert "data-choice=\"delete\"" in javascript
    assert "textContent = 'STAGED'" in javascript
    assert "Choose an action in the reference dialog." in javascript
    assert "reference_id: session.referenceId" in javascript
    assert "reference_start: session.token.start" in javascript
    assert "reference_end: session.token.end" in javascript


def test_reference_identity_parser_excludes_jaw_runtime_symbols():
    javascript = static_asset_for("/document-workbench-reference-ids.js").read().decode("utf-8")

    assert "const JAW_SYMBOLS = new Set([" in javascript
    for symbol in (
        "user",
        "job_ref",
        "work_exp",
        "cap",
        "system",
        "csv",
        "latex_raw",
        "dump",
        "describe",
    ):
        assert f"'{symbol}'" in javascript
    for retired in ("'job'", "'capabilities'", "'work_experience'"):
        assert retired not in javascript
    assert "if (JAW_SYMBOLS.has(match[0])) continue;" in javascript
    assert "&& !JAW_SYMBOLS.has(String(reference.symbol))" in javascript
    assert "position >= binding.start && position < binding.end" in javascript


def test_jaw_objects_panel_uses_new_roots_and_debug_helpers():
    javascript = static_asset_for("/document-workbench-reference-ids.js").read().decode("utf-8")

    assert "['user', 'job_ref', 'work_exp', 'cap', 'system']" in javascript
    assert "{ path: 'dump(...)', insert: 'dump()', method: true }" in javascript
    assert "{ path: 'describe(...)', insert: 'describe()', method: true }" in javascript
