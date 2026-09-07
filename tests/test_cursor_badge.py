from jaw.desktop.iterator_state import iterator_preview_rows


def test_iterator_preview_centers_two_neighbors_each_side():
    values = ["LinkedIn", "Portfolio", "GitHub", "Facebook", "X"]

    assert iterator_preview_rows(values, 2) == (
        ("LinkedIn", -2),
        ("Portfolio", -1),
        ("GitHub", 0),
        ("Facebook", 1),
        ("X", 2),
    )


def test_iterator_preview_does_not_wrap_at_start():
    values = ["LinkedIn", "Portfolio", "GitHub", "Facebook", "X"]

    assert iterator_preview_rows(values, 0) == (
        ("LinkedIn", 0),
        ("Portfolio", 1),
        ("GitHub", 2),
    )


def test_iterator_preview_does_not_wrap_at_end():
    values = ["LinkedIn", "Portfolio", "GitHub", "Facebook", "X"]

    assert iterator_preview_rows(values, 4) == (
        ("GitHub", -2),
        ("Facebook", -1),
        ("X", 0),
    )


def test_iterator_preview_handles_short_and_invalid_sequences():
    assert iterator_preview_rows(["Only"], 0) == (("Only", 0),)
    assert iterator_preview_rows([], 0) == ()
    assert iterator_preview_rows(["A", "B"], -1) == ()
    assert iterator_preview_rows(["A", "B"], 2) == ()
