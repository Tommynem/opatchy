import sys
from pathlib import Path
from typing import Final

HELPER_ROOT: Final = Path(__file__).resolve().parents[2] / "helper"
sys.path.insert(0, str(HELPER_ROOT))
