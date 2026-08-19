"""Inspect eufyMake Studio cache files without printing secret values."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake.redaction import redact

DEFAULT_CACHE = (
    Path(os.environ["APPDATA"])
    / "eufyMake Studio Profile"
    / "cache"
    / "offline"
    / "device_info"
)

def main() -> None:
    """Print redacted cache summaries."""
    cache_dir = Path(os.environ.get("EUFYMAKE_CACHE_DIR", DEFAULT_CACHE))
    for path in sorted(cache_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            print(f"{path.name}: unable to read ({err})")
            continue

        print(f"\n## {path.name}")
        print(json.dumps(redact(data), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
