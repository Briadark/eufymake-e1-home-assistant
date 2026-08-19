from pathlib import Path

from pyeufymake import EufyMakeProfileCacheStore


FIXTURE_PROFILE = Path(__file__).parent / "fixtures" / "profile"


def test_load_cached_login() -> None:
    login = EufyMakeProfileCacheStore(FIXTURE_PROFILE).load_login()

    assert login.user_id == "fixture-user"
    assert login.email == "fixture@example.com"
    assert login.auth_token == "fixture-token"
    assert login.token_expires_at == 1893456000
    assert login.app_domain == "make-app-eu.ankermake.com"
    assert login.make_it_real_domain == "aiot-api-eu.ankermake.com"
    assert login.country_code == "NL"
    assert login.geo_key == "fixture-geo-key"
    assert login.test_flag == "1"
