from jaw.web.assets import static_asset_for


def test_topbar_owns_document_tabs_and_generation_actions():
    loader = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")
    stylesheet = static_asset_for("/document-workbench-structure.css").read().decode("utf-8")

    assert "normalizeTopbarControls" in loader
    assert "page.querySelector('.wb-topbar')" in loader
    assert "topbar.insertBefore(tabs" in loader
    assert "topbar.appendChild(actions)" in loader
    assert "actions.classList.remove('wb-template-actions')" in loader

    assert ".wb-topbar>.wb-document-tabs" in stylesheet
    assert "flex:1 1 auto" in stylesheet
    assert ".wb-topbar>.wb-top-right" in stylesheet
    assert "justify-content:flex-end" in stylesheet
    assert "flex:0 0 auto" in stylesheet
    assert ".wb-pane-head>.wb-template-document-tabs" not in stylesheet
    assert ".wb-pane-head>.wb-template-actions" not in stylesheet
