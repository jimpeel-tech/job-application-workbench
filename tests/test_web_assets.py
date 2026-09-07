from jaw.web.assets import (
    DASHBOARD_PAGE,
    JOB_ANALYSIS_HELP_PAGE,
    WebAsset,
    send_asset,
    static_asset_for,
)


class RecordingResponse:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.body = b""
        self.ended = False

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, keyword, value):
        self.headers[keyword] = value

    def end_headers(self):
        self.ended = True

    def write_body(self, body):
        self.body = body


def test_asset_catalog_uses_lazy_native_workbench_and_document_commands():
    dashboard = DASHBOARD_PAGE.read()
    assert b"Job Application Workbench" in dashboard
    assert b"/site-shell.css" in dashboard
    assert b"/custom-workspace.css" in dashboard
    assert b"/custom-workspace.js" in dashboard
    assert b"/document-workbench.css" in dashboard
    assert b"/document-workbench-repository.css" in dashboard
    assert b"/document-workbench-structure.css" in dashboard
    assert b"/document-generation-commands.css" in dashboard
    assert b"/dashboard-startup-guard.js" not in dashboard
    assert b"/document-workbench-loader.js" in dashboard
    assert b"/site-commands.js" in dashboard
    assert b"/document-generation-commands.js" in dashboard
    assert b'<script src="/document-workbench.js"></script>' not in dashboard
    assert b'<div id="documentsPage" class="page"></div>' in dashboard
    assert b"Document Studio" not in dashboard
    assert b"trackerDocumentDialog" not in dashboard

    for path in (
        "/dashboard.css",
        "/dashboard.js",
        "/site-shell.css",
        "/custom-workspace.css",
        "/custom-workspace.js",
        "/document-generation-commands.css",
        "/document-generation-commands.js",
        "/document-workbench-loader.js",
        "/document-workbench-intelligence.css",
        "/document-workbench-resources.css",
        "/document-workbench-editor.css",
        "/document-workbench-repository.css",
        "/document-workbench-structure.css",
        "/document-workbench.js",
        "/document-workbench-intelligence.js",
        "/document-workbench-resources.js",
        "/document-workbench-editor.js",
        "/document-workbench-repository.js",
        "/document-workbench-preview.js",
        "/site-commands.js",
    ):
        assert static_asset_for(path) is not None

    for retired in (
        "/dashboard-startup-guard.js",
        "/document-workbench-bootstrap.js",
        "/document-workbench-structure.js",
        "/document-workbench-system-template.js",
        "/document-workbench-mutation-debug.js",
        "/review.css",
        "/review.js",
    ):
        assert static_asset_for(retired) is None
    assert static_asset_for("/missing") is None


def test_served_dashboard_bundle_excludes_retired_document_studio_and_user_polling():
    javascript = static_asset_for("/dashboard.js").read().decode("utf-8")

    assert "Document Studio ------------------------------------------------" not in javascript
    assert "/api/documents/" not in javascript
    assert "DOCUMENT_VIEWS" not in javascript
    assert "trackerDocumentDialog" not in javascript
    assert "loadDocuments(" not in javascript
    assert "loadJobs(); const initial" in javascript
    assert "new URLSearchParams(location.search).get('job')" in javascript
    assert "syncActiveUser" not in javascript
    assert "setInterval(syncActiveUser, 750)" not in javascript
    assert "addEventListener('focus', syncActiveUser)" not in javascript
    assert "window.JawWorkbenchLoader?.ensureLoaded?.()" in javascript


def test_workbench_loader_only_activates_from_route_or_initial_documents_page():
    javascript = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    assert "page.classList.contains('active')" in javascript
    assert "'/document-workbench.js'" in javascript
    assert "'/document-workbench-intelligence.js'" in javascript
    assert "'/document-workbench-resources.js'" in javascript
    assert "'/document-workbench-editor.js'" in javascript
    assert "'/document-workbench-repository.js'" in javascript
    assert "'/document-workbench-preview.js'" in javascript
    assert "document-workbench-structure.js" not in javascript
    assert "document-workbench-system-template.js" not in javascript
    assert "document-workbench-mutation-debug.js" not in javascript
    assert "MutationObserver" not in javascript
    assert "setInterval" not in javascript
    assert "setTimeout" not in javascript
    assert "scheduleActivation" not in javascript
    assert "addEventListener('hashchange'" not in javascript
    assert "#drawer .nav" not in javascript
    assert "syncActiveUser" not in javascript
    assert "if (active()) void ensureLoaded();" in javascript


