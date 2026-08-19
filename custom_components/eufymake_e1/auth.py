"""eufyMake cloud authentication helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

from .const import CONF_DEVICE_SN, CONF_EMAIL, CONF_FIRMWARE_VERSION
from .const import CONF_MQTT_HOST, CONF_REGION, CONF_SECRET_KEY, CONF_USER_ID
from .const import REGION_EU, REGION_US, US_REGION_COUNTRIES

APP_VERSION = "4.2.2"
ANKERMAKE_APP_NAME = "anker_make"
ANKERMAKE_PROD_LOCAL_KEY = "c4a8f67abb862469c51d054339d999f5"
PASSPORT_SERVER_PUBLIC_KEY = (
    "04c5c00c4f8d1197cc7c3167c52bf7acb054d722f0ef08dcd7e0883236e0d72a38"
    "68d9750cb47fa4619248f3d83f0f662671dadc6e2d31c2f41db0161651c7c076"
)
APP_KEY_EXCHANGE_PATH = "/v3/pc/oauth/key_exchange"
LOGIN_PATH = "/v2/passport/login"
DEVICE_LIST_PATH = "/v1/app/query_fdm_list"

REGION_ENDPOINTS = {
    "us": {
        "app_domain": "make-app.ankermake.com",
        "mqtt_host": "make-mqtt.ankermake.com",
    },
    "eu": {
        "app_domain": "make-app-eu.ankermake.com",
        "mqtt_host": "make-mqtt-eu.ankermake.com",
    },
}


class EufyMakeAuthError(Exception):
    """Raised when cloud authentication or setup discovery fails."""


class EufyMakeApiCodeError(EufyMakeAuthError):
    """Raised when eufyMake returns a non-success business code."""

    def __init__(self, code: int | None, message: Any, data: Any = None) -> None:
        """Initialize the API code error."""
        self.code = code
        self.message = str(message or "")
        self.data = data
        super().__init__(f"API error: code={code} msg={self.message}")


class EufyMakeCaptchaRequired(EufyMakeApiCodeError):
    """Raised when eufyMake requires captcha verification."""

    def __init__(self, code: int | None, message: Any, data: Any = None) -> None:
        """Initialize the captcha challenge error."""
        super().__init__(code, message, data)
        payload = data if isinstance(data, dict) else {}
        self.captcha_id = str(payload.get("captcha_id") or "")
        self.item = str(payload.get("item") or "")


@dataclass(frozen=True, kw_only=True)
class EufyMakeSession:
    """Authenticated eufyMake cloud session."""

    region: str
    app_domain: str
    mqtt_host: str
    user_id: str
    email: str
    auth_token: str
    token_expires_at: int | None
    entry_id: str
    share_key_hex: str


@dataclass(frozen=True, kw_only=True)
class EufyMakeLoginResult:
    """Cloud login result plus the selected E1 setup fields."""

    session: EufyMakeSession
    devices: tuple[dict[str, Any], ...]


class EufyMakeCloudAuthClient:
    """Minimal eufyMake cloud client for Home Assistant setup."""

    def __init__(
        self,
        *,
        region: str | None = None,
        country: str = "NL",
        timeout: float = 20,
    ) -> None:
        """Initialize a regional auth client."""
        country = country.strip().upper()
        if not region:
            region = region_from_country(country)
        if region not in REGION_ENDPOINTS:
            raise EufyMakeAuthError(f"Unsupported region: {region}")
        self.region = region
        self.timeout = timeout
        self.app_domain = REGION_ENDPOINTS[region]["app_domain"]
        self.mqtt_host = REGION_ENDPOINTS[region]["mqtt_host"]
        self.country = country

    def login(
        self,
        *,
        email: str,
        password: str,
        captcha_id: str | None = None,
        captcha_answer: str | None = None,
    ) -> EufyMakeLoginResult:
        """Log in and fetch E1 devices needed for MQTT setup."""
        normalized_email = email.strip().lower()
        session_key = _perform_key_exchange(
            app_domain=self.app_domain,
            timeout=self.timeout,
        )
        login_body = {
            "email": normalized_email,
            "password": _encrypt_password(password, session_key.private_key),
            "ab": self.country,
            "ab_code": self.country,
            "login_id": "",
            "verify_code": "",
            "captcha_id": captcha_id or "",
            "answer": captcha_answer or "",
            "client_secret_info": {"public_key": session_key.public_key_hex},
        }
        response = _post_encrypted(
            app_domain=self.app_domain,
            path=LOGIN_PATH,
            body=login_body,
            entry_id=session_key.entry_id,
            share_key_hex=session_key.share_key_hex,
            auth_token=None,
            user_id=None,
            timeout=self.timeout,
            country=self.country,
            extra_headers={
                **_desktop_headers(
                    self.country,
                    openudid=hashlib.sha256(normalized_email.encode()).hexdigest(),
                )
            },
        )
        try:
            data = _expect_success(response)
        except EufyMakeApiCodeError as err:
            if _is_captcha_required(err.code, err.data):
                raise EufyMakeCaptchaRequired(err.code, err.message, err.data) from err
            raise
        if not isinstance(data, dict):
            raise EufyMakeAuthError("Login response data is not an object")
        if _requires_verification(data):
            raise EufyMakeApiCodeError(26052, "Verification required", data)

        account_data = dict(data)
        account_data["domain"] = self.app_domain

        auth_token = str(account_data.get("auth_token") or "")
        user_id = str(account_data.get("user_id") or "")
        if not auth_token or not user_id:
            raise EufyMakeAuthError("Login response did not include a token and user ID")

        account_email = _response_email(
            account_data.get("email"),
            account_data,
            session_key.private_key,
        )
        session = EufyMakeSession(
            region=self.region,
            app_domain=self.app_domain,
            mqtt_host=self.mqtt_host,
            user_id=user_id,
            email=account_email or normalized_email,
            auth_token=auth_token,
            token_expires_at=_optional_int(account_data.get("token_expires_at")),
            entry_id=session_key.entry_id,
            share_key_hex=session_key.share_key_hex,
        )
        devices = tuple(_e1_devices(self.get_devices(session)))
        if not devices:
            raise EufyMakeAuthError("No eufyMake E1 devices were found on this account")
        return EufyMakeLoginResult(session=session, devices=devices)

    def get_devices(self, session: EufyMakeSession) -> list[dict[str, Any]]:
        """Fetch all cloud devices for a logged-in session."""
        response = _post_encrypted(
            app_domain=session.app_domain,
            path=DEVICE_LIST_PATH,
            body={},
            entry_id=session.entry_id,
            share_key_hex=session.share_key_hex,
            auth_token=session.auth_token,
            user_id=session.user_id,
            timeout=self.timeout,
            country=self.country,
            extra_headers=_desktop_headers(self.country),
        )
        data = _expect_success(response)
        if not isinstance(data, list):
            raise EufyMakeAuthError("Device list response data is not a list")
        return [item for item in data if isinstance(item, dict)]


@dataclass(frozen=True, kw_only=True)
class _SessionKey:
    entry_id: str
    private_key: Any
    public_key_hex: str
    shared_secret_hex: str
    share_key_hex: str


def build_setup_from_login_device(
    session: EufyMakeSession,
    device: dict[str, Any],
) -> dict[str, Any]:
    """Build Home Assistant config entry data from a logged-in E1 device."""
    serial_number = str(device.get("station_sn") or "")
    secret_key = str(device.get("secret_key") or "")
    if not serial_number or not secret_key:
        raise EufyMakeAuthError("Selected E1 is missing MQTT credentials")
    if str(device.get("station_model") or "") != "V8260":
        raise EufyMakeAuthError("Selected device is not a eufyMake E1")

    data: dict[str, Any] = {
        CONF_REGION: session.region,
        CONF_DEVICE_SN: serial_number,
        CONF_USER_ID: session.user_id,
        CONF_EMAIL: unquote(session.email),
        CONF_SECRET_KEY: secret_key,
        CONF_MQTT_HOST: session.mqtt_host,
    }
    if device.get("main_sw_version"):
        data[CONF_FIRMWARE_VERSION] = str(device["main_sw_version"])
    return data


def region_from_country(country: str) -> str:
    """Return the eufyMake backend region for a country code."""
    return REGION_US if country.strip().upper() in US_REGION_COUNTRIES else REGION_EU


def _perform_key_exchange(
    *,
    app_domain: str,
    timeout: float,
    path: str = APP_KEY_EXCHANGE_PATH,
    app_name: str = ANKERMAKE_APP_NAME,
    model_type: str = "WEB",
    app_name_header: str = "App_name",
    model_type_header: str = "Model-Type",
    local_key_hex: str = ANKERMAKE_PROD_LOCAL_KEY,
) -> _SessionKey:
    private_key, public_key_hex = _generate_ecdh_key_pair()
    encrypted_public_key = _aes_cbc_encrypt_with_random_iv(
        public_key_hex.encode("utf-8"),
        bytes.fromhex(local_key_hex),
    )
    encrypted_public_key_b64 = base64.b64encode(encrypted_public_key).decode("ascii")
    entry_id = secrets.token_hex(16)
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    signature = _hmac_sha256_hex(
        local_key_hex.encode("utf-8"),
        f"{timestamp}+{nonce}+{encrypted_public_key_b64}",
    )
    response = _post_plain(
        app_domain=app_domain,
        path=path,
        body={"client_public_key": encrypted_public_key_b64},
        headers={
            "content-type": "application/json",
            model_type_header: model_type,
            app_name_header: app_name,
            "X-Key-Ident": entry_id,
            "X-Request-Ts": timestamp,
            "X-Request-Once": nonce,
            "X-Signature": signature,
            "X-Encryption-Info": "algo_ecdh",
        },
        timeout=timeout,
    )
    data = _expect_success(response)
    if not isinstance(data, dict) or not data.get("server_public_key"):
        raise EufyMakeAuthError("Key exchange response is missing server public key")
    server_public_key = _aes_cbc_decrypt_with_prepended_iv(
        base64.b64decode(str(data["server_public_key"])),
        bytes.fromhex(local_key_hex),
    ).decode("utf-8")
    shared_secret = private_key.exchange(
        _ecdh_algorithm(),
        _public_key_from_hex(server_public_key),
    )
    shared_secret_hex = shared_secret.hex().rjust(64, "0")
    return _SessionKey(
        entry_id=entry_id,
        private_key=private_key,
        public_key_hex=public_key_hex,
        shared_secret_hex=shared_secret_hex,
        share_key_hex=shared_secret_hex[:32],
    )


def _post_encrypted(
    *,
    app_domain: str,
    path: str,
    body: dict[str, Any],
    entry_id: str,
    share_key_hex: str,
    auth_token: str | None,
    user_id: str | None,
    timeout: float,
    app_name: str = ANKERMAKE_APP_NAME,
    model_type: str = "PC",
    country: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    key = bytes.fromhex(share_key_hex)
    encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    encrypted_body = _aes_cbc_encrypt_with_random_iv(encoded_body, key)
    encrypted_body_b64 = base64.b64encode(encrypted_body).decode("ascii")
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    headers = {
        "content-type": "application/json",
        "app-name": app_name,
        "App-version": APP_VERSION,
        "model-type": model_type,
        "language": "en",
        "Accept": "application/json",
        "User-Agent": f"eufyMake Studio/{APP_VERSION}",
        "X-Key-Ident": entry_id,
        "X-Request-Ts": timestamp,
        "X-Request-Once": nonce,
        "X-Signature": _hmac_sha256_hex(
            share_key_hex.encode("utf-8"),
            f"{timestamp}+{nonce}+{encrypted_body_b64}",
        ),
        "X-Encryption-Info": "algo_ecdh",
        "X-Replay-Info": "replay",
    }
    if country:
        headers["country"] = country
    if extra_headers:
        headers.update(extra_headers)
    if auth_token:
        headers["X-Auth-Token"] = auth_token
        headers["Gtoken"] = hashlib.md5((user_id or "").encode()).hexdigest()

    response = _post_plain(
        app_domain=app_domain,
        path=path,
        body_text=encrypted_body_b64,
        headers=headers,
        timeout=timeout,
    )
    data = response.get("data")
    if isinstance(data, str):
        decrypted = _aes_cbc_decrypt_with_prepended_iv(base64.b64decode(data), key)
        try:
            response["data"] = json.loads(decrypted.decode("utf-8").rstrip("\x00"))
        except json.JSONDecodeError as err:
            raise EufyMakeAuthError("Encrypted response data is not JSON") from err
    return response


def _post_plain(
    *,
    app_domain: str,
    path: str,
    headers: dict[str, str],
    timeout: float,
    body: dict[str, Any] | None = None,
    body_text: str | None = None,
) -> dict[str, Any]:
    if body_text is None:
        body_text = json.dumps(body or {}, separators=(",", ":"))
    request = Request(
        f"https://{app_domain}{path}",
        data=body_text.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as err:
        decoded_error = _decode_body(err.read())
        raise EufyMakeAuthError(
            f"HTTP {err.code} from {path}: {decoded_error!r}"
        ) from err
    except URLError as err:
        raise EufyMakeAuthError(f"Request to {path} failed: {err.reason}") from err
    decoded = _decode_body(raw)
    if not isinstance(decoded, dict):
        raise EufyMakeAuthError(f"Unexpected response from {path}: {decoded!r}")
    return decoded


def _expect_success(response: dict[str, Any]) -> Any:
    if response.get("code") in (0, 200):
        return response.get("data")
    raise EufyMakeApiCodeError(
        _optional_int(response.get("code")),
        response.get("msg"),
        response.get("data"),
    )


def _requires_verification(data: dict[str, Any]) -> bool:
    fa_info = data.get("fa_info")
    return isinstance(fa_info, dict) and _optional_int(fa_info.get("step")) == 26052


def _is_captcha_required(code: int | None, data: Any) -> bool:
    return (
        code in (100032, 100033)
        and isinstance(data, dict)
        and bool(data.get("captcha_id"))
        and bool(data.get("item"))
    )


def _desktop_headers(country: str, *, openudid: str | None = None) -> dict[str, str]:
    return {
        "App_name": ANKERMAKE_APP_NAME,
        "App_version": "14",
        "Country": country,
        "Language": "en",
        "Model_type": "PC",
        "Openudid": openudid or secrets.token_hex(16),
        "Os_type": "Windows",
        "Os_version": "10",
    }


def _decode_body(value: bytes) -> dict[str, Any] | str | None:
    if not value:
        return None
    text = value.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text[:500]


def _e1_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        device
        for device in devices
        if str(device.get("station_model") or "") == "V8260"
    ]


def _response_email(
    value: Any,
    login_data: dict[str, Any],
    private_key: Any,
) -> str | None:
    if not value:
        return None
    text = str(value)
    try:
        server_secret_info = login_data.get("server_secret_info")
        if isinstance(server_secret_info, dict) and server_secret_info.get("public_key"):
            public_key_hex = str(server_secret_info["public_key"])
        else:
            public_key_hex = PASSPORT_SERVER_PUBLIC_KEY
        secret = private_key.exchange(
            _ecdh_algorithm(),
            _public_key_from_hex(public_key_hex),
        )
        return _aes_cbc_decrypt(
            base64.b64decode(text),
            secret,
            secret[:16],
        ).decode("utf-8").rstrip("\x00")
    except Exception:
        return unquote(text)


def _encrypt_password(password: str, private_key: Any) -> str:
    secret = private_key.exchange(
        _ecdh_algorithm(),
        _public_key_from_hex(PASSPORT_SERVER_PUBLIC_KEY),
    )
    ciphertext = _aes_cbc_encrypt(password.encode("utf-8"), secret, secret[:16])
    return base64.b64encode(ciphertext).decode("ascii")


def _aes_cbc_encrypt_with_random_iv(plaintext: bytes, key: bytes) -> bytes:
    iv = secrets.token_bytes(16)
    return iv + _aes_cbc_encrypt(plaintext, key, iv)


def _aes_cbc_decrypt_with_prepended_iv(ciphertext: bytes, key: bytes) -> bytes:
    if len(ciphertext) < 32 or len(ciphertext) % 16 != 0:
        raise EufyMakeAuthError("Invalid AES-CBC payload")
    return _aes_cbc_decrypt(ciphertext[16:], key, ciphertext[:16])


def _aes_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _aes_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _hmac_sha256_hex(key: bytes, message: str) -> str:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _generate_ecdh_key_pair() -> tuple[Any, str]:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_bytes = private_key.public_key().public_bytes(
        Encoding.X962,
        PublicFormat.UncompressedPoint,
    )
    return private_key, public_bytes.hex()


def _public_key_from_hex(value: str) -> Any:
    from cryptography.hazmat.primitives.asymmetric import ec

    return ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(),
        bytes.fromhex(value),
    )


def _ecdh_algorithm() -> Any:
    from cryptography.hazmat.primitives.asymmetric import ec

    return ec.ECDH()


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
