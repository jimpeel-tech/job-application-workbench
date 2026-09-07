from jaw.web.assets import static_asset_for


def test_context_menu_ignores_scroll_from_opening_gesture() -> None:
    source = (
        static_asset_for("/document-workbench-resources.js")
        .read()
        .decode("utf-8")
    )

    assert "let menuScrollCloseReady = false;" in source
    assert "const openedMenu = menu;" in source
    assert "if (menu === openedMenu) menuScrollCloseReady = true;" in source
    assert "if (menu && menuScrollCloseReady) closeMenu();" in source
    assert "shell.addEventListener('scroll', closeMenu, true);" not in source
