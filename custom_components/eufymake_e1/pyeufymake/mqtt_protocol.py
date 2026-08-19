"""MQTT protocol helpers for eufyMake E1 devices."""

from __future__ import annotations

import json
import secrets
import struct
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

from .profile import CachedLogin

MQTT_PORT = 8789
MQTT_USERNAME_PREFIX = "eufy_"
MQTT_CLIENT_ID_PREFIX = "pc_windows_AnkerMakeStudio_direct"

FIXED_IV = b"3DPrintAnkerMake"
GCM_FIXED_NONCE = b"3DPrintAnker"
APP_HEADER_SIZE = 64
DEVICE_HEADER_SIZE = 24
PACKET_TYPE_SINGLE = 0xC0

STATUS_QUERY_COMMAND = {"commandType": 1027, "value": 0}


class EufyMakeMqttProtocolError(Exception):
    """Raised when an MQTT protocol frame cannot be built or parsed."""


@dataclass(frozen=True, kw_only=True)
class MqttCredentials:
    """MQTT credentials derived from cached eufyMake account metadata."""

    username: str
    password: str
    client_id: str


@dataclass(frozen=True, kw_only=True)
class MqttTopics:
    """MQTT topics used for one eufyMake E1 device."""

    notice: str
    command_reply: str
    query_reply: str
    maker_change_notice: str
    user_change_notice: str
    command: str
    query: str

    @property
    def subscriptions(self) -> tuple[str, ...]:
        """Return the exact non-wildcard topics to subscribe to."""
        return (
            self.notice,
            self.command_reply,
            self.query_reply,
            self.maker_change_notice,
            self.user_change_notice,
        )


@dataclass(frozen=True, kw_only=True)
class MqttFrame:
    """A validated MQTT binary frame."""

    magic: bytes
    total_size: int
    header_size: int
    packet_type: int
    packet_num: int
    ciphertext: bytes
    checksum: int


@dataclass(frozen=True, kw_only=True)
class MqttGcmPayload:
    """A validated length/tag/ciphertext MQTT payload variant."""

    declared_size: int
    tag: bytes
    ciphertext: bytes


def build_credentials(login: CachedLogin) -> MqttCredentials:
    """Build MQTT CONNECT credentials from cached login metadata."""
    if not login.user_id:
        raise EufyMakeMqttProtocolError("Cached login has no user id")
    if not login.email:
        raise EufyMakeMqttProtocolError("Cached login has no email")

    return MqttCredentials(
        username=f"{MQTT_USERNAME_PREFIX}{login.user_id}",
        password=unquote(login.email),
        client_id=build_client_id(login.user_id),
    )


def resolve_mqtt_host(login: CachedLogin) -> str:
    """Resolve the MQTT host from cached region/domain metadata."""
    candidates = (
        login.app_domain,
        login.make_it_real_domain,
        login.country_code,
    )
    if any(_contains_eu(value) for value in candidates):
        return "make-mqtt-eu.ankermake.com"
    return "make-mqtt.ankermake.com"


def build_client_id(user_id: str) -> str:
    """Build a desktop-style MQTT client id."""
    random_hex = secrets.token_hex(6)
    timestamp_ms = int(time.time() * 1000)
    return (
        f"{MQTT_CLIENT_ID_PREFIX}_{user_id}_{random_hex}_{timestamp_ms}"
    )


def build_topics(station_sn: str, user_id: str) -> MqttTopics:
    """Build exact MQTT topics for a station/user pair."""
    if not station_sn:
        raise EufyMakeMqttProtocolError("Station serial number is required")
    if not user_id:
        raise EufyMakeMqttProtocolError("User id is required")

    return MqttTopics(
        notice=f"/phone/maker/{station_sn}/notice",
        command_reply=f"/phone/maker/{station_sn}/command/reply",
        query_reply=f"/phone/maker/{station_sn}/query/reply",
        maker_change_notice=f"/phone/maker/{station_sn}/change_notice",
        user_change_notice=f"/phone/user/{user_id}/change_notice",
        command=f"/device/maker/{station_sn}/command",
        query=f"/device/maker/{station_sn}/query",
    )


