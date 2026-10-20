"""PyInstaller entry point for the self-contained Ruby desktop assistant."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from background_agent.bridge.production_server import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
