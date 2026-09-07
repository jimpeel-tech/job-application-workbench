from __future__ import annotations

from inspect import getsource

from jaw.config import BUILTIN_ACTION_LABELS, WorkEntry
from jaw.main import MainWindow


class RowModel:
    def __init__(self, row: int = 0) -> None:
        self.row = row

    def currentRow(self) -> int:
        return self.row

    def setCurrentRow(self, row: int) -> None:
        self.row = row


def test_work_exp_parent_actions_are_registered_and_dispatched() -> None:
    assert BUILTIN_ACTION_LABELS["previous_work_exp"] == "Prev Work Exp"
    assert BUILTIN_ACTION_LABELS["next_work_exp"] == "Next Work Exp"
    source = getsource(MainWindow._dispatch_action)
    assert "previous_work_exp" in source
    assert "next_work_exp" in source


def test_parent_work_exp_navigation_skips_disabled_entries_in_both_directions() -> None:
    class Harness:
        job_order = [
            WorkEntry("One", "A", "", "", enabled=True),
            WorkEntry("Two", "B", "", "", enabled=False),
            WorkEntry("Three", "C", "", "", enabled=True),
        ]
        titles_list = RowModel(0)

    harness = Harness()
    MainWindow.move_work_experience_iterator(harness, 1)
    assert harness.titles_list.currentRow() == 2
    MainWindow.move_work_experience_iterator(harness, 1)
    assert harness.titles_list.currentRow() == 0
    MainWindow.move_work_experience_iterator(harness, -1)
    assert harness.titles_list.currentRow() == 2


def test_child_work_exp_navigation_skips_disabled_fields_in_both_directions() -> None:
    class Harness:
        field_order = ["company", "title", "start", "end", "highlights"]
        disabled_child_fields = {"title", "end"}
        job_fields_list = RowModel(0)

    harness = Harness()
    MainWindow.move_work_field_iterator(harness, 1)
    assert harness.job_fields_list.currentRow() == 2
    MainWindow.move_work_field_iterator(harness, -1)
    assert harness.job_fields_list.currentRow() == 0


def test_work_exp_cursor_uses_role_number_on_active_child_row() -> None:
    source = getsource(MainWindow._update_cursor_badge)
    assert "disabled_child_fields" in source
    assert "active_prefix=str(job_row + 1)" in source
    assert "context=context" not in source