def test_workbench_loader_normalizes_explorer_without_dom_observers():
    javascript = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    assert "function normalizeExplorer()" in javascript
    assert "store.subscribe(scheduleExplorerNormalization)" in javascript
    assert "explorer.addEventListener('click', scheduleExplorerNormalization)" in javascript
    assert "document: 'Doc'" in javascript
    assert "template: 'Temp'" in javascript
    assert "section: 'Sect'" in javascript
    assert "function: 'Func'" in javascript
    assert "MutationObserver" not in javascript


def test_workbench_loader_polishes_drag_image_and_editor_drop_caret():
    javascript = static_asset_for("/document-workbench-loader.js").read().decode("utf-8")

    assert "function installDragDropPolish()" in javascript
    assert "setDragImage(ghost, 8, -6)" in javascript
    assert "application/x-jaw-workbench" in javascript
    assert "[data-wb-drop-caret]" in javascript
    assert "function mirrorDropPoint(editor, event)" in javascript
    assert "document.caretRangeFromPoint" in javascript
    assert "document.caretPositionFromPoint" in javascript
    assert "whiteSpace: style.whiteSpace" in javascript
    assert "overflowWrap: style.overflowWrap" in javascript
    assert "updateDropCaret(editor, event)" in javascript
    assert "hideDropCarets" in javascript
    assert "columnsPerRow" not in javascript
    assert "rowStartColumn" not in javascript
    assert "dragMeasureCanvas" not in javascript


def test_workbench_controller_owns_one_native_state_store():
    javascript = static_asset_for("/document-workbench.js").read().decode("utf-8")

    assert "'/api/workbench/state'" in javascript
    assert "'/api/workbench/checkpoint'" in javascript
    assert "'/api/workbench/save'" in javascript
    assert "'/api/workbench/meta'" in javascript
    assert "'/api/workbench/link'" in javascript
    assert "'/api/workbench/delete'" in javascript
    assert "window.JawWorkbenchStore" in javascript
    assert "const subscribers = new Set()" in javascript
    assert "/api/documents/" not in javascript


def test_workbench_jaw_palette_uses_dataset_camel_case_for_drag_and_selection():
    javascript = static_asset_for("/document-workbench.js").read().decode("utf-8")

    assert 'data-wb-jaw="' in javascript
    assert 'data-wb-select-jaw="' in javascript
    assert "jaw.dataset.wbJaw" in javascript
    assert "selectJaw.dataset.wbSelectJaw" in javascript
    assert "dataset.wbJAW" not in javascript
    assert "dataset.wbSelectJAW" not in javascript


def test_workbench_command_palette_owns_documents_ctrl_p_actions():
    javascript = static_asset_for("/document-workbench.js").read().decode("utf-8")
    commands = static_asset_for("/document-generation-commands.js").read().decode("utf-8")

    assert "Command Palette" in javascript
    assert "Go to Item" in javascript
    assert "Document Routing" in javascript
    assert "action: 'document-routing'" in javascript
    assert "window.JawDocumentGeneration?.open?.()" in javascript
    assert "window.JawCommands.register('jobsPage'" in commands
    assert "window.JawCommands.register('documentsPage'" not in commands


def test_workbench_ctrl_drag_resizes_editor_panes_without_replacing_ctrl_click():
    javascript = static_asset_for("/document-workbench.js").read().decode("utf-8")
    stylesheet = static_asset_for("/document-workbench.css").read().decode("utf-8")

    assert "let resizePending = null" in javascript
    assert "function editorResizeZone(event)" in javascript
    assert "event.target.closest('.wb-editor-body')" in javascript
    assert "Math.hypot" in javascript
    assert "< 4" in javascript
    assert "suppressCtrlClick" in javascript
    assert "navigateEditorSymbol(kind, editor)" in javascript
    assert "wb-vertical-resize-ready" in javascript
    assert "wb-vertical-resize-ready" in stylesheet
    assert "cursor:ns-resize" in stylesheet


def test_document_generation_commands_use_native_workbench_routes():
    javascript = static_asset_for("/document-generation-commands.js").read().decode("utf-8")

    assert "/api/workbench/state" in javascript
    assert "/api/workbench/routing" in javascript
    assert "/api/workbench/routing/save" in javascript
    assert "/api/workbench/generate-job" in javascript
    assert "/api/workbench/open-output" in javascript
    assert "/api/documents/" not in javascript
    assert "manager" in javascript
    assert "director" in javascript
    assert "architect" in javascript
    assert "Lead” is intentionally not treated as management" in javascript
    assert "sessionStorage.setItem(JOB_KEY" in javascript
    assert "window.openTrackerDocuments = jobId => generateForJob(jobId)" in javascript
    assert "window.JawCommands.register('jobsPage'" in javascript
    assert "window.JawCommands.register('documentsPage'" not in javascript
    assert "location.hash =" not in javascript


