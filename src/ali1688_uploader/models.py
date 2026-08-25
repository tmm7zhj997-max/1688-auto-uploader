from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class PriceRange(BaseModel):
    startQuantity: int = Field(gt=0)
    price: float = Field(gt=0)


class SKU(BaseModel):
    cargoNumber: str = Field(min_length=1, max_length=128)
    amountOnSale: int = Field(ge=0)
    price: float | None = Field(default=None, gt=0)
    priceRange: list[PriceRange] | None = None
    retailPrice: float = Field(gt=0)
    consignPrice: float = Field(gt=0)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    skuCode: str | None = None

    @model_validator(mode="after")
    def validate_price(self):
        if self.price is None and not self.priceRange:
            raise ValueError("SKU 必须提供 price 或 priceRange")
        return self


class SaleInfo(BaseModel):
    supportOnlineTrade: bool = True
    mixWholeSale: bool = False
    saleType: str = "normal"
    priceAuth: bool = False
    priceRanges: list[PriceRange] = Field(default_factory=list)
    amountOnSale: float = Field(ge=0)
    unit: str = Field(min_length=1)
    minOrderQuantity: int = Field(gt=0)
    quoteType: int = Field(ge=0, le=3)


class ShippingInfo(BaseModel):
    freightTemplateID: int
    unitWeight: float = Field(gt=0)
    sendGoodsAddressId: int
    sendGoodsAddressText: str = Field(min_length=1)


class Product(BaseModel):
    external_id: str = Field(min_length=1, max_length=128)
    category_id: int = Field(gt=0)
    subject: str = Field(min_length=1, max_length=128)
    description: str = ""
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    images: list[str] = Field(min_length=1)
    skus: list[SKU] = Field(default_factory=list)
    sale_info: SaleInfo
    shipping_info: ShippingInfo

    product_type: str = "wholesale"
    website: str = "1688"
    language: str = "CHINESE"
    biz_type: int = 1
    picture_auth: bool = False

    @field_validator("website")
    @classmethod
    def website_must_be_1688(cls, value: str):
        if value != "1688":
            raise ValueError("website 必须为 1688")
        return value

    @field_validator("language")
    @classmethod
    def language_must_be_chinese(cls, value: str):
        if value != "CHINESE":
            raise ValueError("language 必须为 CHINESE")
        return value
