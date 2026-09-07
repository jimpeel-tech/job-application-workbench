from jaw.web.assets import static_asset_for


def test_workbench_loads_session_workspace_after_core_controller():
    loader = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    assert "'/document-workbench-workspace.js'" in loader
    assert loader.index("'/document-workbench.js'") < loader.index(
        "'/document-workbench-workspace.js'"
    )
    assert loader.index("'/document-workbench-workspace.js'") < loader.index(
        "'/document-workbench-resources.js'"
    )
    assert static_asset_for("/document-workbench-workspace.js") is not None


def test_workbench_workspace_is_document_scoped_and_session_only():
    javascript = static_asset_for("/document-workbench-workspace.js").read().decode("utf-8")

    assert "const documentWorkspaces = new Map()" in javascript
    assert "sectionTabs" in javascript
    assert "functionTabs" in javascript
    assert "activeSection" in javascript
    assert "activeFunction" in javascript
    assert "rememberSnapshot" in javascript
    assert "restoreWorkspace" in javascript
    assert "localStorage" in javascript  # only present in the explanatory non-persistence comment
    assert "localStorage." not in javascript
    assert "sessionStorage." not in javascript


def test_workbench_workspace_resolves_global_resources_through_document_context():
    javascript = static_asset_for("/document-workbench-workspace.js").read().decode("utf-8")

    assert "templateId: document.template_id || document.template?.id || ''" in javascript
    assert "contextsFor(resourceId)" in javascript
    assert "context.documentId === activeDocumentId" in javascript
    assert "Explicit Explorer context must never fall through to a different Document" in javascript
    assert "A Global Template may be shared by several Documents" in javascript
    assert "originalInspectResource(resourceId, { reason: 'workspace-template-selected' })" in javascript


def test_workbench_workspace_ripples_staged_branches_closed():
    javascript = static_asset_for("/document-workbench-workspace.js").read().decode("utf-8")

    assert "pruneCurrentWorkspace" in javascript
    assert "graph.functionIds.has(id)" in javascript
    assert "graph.sectionIds.has(id)" in javascript
    assert "for (const id of invalidFunctions) closeTab('function', id)" in javascript
    assert "for (const id of invalidSections) closeTab('section', id)" in javascript
    assert "resource.state === 'orphaned'" in javascript
    assert "workspace-staged-inspected" in javascript
