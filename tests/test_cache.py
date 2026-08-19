from pathlib import Path

from pyeufymake import EufyMakeCacheStore


FIXTURE_CACHE = Path(__file__).parent / "fixtures" / "cache"


def test_load_e1_snapshot_from_cache() -> None:
    snapshot = EufyMakeCacheStore(FIXTURE_CACHE).load_snapshot()

    assert snapshot.device.serial_number == "AKTESTE100000001"
    assert (
        snapshot.device.secret_key
        == "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    )
    assert snapshot.device.station_model == "V8260"
    assert snapshot.device.firmware_version == "4.0.2"
    assert snapshot.device.is_online is True
    assert snapshot.device.params == {10028: "1", 10029: "0"}
    assert snapshot.dsk_available is True
    assert snapshot.white_ink_enabled is False
    assert len(snapshot.parts) == 1
    assert snapshot.parts[0].remaining_percent == 55


def test_load_snapshot_by_serial_number() -> None:
    snapshot = EufyMakeCacheStore(FIXTURE_CACHE).load_snapshot("AKTESTE100000001")

    assert snapshot.device.product_name == "eufyMake E1"
