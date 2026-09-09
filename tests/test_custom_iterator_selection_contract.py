from pathlib import Path


def test_custom_iterator_click_updates_logical_iterator_position() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src/jaw/desktop/smart_capture_window.py"
    ).read_text(encoding="utf-8")

    assert "self.custom_iterator_list.currentRowChanged.connect(" in source
    assert "self._sync_custom_iterator_selection" in source
    assert "enabled_position_for_item(" in source
    assert "self._sequence_positions[position_key] = position" in source