def build_status_query() -> dict[str, int]:
    """Return the command payload that asks the printer to publish status."""
    return dict(STATUS_QUERY_COMMAND)


def build_app_frame(
    payload: dict[str, Any],
    secret_key_hex: str,
    *,
    device_guid: str | None = None,
) -> bytes:
    """Encrypt a JSON payload and wrap it in an app-to-printer MQTT frame."""
    ciphertext = encrypt_json_payload(payload, secret_key_hex)
    guid = _device_guid_bytes(device_guid)
    header = bytearray(APP_HEADER_SIZE)
    total_size = len(header) + len(ciphertext) + 1
    if total_size > 0xFFFF:
        raise EufyMakeMqttProtocolError("Payload is too large for MA frame")

    header[0:2] = b"MA"
    struct.pack_into("<H", header, 2, total_size)
    header[4] = 0x05
    header[5] = 0x01
    header[6] = 0x02
    header[7] = 0x05
    header[8] = 0x46
    header[9] = PACKET_TYPE_SINGLE
    struct.pack_into("<H", header, 10, 0)
    header[16:53] = guid

    frame_without_checksum = bytes(header) + ciphertext
    return frame_without_checksum + bytes([xor_checksum(frame_without_checksum)])


def build_gcm_payload(payload: dict[str, Any], secret_key_hex: str) -> bytes:
    """Encrypt a JSON payload in the alternate GCM MQTT payload shape."""
    ciphertext, tag = encrypt_json_gcm_payload(payload, secret_key_hex)
    return struct.pack(">I", len(ciphertext)) + tag + ciphertext


def parse_frame(frame: bytes) -> MqttFrame:
    """Validate and split an encrypted MQTT frame without decrypting it."""
    if len(frame) < DEVICE_HEADER_SIZE + 1:
        raise EufyMakeMqttProtocolError("Frame is too short")
    if frame[:2] != b"MA":
        raise EufyMakeMqttProtocolError("Only MA frames are currently supported")

    total_size = struct.unpack_from("<H", frame, 2)[0]
    if total_size != len(frame):
        raise EufyMakeMqttProtocolError(
            f"Frame size mismatch: expected {total_size}, got {len(frame)}"
        )

    expected_checksum = xor_checksum(frame[:-1])
    actual_checksum = frame[-1]
    if actual_checksum != expected_checksum:
        raise EufyMakeMqttProtocolError("Frame checksum mismatch")

    header_size = _header_size_from_m5(frame[6])
    ciphertext = frame[header_size:-1]
    if len(ciphertext) == 0 or len(ciphertext) % 16 != 0:
        raise EufyMakeMqttProtocolError("Frame ciphertext has invalid length")

    return MqttFrame(
        magic=frame[:2],
        total_size=total_size,
        header_size=header_size,
        packet_type=frame[9],
        packet_num=struct.unpack_from("<H", frame, 10)[0],
        ciphertext=ciphertext,
        checksum=actual_checksum,
    )


def decrypt_json_frame(frame: bytes, secret_key_hex: str) -> Any:
    """Decrypt an MQTT frame and parse its JSON payload."""
    parsed = parse_frame(frame)
    plaintext = decrypt_payload(parsed.ciphertext, secret_key_hex)
    return parse_json_payload(plaintext)


def parse_gcm_payload(payload: bytes) -> MqttGcmPayload:
    """Validate the alternate length/tag/ciphertext MQTT payload shape."""
    if len(payload) < 21:
        raise EufyMakeMqttProtocolError("GCM payload is too short")

    declared_size = struct.unpack_from(">I", payload, 0)[0]
    tag = payload[4:20]
    ciphertext = payload[20:]
    allowed_sizes = {
        len(payload),
        len(payload) - 4,
        len(tag) + len(ciphertext),
        len(ciphertext),
    }
    if declared_size not in allowed_sizes:
        raise EufyMakeMqttProtocolError(
            f"GCM payload size mismatch: declared {declared_size}, "
            f"got {len(payload)}"
        )

    return MqttGcmPayload(
        declared_size=declared_size,
        tag=tag,
        ciphertext=ciphertext,
    )


