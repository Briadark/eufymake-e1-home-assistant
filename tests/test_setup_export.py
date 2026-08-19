import json
from pathlib import Path

from pyeufymake.setup_export import (
    EufyMakeSetupExportError,
    build_setup_export,
    parse_setup_export,
)


FIXTURE_CACHE = Path(__file__).parent / "fixtures" / "cache"
FIXTURE_PROFILE = Path(__file__).parent / "fixtures" / "profile"


def test_build_setup_export_from_cache() -> None:
    setup_export = build_setup_export(FIXTURE_PROFILE, FIXTURE_CACHE)

    assert setup_export["version"] == 1
    assert setup_export["region"] == "eu"
    assert setup_export["device_sn"] == "AKTESTE100000001"
    assert setup_export["user_id"] == "fixture-user"
    assert setup_export["mqtt_host"] == "make-mqtt-eu.ankermake.com"
    assert setup_export["station_model"] == "V8260"


def test_parse_setup_export() -> None:
    setup_export = build_setup_export(FIXTURE_PROFILE, FIXTURE_CACHE)

    parsed = parse_setup_export(json.dumps(setup_export))

    assert parsed == {
        "region": "eu",
        "device_sn": "AKTESTE100000001",
        "user_id": "fixture-user",
        "email": "fixture@example.com",
        "secret_key": (
            "000102030405060708090a0b0c0d0e0f"
            "101112131415161718191a1b1c1d1e1f"
        ),
        "mqtt_host": "make-mqtt-eu.ankermake.com",
        "firmware_version": "4.0.2",
    }


def test_parse_setup_export_rejects_non_e1() -> None:
    setup_export = build_setup_export(FIXTURE_PROFILE, FIXTURE_CACHE)
    setup_export["station_model"] = "V8111"

    try:
        parse_setup_export(setup_export)
    except EufyMakeSetupExportError:
        return

    raise AssertionError("Expected non-E1 setup export to be rejected")
