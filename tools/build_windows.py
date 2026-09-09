from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import PyInstaller.__main__
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ICON = ROOT / "src" / "jaw" / "resources" / "icons" / "jaw_app.png"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build" / "pyinstaller"
WINDOWS_ICON = BUILD_DIR / "jaw_app.ico"


def create_windows_icon() -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.open(SOURCE_ICON).convert("RGBA")
    image.save(
        WINDOWS_ICON,
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    return WINDOWS_ICON


def main() -> int:
    parser = argparse.ArgumentParser(description="Build JAW for Windows with PyInstaller.")
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build a directory distribution instead of the default single JAW.exe.",
    )
    args = parser.parse_args()

    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    if args.onedir:
        shutil.rmtree(DIST_DIR / "JAW", ignore_errors=True)
    else:
        (DIST_DIR / "JAW.exe").unlink(missing_ok=True)

    icon = create_windows_icon()
    pyinstaller_args = [
        str(ROOT / "run.py"),
        "--name",
        "JAW",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--icon",
        str(icon),
        "--paths",
        str(ROOT / "src"),
        "--collect-data",
        "jaw",
        # Template-release compatibility reads the installed JAW version via
        # importlib.metadata. Preserve the distribution metadata inside both
        # onefile and onedir builds so packaged JAW resolves the same version
        # declared in pyproject.toml.
        "--copy-metadata",
        "jaw",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / "work"),
        "--specpath",
        str(BUILD_DIR / "spec"),
        "--onedir" if args.onedir else "--onefile",
    ]
    PyInstaller.__main__.run(pyinstaller_args)

    output = DIST_DIR / ("JAW" if args.onedir else "JAW.exe")
    if not output.exists():
        raise RuntimeError(f"PyInstaller completed without producing {output}")
    print(f"Built: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