def decrypt_json_gcm_payload(payload: bytes, secret_key_hex: str) -> Any:
    """Decrypt the alternate GCM MQTT payload shape and parse JSON."""
    parsed = parse_gcm_payload(payload)
    plaintext = decrypt_gcm_payload(
        parsed.ciphertext,
        parsed.tag,
        secret_key_hex,
    )
    return parse_json_payload(plaintext)


def parse_json_payload(plaintext: bytes) -> Any:
    """Parse decrypted JSON payload bytes."""
    try:
        return json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise EufyMakeMqttProtocolError("Frame payload is not JSON") from err


def encrypt_json_payload(payload: dict[str, Any], secret_key_hex: str) -> bytes:
    """Serialize and encrypt a JSON payload."""
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return encrypt_payload(plaintext, secret_key_hex)


def encrypt_json_gcm_payload(
    payload: dict[str, Any],
    secret_key_hex: str,
) -> tuple[bytes, bytes]:
    """Serialize and encrypt a JSON payload with the alternate AES-GCM key."""
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return encrypt_gcm_payload(plaintext, secret_key_hex)


def encrypt_payload(plaintext: bytes, secret_key_hex: str) -> bytes:
    """Encrypt payload bytes with the eufyMake AES-CBC frame key."""
    key = _secret_key_bytes(secret_key_hex)
    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as err:
        raise EufyMakeMqttProtocolError(
            "cryptography is required for MQTT payload encryption"
        ) from err

    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(FIXED_IV)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def decrypt_payload(ciphertext: bytes, secret_key_hex: str) -> bytes:
    """Decrypt payload bytes with the eufyMake AES-CBC frame key."""
    key = _secret_key_bytes(secret_key_hex)
    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as err:
        raise EufyMakeMqttProtocolError(
            "cryptography is required for MQTT payload decryption"
        ) from err

    decryptor = Cipher(algorithms.AES(key), modes.CBC(FIXED_IV)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def encrypt_gcm_payload(plaintext: bytes, secret_key_hex: str) -> tuple[bytes, bytes]:
    """Encrypt payload bytes with the alternate AES-GCM frame key."""
    key = _secret_key_bytes(secret_key_hex)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as err:
        raise EufyMakeMqttProtocolError(
            "cryptography is required for MQTT payload encryption"
        ) from err

    encrypted = AESGCM(key).encrypt(GCM_FIXED_NONCE, plaintext, None)
    return encrypted[:-16], encrypted[-16:]


def decrypt_gcm_payload(
    ciphertext: bytes,
    tag: bytes,
    secret_key_hex: str,
) -> bytes:
    """Decrypt payload bytes with the alternate AES-GCM frame key."""
    key = _secret_key_bytes(secret_key_hex)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as err:
        raise EufyMakeMqttProtocolError(
            "cryptography is required for MQTT payload decryption"
        ) from err

    return AESGCM(key).decrypt(GCM_FIXED_NONCE, ciphertext + tag, None)


def xor_checksum(data: bytes) -> int:
    """Return the one-byte XOR checksum used by MQTT frames."""
    checksum = 0
    for item in data:
        checksum ^= item
    return checksum


def _secret_key_bytes(secret_key_hex: str) -> bytes:
    try:
        key = bytes.fromhex(secret_key_hex)
    except ValueError as err:
        raise EufyMakeMqttProtocolError("Secret key must be hex encoded") from err
    if len(key) != 32:
        raise EufyMakeMqttProtocolError("Secret key must decode to 32 bytes")
    return key


def _device_guid_bytes(device_guid: str | None) -> bytes:
    text = device_guid or str(uuid4())
    encoded = text.encode("ascii")
    if len(encoded) > 36:
        raise EufyMakeMqttProtocolError("Device GUID is too long")
    return encoded.ljust(37, b"\x00")


def _header_size_from_m5(m5: int) -> int:
    if m5 == 0x02:
        return APP_HEADER_SIZE
    if m5 == 0x06:
        return DEVICE_HEADER_SIZE
    raise EufyMakeMqttProtocolError(f"Unsupported frame M5 byte: {m5:#x}")


def _contains_eu(value: str | None) -> bool:
    if value is None:
        return False
    lowered = value.lower()
    return lowered == "eu" or "-eu" in lowered or lowered.endswith(".eu")
