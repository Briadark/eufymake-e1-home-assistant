"""Small read-only cloud API helpers for protocol discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .endpoints import API_PATHS
from .models import Device
from .profile import CachedLogin


class EufyMakeCloudProbeError(Exception):
    """Raised when a cloud API probe cannot be completed."""


@dataclass(frozen=True, kw_only=True)
class ProbeResult:
    """Result from one cloud API probe attempt."""

    name: str
    method: str
    url: str
    header_variant: str
    status: int | None
    ok: bool
    body: dict[str, Any] | list[Any] | str | None
    error: str | None = None


class EufyMakeCloudProbe:
    """Probe read-only eufyMake cloud endpoints with cached login metadata."""

    def __init__(self, login: CachedLogin, *, timeout: float = 10) -> None:
        """Initialize the probe."""
        if not login.auth_token:
            raise EufyMakeCloudProbeError("Cached auth token is empty")
        if not login.app_domain:
            raise EufyMakeCloudProbeError("Cached app domain is empty")
        self.login = login
        self.timeout = timeout

    def probe_read_only(self) -> list[ProbeResult]:
        """Run a small set of read-only endpoint probes."""
        probes = [
            ("user_profile_v3", self._url(API_PATHS["user_profile"]), {}),
            ("device_list_v3", self._url(API_PATHS["device_list"]), {}),
            ("maker_parts_v3", self._url(API_PATHS["maker_parts"]), {}),
            ("user_profile_v1", self._url("/v1/passport/profile"), {}),
            ("device_list_v1", self._url("/v1/app/query_fdm_list"), {}),
            ("maker_parts_v1", self._url("/v1/app/query_makerpart_list"), {}),
        ]

        results: list[ProbeResult] = []
        for name, url, body in probes:
            for header_variant, headers in self._header_variants().items():
                results.append(
                    self._request(
                        name=name,
                        method="POST",
                        url=url,
                        headers=headers,
                        header_variant=header_variant,
                        body=body,
                    )
                )
                if results[-1].ok:
                    break
        return results

    def _url(self, path: str) -> str:
        """Build an HTTPS API URL."""
        return f"https://{self.login.app_domain}{path}"

    def _header_variants(self) -> dict[str, dict[str, str]]:
        """Return candidate request header sets seen in the desktop app."""
        common = {
            "App-name": "anker_make",
            "App-version": "4.2.2",
            "Model-type": "PC",
            "Language": "en",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "eufyMake Studio/4.2.2",
        }
        desktop = {
            "App_name": "anker_make",
            "App_version": "4.2.2",
            "Model_type": "PC",
            "Country": self.login.country_code or "",
            "User_country": self.login.country_code or "",
            "Gtoken": self.login.geo_key or "",
            "Test_flag": self.login.test_flag or "",
            "Openudid": self.login.user_id,
            "Os_type": "Windows",
            "Os_version": "10",
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json",
            "User-Agent": "eufyMake Studio/4.2.2",
        }
        return {
            "bearer": {**common, "Authorization": f"Bearer {self.login.auth_token}"},
            "x_auth_token": {**common, "X-Auth-Token": self.login.auth_token},
            "auth_token": {**common, "auth-token": self.login.auth_token},
            "desktop_x_auth_token": {**desktop, "X-Auth-Token": self.login.auth_token},
            "desktop_bearer": {
                **desktop,
                "Authorization": f"Bearer {self.login.auth_token}",
            },
            "desktop_gtoken_only": desktop,
        }

    def _request(
        self,
        *,
        name: str,
        method: str,
        url: str,
        headers: dict[str, str],
        header_variant: str,
        body: dict[str, Any],
    ) -> ProbeResult:
        """Send one API request."""
        payload = json.dumps(body).encode("utf-8")
        request = Request(url, data=payload, headers=headers, method=method)

        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_body = response.read()
                status = response.status
        except HTTPError as err:
            return ProbeResult(
                name=name,
                method=method,
                url=url,
                header_variant=header_variant,
                status=err.code,
                ok=False,
                body=_decode_body(err.read()),
                error=str(err),
            )
        except URLError as err:
            return ProbeResult(
                name=name,
                method=method,
                url=url,
                header_variant=header_variant,
                status=None,
                ok=False,
                body=None,
                error=str(err.reason),
            )
        except TimeoutError as err:
            return ProbeResult(
                name=name,
                method=method,
                url=url,
                header_variant=header_variant,
                status=None,
                ok=False,
                body=None,
                error=str(err),
            )

        return ProbeResult(
            name=name,
            method=method,
            url=url,
            header_variant=header_variant,
            status=status,
            ok=200 <= status < 300,
            body=_decode_body(response_body),
        )


def _decode_body(value: bytes) -> dict[str, Any] | list[Any] | str | None:
    """Decode an API response body."""
    if not value:
        return None
    text = value.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:500]
    return parsed


class EufyMakeCloudClient:
    """Read-only eufyMake cloud API client."""

    def __init__(self, login: CachedLogin, *, timeout: float = 10) -> None:
        """Initialize the client."""
        if not login.auth_token:
            raise EufyMakeCloudProbeError("Auth token is empty")
        if not login.app_domain:
            raise EufyMakeCloudProbeError("App domain is empty")
        self.login = login
        self.timeout = timeout

    def get_devices(self) -> list[Device]:
        """Fetch the cloud device list."""
        body = self._post("/v1/app/query_fdm_list", {})
        data = _expect_success_object(body).get("data", [])
        if not isinstance(data, list):
            raise EufyMakeCloudProbeError("Device list response data is not a list")
        return [Device.from_cache(item) for item in data if isinstance(item, dict)]

    def get_e1_devices(self) -> list[Device]:
        """Fetch only eufyMake E1 devices."""
        return [device for device in self.get_devices() if device.is_e1]

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to a eufyMake API path."""
        url = f"https://{self.login.app_domain}{path}"
        payload = json.dumps(body).encode("utf-8")
        request = Request(
            url,
            data=payload,
            headers=self._headers(),
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                decoded = _decode_body(response.read())
        except HTTPError as err:
            decoded = _decode_body(err.read())
            raise EufyMakeCloudProbeError(
                f"HTTP {err.code} from {path}: {decoded!r}"
            ) from err
        except URLError as err:
            raise EufyMakeCloudProbeError(
                f"Request to {path} failed: {err.reason}"
            ) from err

        if not isinstance(decoded, dict):
            raise EufyMakeCloudProbeError(
                f"Unexpected response from {path}: {decoded!r}"
            )
        return decoded

    def _headers(self) -> dict[str, str]:
        """Return headers proven by the read-only cloud probe."""
        return {
            "App-name": "anker_make",
            "App-version": "4.2.2",
            "Model-type": "PC",
            "Language": "en",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "eufyMake Studio/4.2.2",
            "X-Auth-Token": self.login.auth_token,
        }


def _expect_success_object(body: dict[str, Any]) -> dict[str, Any]:
    """Validate a common eufyMake API response object."""
    if body.get("code") != 0:
        raise EufyMakeCloudProbeError(
            f"API error: code={body.get('code')} msg={body.get('msg')}"
        )
    return body
