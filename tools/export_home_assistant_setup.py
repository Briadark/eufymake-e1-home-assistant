"""Export eufyMake E1 setup JSON for the Home Assistant integration."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake.setup_export import (  # noqa: E402
    EufyMakeSetupExportError,
    build_setup_export,
)


def default_profile_dir() -> Path:
    """Return the default eufyMake Studio profile directory."""
    return Path(os.environ["APPDATA"]) / "eufyMake Studio Profile"


def main() -> int:
    """Print setup JSON for pasting into Home Assistant."""
    profile_dir = Path(os.environ.get("EUFYMAKE_PROFILE_DIR", default_profile_dir()))
    cache_dir = Path(
        os.environ.get(
            "EUFYMAKE_CACHE_DIR",
            profile_dir / "cache" / "offline" / "device_info",
        )
    )
    serial_number = os.environ.get("EUFYMAKE_DEVICE_SN")

    try:
        setup_export = build_setup_export(
            profile_dir,
            cache_dir,
            serial_number=serial_number,
        )
    except EufyMakeSetupExportError as err:
        print(f"Unable to export Home Assistant setup JSON: {err}", file=sys.stderr)
        return 2

    print(json.dumps(setup_export, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
