from pyeufymake.cloud import EufyMakeCloudClient, EufyMakeCloudProbeError
from pyeufymake.profile import CachedLogin


def test_cloud_client_requires_auth_token() -> None:
    login = CachedLogin(
        user_id="fixture-user",
        email="fixture@example.com",
        auth_token="",
        token_expires_at=None,
        app_domain="make-app-eu.ankermake.com",
        make_it_real_domain="aiot-api-eu.ankermake.com",
        country_code="NL",
        geo_key=None,
        test_flag="1",
    )

    try:
        EufyMakeCloudClient(login)
    except EufyMakeCloudProbeError:
        pass
    else:
        raise AssertionError("Expected EufyMakeCloudProbeError")
