"""Parsers for eufyMake E1 ink status payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INK_STATUS_COMMAND = 1100


@dataclass(frozen=True, kw_only=True)
class InkChannel:
    """One E1 ink channel."""

    channel: str
    remaining_percent: float | None
    serial_number: str | None
    status: int | None
    manufacture_timestamp: int | None
    expiration_timestamp: int | None
    distance_expiration_days: int | None
    expired: bool | None


@dataclass(frozen=True, kw_only=True)
class WasteInkTank:
    """E1 waste ink tank status."""

    remaining_percent: float | None
    status: int | None
    expiration_timestamp: int | None
    distance_expiration_days: int | None
    expired: bool | None


@dataclass(frozen=True, kw_only=True)
class InkStatus:
    """Parsed E1 ink and waste tank status."""

    channels: tuple[InkChannel, ...]
    waste_tank: WasteInkTank | None


def iter_status_messages(payload: Any) -> tuple[dict[str, Any], ...]:
    """Return status message objects from a decrypted MQTT payload."""
    if isinstance(payload, dict):
        return (payload,)
    if isinstance(payload, list):
        return tuple(item for item in payload if isinstance(item, dict))
    return ()


def find_ink_status(payload: Any) -> InkStatus | None:
    """Find and parse the first commandType 1100 status message."""
    for message in iter_status_messages(payload):
        if _optional_int(message.get("commandType")) == INK_STATUS_COMMAND:
            return parse_ink_status(message)
    return None


def parse_ink_status(message: dict[str, Any]) -> InkStatus:
    """Parse a commandType 1100 ink status message."""
    ink = message.get("ink")
    waste_ink = message.get("wasteInk")
    return InkStatus(
        channels=_parse_channels(ink if isinstance(ink, dict) else {}),
        waste_tank=_parse_waste_tank(waste_ink if isinstance(waste_ink, dict) else {}),
    )


def _parse_channels(ink: dict[str, Any]) -> tuple[InkChannel, ...]:
    channels = _list(ink.get("colorSort"))
    levels = _list(ink.get("leftInk"))
    serials = _list(ink.get("sn"))
    statuses = _list(ink.get("status"))
    manufacture = _first_existing_list(
        ink,
        ("manufactureTimestamp", "manufactureTime"),
    )
    expiration = _list(ink.get("expirationTimestamp"))
    distance_expiration = _list(ink.get("distanceExpiration"))
    expired = _list(ink.get("expired"))

    if not channels:
        count = _optional_int(ink.get("count")) or len(levels)
        channels = [str(index + 1) for index in range(count)]

    parsed: list[InkChannel] = []
    for index, channel in enumerate(channels):
        parsed.append(
            InkChannel(
                channel=str(channel),
                remaining_percent=_hundredths_percent(_at(levels, index)),
                serial_number=_optional_str(_at(serials, index)),
                status=_optional_int(_at(statuses, index)),
                manufacture_timestamp=_optional_int(_at(manufacture, index)),
                expiration_timestamp=_optional_int(_at(expiration, index)),
                distance_expiration_days=_optional_int(
                    _at(distance_expiration, index)
                ),
                expired=_optional_bool(_at(expired, index)),
            )
        )
    return tuple(parsed)


def _parse_waste_tank(waste_ink: dict[str, Any]) -> WasteInkTank | None:
    if not waste_ink:
        return None

    levels = _first_existing_list(
        waste_ink,
        ("leftInk", "remainingInk", "remaining", "level"),
    )
    statuses = _list(waste_ink.get("status"))
    expiration = _list(waste_ink.get("expirationTimestamp"))
    distance_expiration = _list(waste_ink.get("distanceExpiration"))
    expired = _list(waste_ink.get("expired"))

    return WasteInkTank(
        remaining_percent=_hundredths_percent(_at(levels, 0)),
        status=_optional_int(_at(statuses, 0)),
        expiration_timestamp=_optional_int(_at(expiration, 0)),
        distance_expiration_days=_optional_int(_at(distance_expiration, 0)),
        expired=_optional_bool(_at(expired, 0)),
    )


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _first_existing_list(data: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    for key in keys:
        if key in data:
            return _list(data.get(key))
    return []


def _at(values: list[Any], index: int) -> Any:
    try:
        return values[index]
    except IndexError:
        return None


def _hundredths_percent(value: Any) -> float | None:
    parsed = _optional_int(value)
    if parsed is None:
        return None
    return parsed / 100


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    parsed = _optional_int(value)
    if parsed is None:
        return None
    return bool(parsed)
