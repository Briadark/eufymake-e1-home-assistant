"""Known eufyMake endpoint metadata from the desktop app."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class EufyMakeEndpoints:
    """Regional eufyMake service endpoints."""

    app_domain: str
    make_it_real_domain: str
    mqtt_host: str


REGIONAL_ENDPOINTS: dict[str, EufyMakeEndpoints] = {
    "us": EufyMakeEndpoints(
        app_domain="make-app.ankermake.com",
        make_it_real_domain="aiot-api-us.ankermake.com",
        mqtt_host="make-mqtt.ankermake.com",
    ),
    "eu": EufyMakeEndpoints(
        app_domain="make-app-eu.ankermake.com",
        make_it_real_domain="aiot-api-eu.ankermake.com",
        mqtt_host="make-mqtt-eu.ankermake.com",
    ),
}

API_PATHS = {
    "device_list": "/v3/app/query_fdm_list",
    "device_dsk_keys": "/v3/app/equipment/get_dsk_keys",
    "maker_parts": "/v3/app/query_makerpart_list",
    "user_profile": "/v3/passport/profile",
    "user_params": "/v3/pc/passport/get_user_params",
    "overall_config": "/v3/pc/overall/get_config",
}

MQTT_TOPICS = {
    "device": "/device/maker/{serial_number}",
    "device_query": "/device/maker/field/query",
    "device_command": "/device/maker/field/command",
    "phone_query_reply": "/phone/maker/field/query/reply",
    "phone_command_reply": "/phone/maker/field/command/reply",
    "phone_notice": "/phone/maker/field/notice",
}

