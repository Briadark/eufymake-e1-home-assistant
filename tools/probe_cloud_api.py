"""Probe read-only eufyMake cloud API calls with cached login metadata."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake import EufyMakeProfileCacheStore
from pyeufymake.cloud import EufyMakeCloudProbe, EufyMakeCloudProbeError
from pyeufymake.profile import EufyMakeProfileCacheError
from pyeufymake.redaction import redact


def default_profile_dir() -> Path:
    """Return the default eufyMake Studio profile directory."""
    return Path(os.environ["APPDATA"]) / "eufyMake Studio Profile"


def main() -> int:
    """Run read-only cloud probes and print redacted results."""
    profile_dir = Path(os.environ.get("EUFYMAKE_PROFILE_DIR", default_profile_dir()))

    try:
        login = EufyMakeProfileCacheStore(profile_dir).load_login()
        probe = EufyMakeCloudProbe(login)
    except (EufyMakeProfileCacheError, EufyMakeCloudProbeError) as err:
        print(f"Unable to start probe: {err}")
        return 2

    print(f"Using app domain: {login.app_domain}")
    print("Token value is loaded from cache but will not be printed.")

    for result in probe.probe_read_only():
        print(
            "\n"
            f"{result.name} "
            f"{result.method} "
            f"{result.header_variant}: "
            f"status={result.status} ok={result.ok}"
        )
        if result.error:
            print(f"error: {result.error}")
        if result.body is not None:
            print(json.dumps(redact(result.body), indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

