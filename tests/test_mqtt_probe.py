from pathlib import Path

from pyeufymake.mqtt_probe import build_probe_plan


FIXTURE_CACHE = Path(__file__).parent / "fixtures" / "cache"
FIXTURE_PROFILE = Path(__file__).parent / "fixtures" / "profile"


def test_build_probe_plan_from_cache() -> None:
    plan = build_probe_plan(FIXTURE_PROFILE, FIXTURE_CACHE)

    assert plan.host == "make-mqtt-eu.ankermake.com"
    assert plan.port == 8789
    assert plan.device.station_model == "V8260"
    assert plan.credentials.username == "eufy_fixture-user"
    assert plan.topics.query == "/device/maker/AKTESTE100000001/query"
    assert plan.has_secret_key is True
