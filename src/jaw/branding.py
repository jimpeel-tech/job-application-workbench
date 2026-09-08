from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ICON_DIR = PACKAGE_DIR / "resources" / "icons"

APP_ICON_PATH = ICON_DIR / "jaw_app.png"
TRAY_ICON_PATH = ICON_DIR / "jaw_tray.png"
TITLEBAR_ICON_PATH = ICON_DIR / "jaw_titlebar.png"
FAVICON_PATH = ICON_DIR / "jaw_favicon.png"

WINDOWS_APP_USER_MODEL_ID = "jimpeel-tech.JobApplicationWorkbench"


def set_windows_app_user_model_id() -> None:
    # Give Windows a stable identity for taskbar grouping/pinning.
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WINDOWS_APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        # Branding should never prevent JAW from starting on an unusual Windows host.
        pass
