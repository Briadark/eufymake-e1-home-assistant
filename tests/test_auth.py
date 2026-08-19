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
