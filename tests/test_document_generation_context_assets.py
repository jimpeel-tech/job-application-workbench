from pathlib import Path


def test_documents_command_palette_exposes_generation_context_selection():
    source = Path("src/jaw/site_commands.js").read_text(encoding="utf-8")

    assert "Documents: Set Generation Context" in source
    assert "Automatic — Latest tracked job" in source
    assert "Example Data" in source
    assert "generation_context" in source
    assert "generation_context_info" in source
    assert "JawCommands.register('documentsPage'" in source
    assert "/api/workbench/routing/save" in source
    assert "wbGenerationContextStatus" in source
