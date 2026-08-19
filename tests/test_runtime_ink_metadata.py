import importlib.util
import sys
from pathlib import Path


RUNTIME = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "eufymake_e1"
    / "runtime.py"
)


def test_runtime_ink_status_includes_expiry_metadata() -> None:
    runtime = _load_runtime()
    status = runtime.find_ink_status(_ink_status_message())

    assert status is not None
    assert status.channels[0].channel == "C"
    assert status.channels[0].remaining_percent == 78.2
    assert status.channels[0].manufacture_timestamp == 1756396800
    assert status.channels[0].expiration_timestamp == 1787932800
    assert status.channels[0].distance_expiration_days == 10
    assert status.channels[0].expired is False
    assert status.channels[1].expired is True
    assert status.waste_tank is not None
    assert status.waste_tank.expiration_timestamp == 1803657600
    assert status.waste_tank.distance_expiration_days == 192


def _load_runtime():
    spec = importlib.util.spec_from_file_location("runtime_under_test", RUNTIME)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["runtime_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _ink_status_message() -> dict:
    return {
        "commandType": 1100,
        "ink": {
            "count": 2,
            "colorSort": ["C", "K"],
            "leftInk": [7820, 7418],
            "status": [1, 2],
            "manufactureTime": [1756396800, 1753804800],
            "expirationTimestamp": [1787932800, 1785340800],
            "distanceExpiration": [10, 0],
            "expired": [0, 1],
        },
        "wasteInk": {
            "leftInk": [2000],
            "status": [1],
            "expirationTimestamp": [1803657600],
            "distanceExpiration": [192],
            "expired": [0],
        },
    }
