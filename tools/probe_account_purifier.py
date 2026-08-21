"""Probe read-only eufyMake account endpoints for purifier discovery."""

from __future__ import annotations

import getpass
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


READ_ONLY_PATHS = (
    ("device_list_v1", "/v1/app/query_fdm_list"),
    ("device_list_v3", "/v3/app/query_fdm_list"),
    ("maker_parts_v1", "/v1/app/query_makerpart_list"),
    ("maker_parts_v3", "/v3/app/query_makerpart_list"),
    ("user_profile_v3", "/v3/passport/profile"),
    ("user_params_v3", "/v3/pc/passport/get_user_params"),
)

SENSITIVE_KEYS = {
    "access_token",
    "auth_token",
    "client_secret_info",
    "admin_user_id",
    "action_user_email",
    "action_user_name",
    "app_conn",
    "bt_mac",
    "eth_mac",
    "ip_addr",
    "lot_number",
    "machine_name",
    "dsk_key",
    "email",
    "file_md5",
    "file_path",
    "key",
    "mac",
    "mac_addr",
    "mac_address",
    "ndt_did",
    "ndt_license",
    "p2p_conn",
    "p2p_did",
    "p2p_license",
    "push_did",
    "push_license",
    "secret_key",
    "server_secret_info",
    "station_sn",
    "token",
    "user_id",
    "wifi_mac",
    "wifi_ssid",
    "wakeup_key",
    "wipn_enc_dec_key",
    "wipn_ndt_aes128key",
}


def main() -> int:
    """Run an interactive, redacted purifier discovery probe."""
    auth = _load_auth_module()
    country = input("Country code (default NL): ").strip().upper() or "NL"
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    client = auth.EufyMakeCloudAuthClient(country=country)
    try:
        result = client.login(email=email, password=password)
    except auth.EufyMakeApiCodeError as err:
        print(f"Login API error: code={err.code} msg={err.message}")
        _print_redacted_api_data(err.data)
        return 2
    except auth.EufyMakeAuthError as err:
        print(f"Login failed: {err}")
        return 2

    print("Login ok.")
    print(f"Setup-visible E1 devices: {len(result.devices)}")

    for name, path in READ_ONLY_PATHS:
        print(f"\n{name} {path}")
        try:
            response = auth._post_encrypted(
                app_domain=result.session.app_domain,
                path=path,
                body={},
                entry_id=result.session.entry_id,
                share_key_hex=result.session.share_key_hex,
                auth_token=result.session.auth_token,
                user_id=result.session.user_id,
                timeout=20,
                country=country,
                extra_headers=auth._desktop_headers(country),
            )
        except auth.EufyMakeAuthError as err:
            print(f"  error: {err}")
            continue

        code = response.get("code")
        msg = response.get("msg")
        data = response.get("data")
        print(f"  code={code} msg={msg!r}")
        _print_summary(data)

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


def _print_summary(data: Any) -> None:
    if isinstance(data, list):
        print(f"  data: list length={len(data)}")
        for index, item in enumerate(data[:10]):
            print(
                f"  [{index}] "
                f"{json.dumps(_safe_compact(item, max_depth=6), sort_keys=True)}"
            )
        if len(data) > 10:
            print(f"  ... {len(data) - 10} more items")
        return
    if isinstance(data, dict):
        print(f"  data: dict keys={', '.join(sorted(str(key) for key in data))}")
        print(json.dumps(_safe_compact(data, max_depth=6), indent=2, sort_keys=True))
        return
    print(f"  data: {type(data).__name__}")


def _safe_compact(value: Any, *, depth: int = 0, max_depth: int = 3) -> Any:
    if depth > max_depth:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            lowered = text_key.lower()
            if (
                lowered in SENSITIVE_KEYS
                or "secret" in lowered
                or lowered.endswith("_sn")
                or lowered in {"sn", "serial", "serial_number"}
            ):
                safe[text_key] = _redacted_value(item)
            elif lowered == "param_value":
                safe[text_key] = _safe_param_value(item, depth=depth + 1)
            else:
                safe[text_key] = _safe_compact(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
        return safe
    if isinstance(value, list):
        return [
            _safe_compact(item, depth=depth + 1, max_depth=max_depth)
            for item in value[:20]
        ]
    if isinstance(value, str) and len(value) > 80:
        return f"<string length={len(value)}>"
    return value


def _safe_param_value(value: Any, *, depth: int) -> Any:
    if not isinstance(value, str):
        return _safe_compact(value, depth=depth, max_depth=6)
    stripped = value.strip()
    if not stripped:
        return value
    if stripped[0] not in "[{":
        if len(value) > 160:
            return f"<string length={len(value)}>"
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return f"<json-like string length={len(value)}>"
    return _safe_compact(parsed, depth=depth, max_depth=6)


def _redacted_value(value: Any) -> str:
    if value is None:
        return "<none>"
    text = str(value)
    return f"<redacted length={len(text)}>"


def _print_redacted_api_data(data: Any) -> None:
    if data is None:
        return
    print(f"Response data type: {type(data).__name__}")
    if isinstance(data, dict):
        keys = ", ".join(sorted(str(key) for key in data))
        print(f"Response data keys: {keys or '<none>'}")


if __name__ == "__main__":
    raise SystemExit(main())
