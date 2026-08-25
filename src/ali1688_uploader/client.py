from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import time
from typing import Any

import requests

from .config import Settings
from .images import validate_image_file


def _wire_value(value: Any) -> str | int | float | bool:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def compute_signature(api_path: str, params: dict[str, Any], app_secret: str) -> str:
    """
    1688 Open Platform param2 style signing:
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

    def _signed_params(self, api: str, params: dict[str, Any]) -> dict[str, Any]:
        api_path = self._api_path(api)
        wire_params = {k: _wire_value(v) for k, v in params.items()}
        wire_params["access_token"] = self.settings.access_token
        wire_params["_aop_timestamp"] = int(time.time() * 1000)
        wire_params["_aop_signature"] = compute_signature(
            api_path=api_path,
            params=wire_params,
            app_secret=self.settings.app_secret,
        )
        return wire_params

    @staticmethod
    def _decode_response(response: requests.Response) -> dict:
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
            if error_code not in (None, "", 0, "0") and not (
                payload.get("productID")
                or payload.get("productId")
                or payload.get("result")
            ):
                raise RuntimeError(f"1688 API 错误: {payload}")
        return payload

    def execute(self, api: str, params: dict[str, Any]) -> dict:
        response = self.session.post(
            self._url(api),
            params=self._signed_params(api, params),
            timeout=self.settings.timeout_seconds,
        )
        return self._decode_response(response)

    def category_attributes(self, category_id: int) -> dict:
        return self.execute(
            self.settings.category_attr_api,
            {"categoryID": category_id, "webSite": "1688"},
        )

    def add_product(self, params: dict[str, Any]) -> dict:
        return self.execute(self.settings.product_add_api, params)

    def edit_product(self, product_id: int, product_info: dict[str, Any]) -> dict:
        return self.execute(
            self.settings.product_edit_api,
            {
                "productID": product_id,
                "productInfo": product_info,
                "webSite": "1688",
            },
        )

    def modify_stock(
        self,
        stock_changes: list[dict[str, Any]],
        *,
        incremental: bool = False,
    ) -> dict:
        return self.execute(
            self.settings.product_stock_api,
            {
                "productStockChange": stock_changes,
                "increaseModify": incremental,
                "webSite": "1688",
            },
        )

    def get_product(self, product_id: int) -> dict:
        return self.execute(
            self.settings.product_get_api,
            {"productID": product_id, "webSite": "1688", "scene": "1688"},
        )

    def list_products(
        self,
        *,
        page_no: int = 1,
        page_size: int = 20,
        status_list: list[str] | None = None,
        category_id: int | None = None,
        subject_key: str | None = None,
    ) -> dict:
        if not 1 <= page_size <= 20:
            raise ValueError("page_size 必须在 1 到 20 之间")
        params: dict[str, Any] = {"pageNo": page_no, "pageSize": page_size}
        if status_list:
            params["statusList"] = status_list
        if category_id:
            params["categoryId"] = category_id
        if subject_key:
            params["subjectKey"] = subject_key
        return self.execute(self.settings.product_list_api, params)

    def add_photo(
        self,
        image_path: str | Path,
        *,
        name: str | None = None,
        album_id: int | None = None,
        description: str | None = None,
        draw_text: bool = False,
    ) -> dict:
        """
        Multipart upload for alibaba.photobank.photo.add.

        Normal parameters are signed through the param2 flow, while imageBytes
        is sent as multipart file content.
        """
        image_path = Path(image_path)
        info = validate_image_file(image_path)
        upload_name = name or image_path.stem
        if len(upload_name) > 30:
            raise ValueError("图片名称最多 30 个字符")

        params: dict[str, Any] = {
            "name": upload_name,
            "drawTxt": draw_text,
            "webSite": "1688",
        }
        if album_id is not None:
            params["albumID"] = album_id
        if description:
            params["description"] = description

        signed = self._signed_params(self.settings.photobank_photo_add_api, params)
        with image_path.open("rb") as fh:
            response = self.session.post(
                self._url(self.settings.photobank_photo_add_api),
                data=signed,
                files={
                    "imageBytes": (
                        image_path.name,
                        fh,
                        str(info["mime_type"]),
                    )
                },
                timeout=self.settings.timeout_seconds,
            )
        return self._decode_response(response)
