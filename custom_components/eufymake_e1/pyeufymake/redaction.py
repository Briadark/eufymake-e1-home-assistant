"""Redaction helpers for eufyMake development tools."""

from __future__ import annotations

from typing import Any

SECRET_WORDS = (
    "auth",
    "conn",
    "did",
    "email",
    "key",
    "license",
    "mac",
    "name",
    "password",
    "secret",
    "signature",
    "sn",
    "ssid",
    "taskid",
    "token",
    "user",
)

MAX_DICT_ITEMS = 25
MAX_LIST_ITEMS = 3


def is_secret_key(key: str) -> bool:
    """Return true if the key likely identifies private data."""
    lowered = key.lower()
    return any(word in lowered for word in SECRET_WORDS)


def display_key(key: str) -> str:
    """Redact dictionary keys that are themselves identifiers."""
    if is_secret_key(key) or (key.startswith("AK") and len(key) >= 10):
        return "<redacted_key>"
    return key


def redact(value: Any, key: str = "") -> Any:
    """Redact secret-looking values while keeping structure visible."""
    if isinstance(value, dict):
        items = list(value.items())
        redacted = {
            display_key(item_key): redact(item_value, item_key)
            for item_key, item_value in items[:MAX_DICT_ITEMS]
        }
        if len(items) > MAX_DICT_ITEMS:
            redacted["<truncated_keys>"] = len(items) - MAX_DICT_ITEMS
        return redacted
    if isinstance(value, list):
        redacted_items = [redact(item) for item in value[:MAX_LIST_ITEMS]]
        if len(value) > MAX_LIST_ITEMS:
            redacted_items.append({"<truncated_items>": len(value) - MAX_LIST_ITEMS})
        return redacted_items
    if is_secret_key(key):
        return "<redacted>"
    if isinstance(value, str) and len(value) > 10:
        return f"{value[:4]}...{value[-4:]}"
    return value