def test_site_commands_prefers_registered_provider_then_documents_workbench_fallback():
    javascript = static_asset_for("/site-commands.js").read().decode("utf-8")
    keydown_handler = javascript[javascript.index("document.addEventListener('keydown'") :]

    provider_check = "if (providers.has(activePageId()))"
    workbench_fallback = (
        "if (activePageId() === 'documentsPage' && window.JawDocumentWorkbench?.openQuick)"
    )
    assert provider_check in keydown_handler
    assert workbench_fallback in keydown_handler
    assert keydown_handler.index(provider_check) < keydown_handler.index(workbench_fallback)


def test_workbench_intelligence_uses_shared_store_and_current_semantics():
    javascript = static_asset_for("/document-workbench-intelligence.js").read().decode("utf-8")
    stylesheet = static_asset_for("/document-workbench-intelligence.css").read().decode("utf-8")

    assert "window.JawWorkbenchStore" in javascript
    assert "'latex_raw'" in javascript
    assert "(?::(?:text|list))?" in javascript
    assert "Generation blocks belong in Sections or Functions" in javascript
    assert "Syntax: ✓" in javascript
    assert "wb-syn-private" in stylesheet
    assert "wb-syn-global" in stylesheet
    assert "wb-syn-jaw" in stylesheet
    assert "wb-syn-local" in stylesheet
    assert "wb-syn-orphan" in stylesheet
    assert "wb-syn-unresolved" in stylesheet


def test_workbench_intelligence_observer_only_tracks_editor_resource_identity():
    javascript = static_asset_for("/document-workbench-intelligence.js").read().decode("utf-8")

    assert "new MutationObserver" in javascript
    assert "attributeFilter: ['data-resource-id']" in javascript
    assert "mutation.attributeName === 'data-resource-id'" in javascript
    assert "documentTabs" not in javascript
    assert "setInterval(" not in javascript


def test_workbench_resource_assets_use_shared_store_and_current_actions():
    javascript = static_asset_for("/document-workbench-resources.js").read().decode("utf-8")
    stylesheet = static_asset_for("/document-workbench-resources.css").read().decode("utf-8")

    assert "window.JawWorkbenchStore" in javascript
    assert "Rename Symbol…" in javascript
    assert "Make Global" in javascript
    assert "Copy Reference" in javascript
    assert "Delete" in javascript
    assert "Rename…" not in javascript
    assert "MutationObserver" not in javascript
    assert "wb-context-menu" in stylesheet
    assert "wb-tree-kind" in stylesheet
    assert ".wb-explorer .wb-kind-dot" in stylesheet


def test_workbench_repository_assets_use_dedicated_repository_routes():
    javascript = static_asset_for("/document-workbench-repository.js").read().decode("utf-8")
    stylesheet = static_asset_for("/document-workbench-repository.css").read().decode("utf-8")

    assert "+ Template Repo" in javascript
    assert "Template Repository" in javascript
    assert "/api/workbench/repository" in javascript
    assert "/api/workbench/repository/download" in javascript
    assert "/api/workbench/repository/open-local" in javascript
    assert "/api/workbench/repository/clone" in javascript
    assert "Download" in javascript
    assert "Open Local" in javascript
    assert "Clone" in javascript
    assert "MutationObserver" not in javascript
    assert "wb-repository-dialog" in stylesheet


def test_workbench_editor_assets_handle_tab_indentation_and_tab_scrollbar():
    javascript = static_asset_for("/document-workbench-editor.js").read().decode("utf-8")
    stylesheet = static_asset_for("/document-workbench-editor.css").read().decode("utf-8")

    assert "event.key !== 'Tab'" in javascript
    assert "event.shiftKey" in javascript
    assert "INDENT = '  '" in javascript
    assert "::-webkit-scrollbar" in stylesheet
    assert "height: 23px" in stylesheet


def test_send_asset_preserves_no_store_response_semantics():
    response = RecordingResponse()

    send_asset(response, WebAsset("text/plain; charset=utf-8", "hello"))

    assert response.status == 200
    assert response.headers == {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
        "Content-Length": "5",
    }
    assert response.ended is True
    assert response.body == b"hello"


def test_analysis_help_asset_remains_available():
    body = JOB_ANALYSIS_HELP_PAGE.read().decode("utf-8")
    assert "Job Description Analysis" in body
    assert "Local Analyzer" in body
    assert "Generative AI" in body
