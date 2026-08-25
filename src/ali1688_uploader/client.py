from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import requests

from .config import Settings


def _wire_value(value: Any) -> str | int | float | bool:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def compute_signature(api_path: str, params: dict[str, Any], app_secret: str) -> str:
    """
    1688 Open Platform 常见 param2 签名：
    api_path + sorted(key + value), HMAC-SHA1, uppercase hex.
    """
    normalized = {k: _wire_value(v) for k, v in params.items()}
    encoded_parts = [f"{key}{normalized[key]}" for key in sorted(normalized)]
    message = api_path + "".join(encoded_parts)
    return hmac.new(
        app_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest().upper()


class Alibaba1688Client:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()

    def _api_path(self, api: str) -> str:
        return f"param2/{self.settings.api_version}/{api}/{self.settings.app_key}"

    def _url(self, api: str) -> str:
        return f"{self.settings.gateway}/openapi/{self._api_path(api)}"

    def execute(self, api: str, params: dict[str, Any]) -> dict:
        api_path = self._api_path(api)

        wire_params = {k: _wire_value(v) for k, v in params.items()}
        wire_params["access_token"] = self.settings.access_token
        wire_params["_aop_timestamp"] = int(time.time() * 1000)
        wire_params["_aop_signature"] = compute_signature(
            api_path=api_path,
            params=wire_params,
            app_secret=self.settings.app_secret,
        )

        response = self.session.post(
            self._url(api),
            params=wire_params,
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"1688 返回非 JSON，HTTP {response.status_code}: {response.text[:500]}"
            ) from exc

        if isinstance(payload, dict):
            error_code = (
                payload.get("errorCode")
                or payload.get("error_code")
                or payload.get("code")
            )
            success = payload.get("success")
            if success is False:
                raise RuntimeError(f"1688 API 返回失败: {payload}")
            if error_code not in (None, "", 0, "0") and not payload.get("productID"):
                raise RuntimeError(f"1688 API 错误: {payload}")

        return payload

    def add_product(self, params: dict[str, Any]) -> dict:
        return self.execute(self.settings.product_add_api, params)
