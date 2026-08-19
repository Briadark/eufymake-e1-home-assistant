"""Probe eufyMake account login without printing secrets."""

from __future__ import annotations

import getpass
import importlib.util
import sys
from pathlib import Path


def main() -> int:
    """Run an interactive, redacted login probe."""
    auth = _load_auth_module()
    country = input("Country code (default NL): ").strip().upper() or "NL"
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    try:
        result = auth.EufyMakeCloudAuthClient(country=country).login(
            email=email,
            password=password,
        )
    except auth.EufyMakeApiCodeError as err:
        print(f"Login API error: code={err.code} msg={err.message}")
        _print_redacted_api_data(err.data)
        return 2
    except auth.EufyMakeAuthError as err:
        print(f"Login failed: {err}")
        return 2

    print("Login ok.")
    print(f"E1 devices: {len(result.devices)}")
    for device in result.devices:
        serial_number = str(device.get("station_sn") or "")
        suffix = serial_number[-4:] if len(serial_number) >= 4 else "<unknown>"
        firmware = device.get("main_sw_version") or "<unknown>"
        print(f"  eufyMake E1 ...{suffix} firmware={firmware}")
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


def _print_redacted_api_data(data) -> None:
    """Print response shape without exposing tokens or identifiers."""
    if data is None:
        return
    print(f"Response data type: {type(data).__name__}")
    if isinstance(data, dict):
        keys = ", ".join(sorted(str(key) for key in data))
        print(f"Response data keys: {keys or '<none>'}")
        for key in sorted(str(key) for key in data):
            value = data.get(key)
            if isinstance(value, (dict, list, tuple)):
                print(f"  {key}: {type(value).__name__} size={len(value)}")
            elif isinstance(value, str):
                print(f"  {key}: string length={len(value)}")
            else:
                print(f"  {key}: {type(value).__name__}")
    elif isinstance(data, (list, tuple)):
        print(f"Response data length: {len(data)}")


if __name__ == "__main__":
    raise SystemExit(main())
