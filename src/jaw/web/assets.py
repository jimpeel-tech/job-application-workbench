"""Static assets served by JAW's dependency-free local HTTP transport."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .outlook_assets import decorate_dashboard


class AssetResponse(Protocol):
    """Minimal response interface needed to serve a web asset."""

    def send_response(self, code: int, message: str | None = None) -> None: ...

    def send_header(self, keyword: str, value: str) -> None: ...

    def end_headers(self) -> None: ...

    def write_body(self, body: bytes) -> None: ...


@dataclass(frozen=True, slots=True)
class WebAsset:
    """A file-backed or in-memory HTTP asset and its response metadata."""

    content_type: str
    source: Path | str

    def read(self) -> bytes:
        if isinstance(self.source, Path):
            return self.source.read_bytes()
        return self.source.encode("utf-8")


_PACKAGE_DIR = Path(__file__).resolve().parent.parent


def _native_dashboard_javascript() -> str:
    """Build the browser dashboard without transition-era Document behavior.

    ``dashboard.js`` is still a large source file shared by Tracker, User Data,
    Keybinds, and Capabilities. Documents is now fully owned by the native
    Workbench, so the served browser bundle removes the retired Studio block,
    removes the retired active-user polling loop, and rewires the two remaining
    Documents navigation hooks to the Workbench loader.
    """

    source = (_PACKAGE_DIR / "dashboard.js").read_text(encoding="utf-8")
    studio_start = "// Document Studio -----------------------------------------------------------"
    dashboard_resume = "let timer; $('search').oninput"

    before, marker, retired = source.partition(studio_start)
    if not marker:
        raise RuntimeError("dashboard.js is missing the retired Document Studio marker")
    _discarded, resume, after = retired.partition(dashboard_resume)
    if not resume:
        raise RuntimeError("dashboard.js is missing the post-Document Studio marker")
    source = before.rstrip() + "\n\n" + resume + after

    source, sync_count = re.subn(
        r"\nasync function syncActiveUser\(\) \{\n.*?\n\}\n"
        r"setInterval\(syncActiveUser, 750\);\n"
        r"window\.addEventListener\('focus', syncActiveUser\);\n",
        "\n",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if sync_count != 1:
        raise RuntimeError("dashboard.js active-user polling block changed unexpectedly")

    source, user_switch_count = re.subn(
        r"  if \(\$\('documentsPage'\)\.classList\.contains\('active'\)\) \{\n"
        r"    await loadDocuments\(\{ keepSelection: false \}\);\n"
        r"  \}",
        "  if ($('documentsPage').classList.contains('active')) {\n"
        "    await window.JawWorkbenchLoader?.ensureLoaded?.();\n"
        "  }",
        source,
        count=1,
    )
    if user_switch_count != 1:
        raise RuntimeError("dashboard.js user-scoped Documents reload hook changed unexpectedly")

    legacy_route = """    if (root === 'documents') {
      activateTopPage('documentsPage');
      documentView = Object.hasOwn(DOCUMENT_VIEWS, parts[1]) ? parts[1] : 'profiles';
      selectedDocumentId = '';
      await loadDocuments({ keepSelection: false });
    } else if (root === 'capabilities') {"""
    native_route = """    if (root === 'documents') {
      activateTopPage('documentsPage');
      await window.JawWorkbenchLoader?.ensureLoaded?.();
    } else if (root === 'capabilities') {"""
    if legacy_route not in source:
        raise RuntimeError("dashboard.js Documents hash route changed unexpectedly")
    source = source.replace(legacy_route, native_route, 1)

    return source


_DASHBOARD_JAVASCRIPT = _native_dashboard_javascript()
_DASHBOARD_HTML = (_PACKAGE_DIR / "dashboard.html").read_text(encoding="utf-8")
_DASHBOARD_HTML = _DASHBOARD_HTML.replace(
    "</head>",
    '<link rel="stylesheet" href="/site-shell.css">'
    '<link rel="stylesheet" href="/custom-workspace.css">'
    '<link rel="stylesheet" href="/document-workbench.css">'
    '<link rel="stylesheet" href="/document-workbench-intelligence.css">'
    '<link rel="stylesheet" href="/document-workbench-resources.css">'
    '<link rel="stylesheet" href="/document-workbench-editor.css">'
    '<link rel="stylesheet" href="/document-workbench-transitions.css">'
    '<link rel="stylesheet" href="/document-workbench-repository.css">'
    '<link rel="stylesheet" href="/document-workbench-structure.css">'
    '<link rel="stylesheet" href="/document-generation-commands.css"></head>',
)
_DASHBOARD_HTML = _DASHBOARD_HTML.replace(
    "</body>",
    '<script src="/custom-workspace.js"></script>'
    '<script src="/document-workbench-loader.js"></script>'
    '<script src="/site-commands.js"></script>'
    '<script src="/document-generation-commands.js"></script></body>',
)
_DASHBOARD_HTML = decorate_dashboard(_DASHBOARD_HTML)

DASHBOARD_PAGE = WebAsset(
    "text/html; charset=utf-8",
    _DASHBOARD_HTML,
)

_ANALYSIS_HELP_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JAW · Job Description Analysis Help</title>
<style>
:root{color-scheme:dark;--bg:#15171b;--panel:#202329;--line:#343943;--text:#eef1f5;--muted:#aab2bf;--blue:#65a6e8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 Segoe UI,Arial,sans-serif}
header{padding:18px 24px;border-bottom:1px solid var(--line)}main{max-width:900px;margin:auto;padding:28px 24px}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;margin-bottom:14px}
h1{font-size:21px;margin:0}h2{font-size:17px;margin:0 0 8px;color:var(--blue)}p,li{color:var(--muted)}code{color:var(--text)}
</style></head><body>
<header><h1>JAW · Job Description Analysis</h1></header><main>
<section><h2>What it does</h2><p>JAW extracts the company, title, location, remote status, disclosed pay, match strengths, missing qualifications, and concerns from a captured job description. Match scores are comparison aids—not hiring probabilities.</p></section>
<section><h2>Local Analyzer</h2><p>Runs entirely on this computer using deterministic text and skill matching. No job description is sent to an AI provider. It is private and fast, but its extraction and reasoning are limited.</p></section>
<section><h2>Generative AI</h2><p>Sends the job description plus your Work Experience and the capabilities selected for matching to the chosen provider. The provider returns structured analysis. JAW supports OpenAI and locally hosted Ollama models.</p></section>
<section><h2>Privacy and credentials</h2><p>Ollama analysis stays on the machine running JAW. OpenAI analysis reads the key from <code>OPENAI_API_KEY</code>; JAW does not save that key in SQLite, configuration files, exports, or the website.</p></section>
<section><h2>Cost and connection testing</h2><p>OpenAI analysis uses API tokens and may incur provider charges. Local Ollama inference has no per-request API charge. “Test connection” verifies that the selected model is available without running a job analysis.</p></section>
</main></body></html>"""

JOB_ANALYSIS_HELP_PAGE = WebAsset(
    "text/html; charset=utf-8",
    _ANALYSIS_HELP_HTML,
)

_STATIC_ASSETS = {
    "/favicon.png": WebAsset(
        "image/png",
        _PACKAGE_DIR / "resources" / "icons" / "jaw_favicon.png",
    ),
    "/dashboard.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "dashboard.css",
    ),
    "/site-shell.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "site_shell.css",
    ),
    "/custom-workspace.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "custom_workspace.css",
    ),
    "/custom-workspace.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "custom_workspace.js",
    ),
    "/site-commands.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "site_commands.js",
    ),
    "/dashboard.js": WebAsset(
        "text/javascript; charset=utf-8",
        _DASHBOARD_JAVASCRIPT,
    ),
    "/document-generation-commands.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "document_generation_commands.css",
    ),
    "/document-generation-commands.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_generation_commands.js",
    ),
    "/document-workbench-loader.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_loader.js",
    ),
    "/document-workbench.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "document_workbench.css",
    ),
    "/document-workbench-intelligence.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_intelligence.css",
    ),
    "/document-workbench-resources.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_resources.css",
    ),
    "/document-workbench-editor.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_editor.css",
    ),
    "/document-workbench-transitions.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_transitions.css",
    ),
    "/document-workbench-repository.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_repository.css",
    ),
    "/document-workbench-structure.css": WebAsset(
        "text/css; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_structure.css",
    ),
    "/document-workbench.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench.js",
    ),
    "/document-workbench-workspace.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_workspace.js",
    ),
    "/document-workbench-intelligence.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_intelligence.js",
    ),
    "/document-workbench-reference-ids.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_reference_ids.js",
    ),
    "/document-workbench-multi-reference.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_multi_reference.js",
    ),
    "/document-workbench-resources.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_resources.js",
    ),
    "/document-workbench-editor.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_editor.js",
    ),
    "/document-workbench-transitions.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_transitions.js",
    ),
    "/document-workbench-repository.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_repository.js",
    ),
    "/document-workbench-preview.js": WebAsset(
        "text/javascript; charset=utf-8",
        _PACKAGE_DIR / "document_workbench_preview.js",
    ),
}


def static_asset_for(path: str) -> WebAsset | None:
    """Return the static asset mounted at *path*, if one exists."""

    return _STATIC_ASSETS.get(path)


def send_asset(response: AssetResponse, asset: WebAsset) -> None:
    """Write an asset using the dashboard's established response semantics."""

    body = asset.read()
    response.send_response(200)
    response.send_header("Content-Type", asset.content_type)
    response.send_header("Cache-Control", "no-store")
    response.send_header("Content-Length", str(len(body)))
    response.end_headers()
    response.write_body(body)