"""Read eufyMake Studio user profile cache files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote


class EufyMakeProfileCacheError(Exception):
    """Raised when profile cache data cannot be loaded."""


@dataclass(frozen=True, kw_only=True)
class CachedLogin:
    """Cached eufyMake login metadata."""

    user_id: str
    email: str | None
    auth_token: str
    token_expires_at: int | None
    app_domain: str | None
    make_it_real_domain: str | None
    country_code: str | None
    geo_key: str | None
    test_flag: str | None


class EufyMakeProfileCacheStore:
    """Load login metadata from a eufyMake Studio profile cache directory."""

    def __init__(self, profile_dir: str | Path) -> None:
        """Initialize the profile cache store."""
        self.profile_dir = Path(profile_dir)

    def load_login(self) -> CachedLogin:
        """Load cached login metadata."""
        data = self._load_login_info()
        login_data = self._load_login_list_data()
        return CachedLogin(
            user_id=str(data.get("user_id", "")),
            email=_optional_str(unquote(str(data.get("email", "")))),
            auth_token=str(data.get("auth_token", "")),
            token_expires_at=_optional_int(data.get("token_expires_at")),
            app_domain=_optional_str(data.get("domain") or login_data.get("domain")),
            make_it_real_domain=_optional_str(
                data.get("makeItRealDomain") or login_data.get("makeItRealDomain")
            ),
            country_code=_optional_str(
                data.get("country_code") or login_data.get("country_code")
            ),
            geo_key=_optional_str(login_data.get("geo_key")),
            test_flag=_optional_str(
                data.get("test_flag") or login_data.get("test_flag")
            ),
        )

    def _load_login_info(self) -> dict[str, Any]:
        """Load login metadata from login_info.json."""
        path = self.profile_dir / "cache" / "offline" / "user_info" / "login_info.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as err:
            raise EufyMakeProfileCacheError(
                f"Could not read {path.name}: {err}"
            ) from err
        except json.JSONDecodeError as err:
            raise EufyMakeProfileCacheError(
                f"Invalid JSON in {path.name}: {err}"
            ) from err

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise EufyMakeProfileCacheError("login_info.json data is not an object")
        return data

    def _load_login_list_data(self) -> dict[str, Any]:
        """Load supplemental login metadata from login_list.json when present."""
        path = self.profile_dir / "cache" / "offline" / "user_info" / "login_list.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        login_data = payload.get("login_data") if isinstance(payload, dict) else None
        data = login_data.get("data") if isinstance(login_data, dict) else None
        return data if isinstance(data, dict) else {}


def _optional_str(value: Any) -> str | None:
    """Return a non-empty string or None."""
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: Any) -> int | None:
    """Return an integer or None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
