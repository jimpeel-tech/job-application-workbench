from __future__ import annotations

import pytest

from jaw.documents import DocumentRenderRequest, TectonicRenderer, find_tectonic


pytestmark = pytest.mark.skipif(
    find_tectonic() is None,
    reason="Tectonic is not installed for the real document smoke test",
)


def test_real_tectonic_renders_with_bundled_font() -> None:
    renderer = TectonicRenderer(timeout=180)
    source = r"""
\documentclass[10pt]{article}
\usepackage{fontspec}
\setmainfont{OpenSans-Regular.ttf}[
  BoldFont = OpenSans-Bold.ttf,
  ItalicFont = OpenSans-Italic.ttf,
  BoldItalicFont = OpenSans-BoldItalic.ttf
]
\pagestyle{empty}
\begin{document}
Hello {{ name }}. Bundled font staging is working.
\end{document}
"""

    result = renderer.render(
        DocumentRenderRequest(
            template_source=source,
            context={"name": "JAW"},
            output_name="jaw-tectonic-smoke",
            only_cached=False,
            autoescape_text=True,
        )
    )

    assert result.pdf_bytes.startswith(b"%PDF")
    assert "Hello JAW" in result.rendered_source
    assert result.renderer == "tectonic"
    assert "--untrusted" in result.command
