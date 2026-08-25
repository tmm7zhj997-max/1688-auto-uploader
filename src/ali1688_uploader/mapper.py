from __future__ import annotations

from .models import Product


def to_product_add_params(product: Product) -> dict:
    """
    将标准商品模型映射为 alibaba.product.add 的业务参数。
    复杂对象保持 Python 结构，HTTP 客户端会在发送前 JSON 序列化。
    """
    return {
        "productType": product.product_type,
        "categoryID": product.category_id,
        "webSite": product.website,
        "subject": product.subject,
        "description": product.description,
        "language": product.language,
        "bizType": product.biz_type,
        "pictureAuth": product.picture_auth,
        "attributes": product.attributes,
        "image": {"images": product.images},
        "skuInfos": [sku.model_dump(exclude_none=True) for sku in product.skus],
        "saleInfo": product.sale_info.model_dump(exclude_none=True),
        "shippingInfo": product.shipping_info.model_dump(exclude_none=True),
    }
