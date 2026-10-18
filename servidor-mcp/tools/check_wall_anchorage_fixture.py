"""Print the deterministic, non-construction synthetic fixture to stdout."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wall_detail_checks import anchorage_fixture

if __name__ == "__main__":
    print(json.dumps(anchorage_fixture(), indent=2))
