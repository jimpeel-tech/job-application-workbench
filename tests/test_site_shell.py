from jaw.web.assets import static_asset_for


def _site_shell_stylesheet() -> str:
    """Return site shell CSS with platform-independent newlines for contract tests."""
    return (
        static_asset_for("/site-shell.css")
        .read()
        .decode("utf-8")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def test_tracker_workspace_accounts_for_tips_shell_inside_viewport():
    stylesheet = _site_shell_stylesheet()

    assert "#jobsPage{\n  position:fixed;" in stylesheet
    assert "inset:var(--site-header-height) 0 0;" in stylesheet
    assert "#jobsPage.page.active{\n  display:flex;\n  flex-direction:column;" in stylesheet
    assert "#jobsPage > .tips-shell{\n  flex:0 0 auto;" in stylesheet
    assert "#jobsPage > .jobs-layout{\n  flex:1 1 auto;\n  height:auto;" in stylesheet
    assert ".jobs-layout,\n#jobsPage," not in stylesheet


def test_collapsed_tracker_tips_shell_has_no_layout_footprint():
    stylesheet = _site_shell_stylesheet()

    collapsed = stylesheet.split("#jobsPage > .tips-shell.collapsed{", 1)[1]
    collapsed = collapsed.split("}", 1)[0]
    assert "min-height:0;" in collapsed
    assert "height:0;" in collapsed
    assert "margin:0;" in collapsed
    assert "padding:0;" in collapsed


def test_tracker_mobile_layout_returns_to_normal_document_flow():
    stylesheet = _site_shell_stylesheet()

    mobile = stylesheet.split("@media(max-width:760px){", 1)[1]
    assert "#jobsPage{" in mobile
    assert "position:static;" in mobile
    assert "overflow:visible;" in mobile
    assert "#jobsPage.page.active{\n    display:block;" in mobile
    assert "#jobsPage > .jobs-layout{\n    height:auto;" in mobile
