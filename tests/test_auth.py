import importlib.util
import sys
import types
from pathlib import Path


COMPONENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "eufymake_e1"
)


def test_build_setup_from_login_device() -> None:
    module = _load_auth_module()
    session = module.EufyMakeSession(
        region="eu",
        app_domain="make-app-eu.ankermake.com",
        mqtt_host="make-mqtt-eu.ankermake.com",
        user_id="fixture-user",
        email="fixture%40example.com",
        auth_token="fixture-token",
        token_expires_at=1893456000,
        entry_id="fixture-entry",
        share_key_hex="000102030405060708090a0b0c0d0e0f",
    )

    setup = module.build_setup_from_login_device(
        session,
        {
            "station_sn": "AKTESTE100000001",
            "station_model": "V8260",
            "secret_key": "fixture-secret",
            "main_sw_version": "4.0.2",
        },
    )

    assert setup == {
        "region": "eu",
        "device_sn": "AKTESTE100000001",
        "user_id": "fixture-user",
        "email": "fixture@example.com",
        "secret_key": "fixture-secret",
        "mqtt_host": "make-mqtt-eu.ankermake.com",
        "firmware_version": "4.0.2",
    }


def test_build_setup_from_login_device_rejects_non_e1() -> None:
    module = _load_auth_module()
    session = module.EufyMakeSession(
        region="eu",
        app_domain="make-app-eu.ankermake.com",
        mqtt_host="make-mqtt-eu.ankermake.com",
        user_id="fixture-user",
        email="fixture@example.com",
        auth_token="fixture-token",
        token_expires_at=None,
        entry_id="fixture-entry",
        share_key_hex="000102030405060708090a0b0c0d0e0f",
    )

    try:
        module.build_setup_from_login_device(
            session,
            {
                "station_sn": "AKTESTM500000001",
                "station_model": "V8111",
                "secret_key": "fixture-secret",
            },
        )
    except module.EufyMakeAuthError:
        return

    raise AssertionError("Expected non-E1 setup to be rejected")


def test_aes_cbc_prepended_iv_roundtrip() -> None:
    module = _load_auth_module()
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    plaintext = b'{"fixture":true}'

    ciphertext = module._aes_cbc_encrypt_with_random_iv(plaintext, key)

    assert ciphertext != plaintext
    assert module._aes_cbc_decrypt_with_prepended_iv(ciphertext, key) == plaintext


def test_login_uses_printer_api_endpoint() -> None:
    module = _load_auth_module()

    assert module.APP_KEY_EXCHANGE_PATH == "/v3/pc/oauth/key_exchange"
    assert module.LOGIN_PATH == "/v2/passport/login"


def test_country_routes_to_expected_region() -> None:
    module = _load_auth_module()

    assert module.region_from_country("NL") == "eu"
    assert module.region_from_country("DE") == "eu"
    assert module.region_from_country("US") == "us"
    assert module.region_from_country("ca") == "us"


def test_printer_api_domains_are_configured() -> None:
    module = _load_auth_module()

    assert module.REGION_ENDPOINTS["eu"]["app_domain"] == "make-app-eu.ankermake.com"
    assert module.REGION_ENDPOINTS["us"]["app_domain"] == "make-app.ankermake.com"


def test_desktop_headers_use_native_shape() -> None:
    module = _load_auth_module()

    headers = module._desktop_headers("NL", openudid="fixture-openudid")

    assert headers["App_name"] == "anker_make"
    assert headers["Model_type"] == "PC"
    assert headers["Country"] == "NL"
    assert headers["Openudid"] == "fixture-openudid"


def _load_auth_module():
    package = types.ModuleType("custom_components.eufymake_e1")
    package.__path__ = [str(COMPONENT_DIR)]
    sys.modules["custom_components.eufymake_e1"] = package
    sys.modules["custom_components.eufymake_e1.const"] = _load_module(
        "custom_components.eufymake_e1.const",
        COMPONENT_DIR / "const.py",
    )
    return _load_module(
        "custom_components.eufymake_e1.auth",
        COMPONENT_DIR / "auth.py",
    )


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
