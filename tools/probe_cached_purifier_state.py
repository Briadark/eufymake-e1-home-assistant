"""Read linked Purifier P1 state using cached eufyMake Studio auth."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake.profile import EufyMakeProfileCacheError, EufyMakeProfileCacheStore


def default_profile_dir() -> Path:
    """Return the default eufyMake Studio profile directory."""
    return Path(os.environ["APPDATA"]) / "eufyMake Studio Profile"


def main() -> int:
    """Print the linked P1 state from the cached account token."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-dir", type=Path, default=default_profile_dir())
    args = parser.parse_args()

    auth = _load_auth_module()
    try:
        login = EufyMakeProfileCacheStore(args.profile_dir).load_login()
    except EufyMakeProfileCacheError as err:
        print(f"Unable to load cached login: {err}")
        return 2

    if not login.auth_token or not login.user_id or not login.app_domain:
        print("Cached login is missing auth token, user ID, or app domain.")
        return 2

    country = (login.country_code or "NL").strip().upper()
    try:
        session_key = auth._perform_key_exchange(
            app_domain=login.app_domain,
            timeout=15,
        )
        response = auth._post_encrypted(
            app_domain=login.app_domain,
            path="/v1/app/query_fdm_list",
            body={},
            entry_id=session_key.entry_id,
            share_key_hex=session_key.share_key_hex,
            auth_token=login.auth_token,
            user_id=login.user_id,
            timeout=20,
            country=country,
            extra_headers=auth._desktop_headers(country),
        )
    except auth.EufyMakeAuthError as err:
        print(f"Unable to fetch device list: {err}")
        return 2

    if response.get("code") not in (0, 200):
        print(f"API error: code={response.get('code')} msg={response.get('msg')}")
        return 2

    purifier = _find_purifier(response.get("data"))
    if purifier is None:
        print("No linked Purifier P1 found.")
        return 1

    state = _purifier_state(purifier)
    print("Purifier P1:")
    print(f"  product_name: {purifier.get('product_name') or '<unknown>'}")
    print(
        "  model: "
        f"{purifier.get('device_model') or purifier.get('device_name') or '<unknown>'}"
    )
    print(f"  firmware: {purifier.get('main_sw_version') or '<unknown>'}")
    print(f"  mqtt_status: {purifier.get('mqtt_status')}")
    print(f"  status: {purifier.get('status')}")
    print("  param_type_10037:")
    for key in (
        "work_mode",
        "work_status",
        "filter_health",
        "filter_lifeTime",
        "filter_status",
        "delay",
    ):
        print(f"    {key}: {state.get(key)}")
    return 0


def _load_auth_module():
    component_dir = (
        Path(__file__).resolve().parents[1] / "custom_components" / "eufymake_e1"
    )
    package_name = "custom_components.eufymake_e1"

    import types

    package = types.ModuleType(package_name)
    package.__path__ = [str(component_dir)]
    sys.modules[package_name] = package
    _load_module(f"{package_name}.const", component_dir / "const.py")
    return _load_module(f"{package_name}.auth", component_dir / "auth.py")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _find_purifier(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, list):
        return None
    for device in data:
        if not isinstance(device, dict):
            continue
        for accessory in device.get("accessories") or ():
            if isinstance(accessory, dict) and _is_purifier(accessory):
                return accessory
    return None


def _is_purifier(accessory: dict[str, Any]) -> bool:
    product_name = str(accessory.get("product_name") or "").lower()
    model = str(
        accessory.get("device_model")
        or accessory.get("device_name")
        or accessory.get("machine_name")
        or ""
    ).upper()
    return (
        "purifier p1" in product_name
        or model in {"T5216", "TS5216"}
        or accessory.get("device_type") == 101
    )


def _purifier_state(accessory: dict[str, Any]) -> dict[str, Any]:
    for param in accessory.get("params") or ():
        if not isinstance(param, dict):
            continue
        if _optional_int(param.get("param_type")) != 10037:
            continue
        value = param.get("param_value")
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip().startswith("{"):
            try:
                parsed = __import__("json").loads(value)
            except ValueError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
    return {}


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
