"""Root launcher for Excel ID Card Generator."""

import sys
from pathlib import Path

# Add src to sys.path so it works directly from repository root
src_dir = Path(__file__).resolve().parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from id_card_generator.app import main

if __name__ == "__main__":
    sys.exit(main())
