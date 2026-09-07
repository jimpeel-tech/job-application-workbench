import re

from jaw.documents.workbench_symbols import JAW_SYMBOLS
from jaw.web.assets import static_asset_for


def test_workbench_syntax_runtime_roots_match_backend_contract() -> None:
    javascript = static_asset_for("/document-workbench-intelligence.js").read().decode("utf-8")
    match = re.search(
        r"const JAW_ROOTS = new Set\(\[\s*(.*?)\s*\]\);",
        javascript,
        re.DOTALL,
    )

    assert match is not None
    highlighted_roots = set(re.findall(r"'([A-Za-z_][A-Za-z0-9_]*)'", match.group(1)))
    assert highlighted_roots == JAW_SYMBOLS
