from jaw.web.assets import static_asset_for

WORKBENCH_MODULES = (
    "/document-workbench.js",
    "/document-workbench-workspace.js",
    "/document-workbench-intelligence.js",
    "/document-workbench-reference-ids.js",
    "/document-workbench-multi-reference.js",
    "/document-workbench-resources.js",
    "/document-workbench-editor.js",
    "/document-workbench-transitions.js",
    "/document-workbench-repository.js",
    "/document-workbench-preview.js",
)


def test_every_lazy_workbench_module_is_a_served_asset():
    loader = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    for path in WORKBENCH_MODULES:
        assert repr(path) in loader
        assert static_asset_for(path) is not None


def test_workbench_loader_retries_failed_modules_without_trusting_stale_script_nodes():
    loader = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    assert "function loadScriptAttempt(src)" in loader
    assert "script.dataset.jawWorkbenchLoaded === 'true'" in loader
    assert "script.remove();" in loader
    assert "Retrying Workbench module" in loader
