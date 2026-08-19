from pyeufymake.mqtt_protocol import (
    APP_HEADER_SIZE,
    DEVICE_HEADER_SIZE,
    EufyMakeMqttProtocolError,
    build_credentials,
    build_status_query,
    build_topics,
    parse_frame,
    parse_gcm_payload,
    resolve_mqtt_host,
    xor_checksum,
)
from pyeufymake.profile import CachedLogin


def test_build_topics() -> None:
    topics = build_topics("AKTESTE100000001", "user-123")

    assert topics.notice == "/phone/maker/AKTESTE100000001/notice"
    assert topics.command == "/device/maker/AKTESTE100000001/command"
    assert topics.query == "/device/maker/AKTESTE100000001/query"
    assert topics.subscriptions == (
        "/phone/maker/AKTESTE100000001/notice",
        "/phone/maker/AKTESTE100000001/command/reply",
        "/phone/maker/AKTESTE100000001/query/reply",
        "/phone/maker/AKTESTE100000001/change_notice",
        "/phone/user/user-123/change_notice",
    )


def test_build_credentials() -> None:
    login = CachedLogin(
        user_id="user-123",
        email="fixture%2Bencoded@example.com",
        auth_token="fixture-token",
        token_expires_at=None,
        app_domain="make-app-eu.ankermake.com",
        make_it_real_domain="aiot-api-eu.ankermake.com",
        country_code="NL",
        geo_key=None,
        test_flag="1",
    )

    credentials = build_credentials(login)

    assert credentials.username == "eufy_user-123"
    assert credentials.password == "fixture+encoded@example.com"
    assert credentials.client_id.startswith(
        "pc_windows_AnkerMakeStudio_direct_user-123_"
    )


def test_resolve_mqtt_host_for_eu_login() -> None:
    login = _login(country_code="NL", app_domain="make-app-eu.ankermake.com")

    assert resolve_mqtt_host(login) == "make-mqtt-eu.ankermake.com"


def test_resolve_mqtt_host_defaults_to_us() -> None:
    login = _login(country_code="US", app_domain="make-app.ankermake.com")

    assert resolve_mqtt_host(login) == "make-mqtt.ankermake.com"


def test_status_query_payload() -> None:
    assert build_status_query() == {"commandType": 1027, "value": 0}


def test_xor_checksum() -> None:
    assert xor_checksum(b"") == 0
    assert xor_checksum(bytes([0x01, 0x02, 0x03])) == 0
    assert xor_checksum(b"MA") == (ord("M") ^ ord("A"))


def test_parse_device_frame_without_decrypting() -> None:
    ciphertext = b"\x10" * 16
    frame_without_checksum = _frame_header(DEVICE_HEADER_SIZE, 0x06) + ciphertext
    frame = frame_without_checksum + bytes([xor_checksum(frame_without_checksum)])

    parsed = parse_frame(frame)

    assert parsed.total_size == len(frame)
    assert parsed.header_size == DEVICE_HEADER_SIZE
    assert parsed.packet_type == 0xC0
    assert parsed.packet_num == 7
    assert parsed.ciphertext == ciphertext


def test_parse_app_frame_without_decrypting() -> None:
    ciphertext = b"\x20" * 16
    frame_without_checksum = _frame_header(APP_HEADER_SIZE, 0x02) + ciphertext
    frame = frame_without_checksum + bytes([xor_checksum(frame_without_checksum)])

    parsed = parse_frame(frame)

    assert parsed.header_size == APP_HEADER_SIZE
    assert parsed.ciphertext == ciphertext


def test_parse_rejects_bad_checksum() -> None:
    ciphertext = b"\x10" * 16
    frame_without_checksum = _frame_header(DEVICE_HEADER_SIZE, 0x06) + ciphertext
    frame = frame_without_checksum + b"\x00"

    try:
        parse_frame(frame)
    except EufyMakeMqttProtocolError:
        pass
    else:
        raise AssertionError("Expected checksum failure")


def test_parse_gcm_payload_accepts_declared_ciphertext_size() -> None:
    tag = b"\x01" * 16
    ciphertext = b'{"commandType":1100}'
    declared_size = len(ciphertext).to_bytes(4, "big")

    parsed = parse_gcm_payload(declared_size + tag + ciphertext)

    assert parsed.declared_size == len(ciphertext)
    assert parsed.tag == tag
    assert parsed.ciphertext == ciphertext


def test_parse_gcm_payload_rejects_bad_size() -> None:
    tag = b"\x01" * 16
    ciphertext = b"payload"

    try:
        parse_gcm_payload((999).to_bytes(4, "big") + tag + ciphertext)
    except EufyMakeMqttProtocolError:
        pass
    else:
        raise AssertionError("Expected GCM payload size failure")


def _frame_header(header_size: int, m5: int) -> bytes:
    header = bytearray(header_size)
    total_size = header_size + 16 + 1
    header[0:2] = b"MA"
    header[2:4] = total_size.to_bytes(2, "little")
    header[4] = 0x05
    header[5] = 0x01
    header[6] = m5
    header[7] = 0x05
    header[8] = 0x46
    header[9] = 0xC0
    header[10:12] = (7).to_bytes(2, "little")
    return bytes(header)


def _login(country_code: str, app_domain: str) -> CachedLogin:
    return CachedLogin(
        user_id="user-123",
        email="fixture@example.com",
        auth_token="fixture-token",
        token_expires_at=None,
        app_domain=app_domain,
        make_it_real_domain=None,
        country_code=country_code,
        geo_key=None,
        test_flag="1",
    )
