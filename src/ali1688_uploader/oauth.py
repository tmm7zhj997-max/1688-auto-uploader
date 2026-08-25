from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from .config import Settings


AUTHORIZATION_URL = "https://auth.1688.com/oauth/authorize"


def build_authorization_url(
    app_key: str,
    redirect_uri: str,
    *,
    state: str | None = None,
) -> str:
    if not app_key:
        raise ValueError("AppKey 不能为空")
    if not redirect_uri:
        raise ValueError("redirect_uri 不能为空")

    params = {
        "client_id": app_key,
        "site": "1688",
        "redirect_uri": redirect_uri,
    }
    if state:
        params["state"] = state
    return f"{AUTHORIZATION_URL}?{urlencode(params)}"


@dataclass(frozen=True)
class TokenResult:
    access_token: str
    refresh_token: str | None
    expires_in: str | int | None
    resource_owner: str | None
    member_id: str | None
    raw: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TokenResult":
        access_token = payload.get("access_token")
        if not access_token:
            raise RuntimeError(f"1688 OAuth 未返回 access_token: {payload}")
        return cls(
            access_token=str(access_token),
            refresh_token=(
                str(payload["refresh_token"])
                if payload.get("refresh_token") is not None
                else None
            ),
            expires_in=payload.get("expires_in"),
            resource_owner=payload.get("resource_owner"),
            member_id=payload.get("memberId") or payload.get("member_id"),
            raw=payload,
        )

    def safe_summary(self) -> dict[str, Any]:
        """Return metadata without exposing token values."""
        return {
            "access_token_received": bool(self.access_token),
            "refresh_token_received": bool(self.refresh_token),
            "expires_in": self.expires_in,
            "resource_owner": self.resource_owner,
            "member_id": self.member_id,
        }


def write_tokens_to_env(path: str | Path, result: TokenResult) -> Path:
    """Upsert access/refresh tokens into a local dotenv file."""
    path = Path(path)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    managed = {"ALI1688_ACCESS_TOKEN", "ALI1688_REFRESH_TOKEN"}
    kept = [
        line
        for line in existing
        if not any(line.startswith(f"{key}=") for key in managed)
    ]
    kept.append(f"ALI1688_ACCESS_TOKEN={result.access_token}")
    if result.refresh_token:
        kept.append(f"ALI1688_REFRESH_TOKEN={result.refresh_token}")
    path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


class Alibaba1688OAuthClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()

    def _require_app_credentials(self) -> None:
        missing = []
        if not self.settings.app_key:
            missing.append("ALI1688_APP_KEY")
        if not self.settings.app_secret:
            missing.append("ALI1688_APP_SECRET")
        if missing:
            raise RuntimeError("缺少 OAuth 配置: " + ", ".join(missing))

    def _decode(self, response: requests.Response) -> TokenResult:
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"1688 OAuth 返回非 JSON，HTTP {response.status_code}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError("1688 OAuth 返回格式不是 JSON object")
        if payload.get("error") or payload.get("error_code") or payload.get("errorMessage"):
            raise RuntimeError(f"1688 OAuth 返回错误: {payload}")
        return TokenResult.from_payload(payload)

    def exchange_code(self, code: str, redirect_uri: str) -> TokenResult:
        """Exchange a one-time authorization code for access/refresh tokens."""
        self._require_app_credentials()
        if not code:
            raise ValueError("授权 code 不能为空")
        if not redirect_uri:
            raise ValueError("redirect_uri 不能为空")

        url = (
            f"{self.settings.gateway}/openapi/http/1/"
            f"system.oauth2/getToken/{self.settings.app_key}"
        )
        params = {
            "grant_type": "authorization_code",
            "need_refresh_token": "true",
            "client_id": self.settings.app_key,
            "client_secret": self.settings.app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        response = self.session.post(
            url,
            params=params,
            timeout=self.settings.timeout_seconds,
        )
        return self._decode(response)

    def refresh_access_token(self, refresh_token: str) -> TokenResult:
        """Use a refresh token to obtain a new access token."""
        self._require_app_credentials()
        if not refresh_token:
            raise ValueError("refresh_token 不能为空")

        url = (
            f"{self.settings.gateway}/openapi/param2/1/"
            f"system.oauth2/getToken/{self.settings.app_key}"
        )
        params = {
            "grant_type": "refresh_token",
            "client_id": self.settings.app_key,
            "client_secret": self.settings.app_secret,
            "refresh_token": refresh_token,
        }
        response = self.session.post(
            url,
            params=params,
            timeout=self.settings.timeout_seconds,
        )
        return self._decode(response)
