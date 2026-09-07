import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from jaw.desktop.smart_capture_window import main

if __name__ == "__main__":
    raise SystemExit(main())
