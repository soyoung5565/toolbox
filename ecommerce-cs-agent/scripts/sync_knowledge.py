"""商品知识库同步脚本 — 从各平台API拉取商品数据，生成结构化文档

用途:
1. 定时同步全店商品到Dify知识库
2. 生成商品FAQ文档
3. 更新RAG索引

运行方式:
    python -m scripts.sync_knowledge --platform taobao --shop-id xxx
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def sync_products(platform: str, shop_id: str, output_dir: str = "knowledge_base"):
    """同步全店商品到知识库
    
    步骤:
    1. 调用平台API获取全店商品列表
    2. 获取每个商品详情
    3. 生成结构化Markdown文档
    4. 上传到Dify知识库
    """
    from app.adapters.registry import get_adapter

    adapter = get_adapter(platform, shop_id)
    logger.info(f"开始同步: [{platform}] shop={shop_id}")

    # 1. 获取全店商品
    all_products = []
    page = 1
    while True:
        result = await adapter.get_all_products(shop_id, page=page, page_size=50)
        if not result.get("success"):
            logger.error(f"获取商品列表失败: {result}")
            break

        # 解析商品列表（不同平台返回格式不同）
        products = _extract_products(result, platform)
        if not products:
            break

        all_products.extend(products)
        logger.info(f"  第{page}页: {len(products)}个商品，累计{len(all_products)}个")

        if len(products) < 50:
            break
        page += 1

    logger.info(f"共获取 {len(all_products)} 个商品")

    # 2. 生成知识库文档
    os.makedirs(output_dir, exist_ok=True)

    # 商品目录文档
    catalog_doc = generate_catalog_doc(all_products, platform, shop_id)
    catalog_path = os.path.join(output_dir, f"{platform}_catalog.md")
    with open(catalog_path, "w", encoding="utf-8") as f:
        f.write(catalog_doc)
    logger.info(f"商品目录已生成: {catalog_path}")

    # 每个商品的详情文档
    for product in all_products:
        detail_doc = generate_product_doc(product, platform)
        product_id = product.get("product_id", product.get("id", "unknown"))
        detail_path = os.path.join(output_dir, f"{platform}_product_{product_id}.md")
        with open(detail_path, "w", encoding="utf-8") as f:
            f.write(detail_doc)

    logger.info(f"商品详情文档已生成: {len(all_products)}个")

    # 3. 上传到Dify (TODO)
    # await upload_to_dify(output_dir, f"{platform}_products")

    return {"total": len(all_products), "output_dir": output_dir}


def _extract_products(result: dict, platform: str) -> list:
    """从API返回中提取标准化商品列表"""
    data = result.get("data", result)

    if platform == "taobao":
        items = data.get("items_onsale_get_response", {}).get("items", {}).get("item", [])
        return [
            {
                "product_id": str(item.get("num_iid", "")),
                "title": item.get("title", ""),
                "price": float(item.get("price", 0)),
                "stock": int(item.get("num", 0)),
                "image": item.get("pic_url", ""),
            }
            for item in items
        ]
    elif platform == "pdd":
        items = data.get("goods_search_response", {}).get("goods_list", [])
        return [
            {
                "product_id": str(item.get("goods_id", "")),
                "title": item.get("goods_name", ""),
                "price": float(item.get("min_group_price", 0)) / 100,
                "stock": int(item.get("goods_quantity", 0)),
                "image": item.get("goods_thumbnail_url", ""),
            }
            for item in items
        ]
    elif platform == "douyin":
        items = data.get("products", data.get("data", []))
        if isinstance(items, dict):
            items = items.get("products", [])
        return [
            {
                "product_id": str(item.get("product_id", "")),
                "title": item.get("product_name", item.get("title", "")),
                "price": float(item.get("market_price", 0)) / 100,
                "stock": int(item.get("stock_num", 0)),
                "image": item.get("cover", item.get("img", "")),
            }
            for item in items
        ]

    return []


def generate_catalog_doc(products: list, platform: str, shop_id: str) -> str:
    """生成商品目录Markdown文档"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = f"# {platform.upper()} 商品目录\n\n"
    doc += f"> 店铺ID: {shop_id}\n"
    doc += f"> 更新时间: {now}\n"
    doc += f"> 商品总数: {len(products)}\n\n"
    doc += "| 商品ID | 商品名称 | 价格 | 库存 |\n"
    doc += "|--------|----------|------|------|\n"

    for p in products:
        doc += f"| {p['product_id']} | {p['title']} | ¥{p['price']:.2f} | {p['stock']} |\n"

    return doc


def generate_product_doc(product: dict, platform: str) -> str:
    """生成单个商品的知识库文档"""
    doc = f"# {product.get('title', '未知商品')}\n\n"
    doc += f"- **商品ID**: {product.get('product_id', '')}\n"
    doc += f"- **价格**: ¥{product.get('price', 0):.2f}\n"
    doc += f"- **库存**: {product.get('stock', 0)}\n"
    doc += f"- **平台**: {platform}\n"

    if product.get("image"):
        doc += f"- **图片**: {product['image']}\n"

    if product.get("description"):
        doc += f"\n## 商品描述\n\n{product['description']}\n"

    if product.get("skus"):
        doc += "\n## 规格列表\n\n"
        for sku in product["skus"]:
            doc += f"- {sku.get('spec', '')}: ¥{sku.get('price', 0):.2f} (库存{sku.get('stock', 0)})\n"

    return doc


if __name__ == "__main__":
    import sys
    platform = sys.argv[1] if len(sys.argv) > 1 else "taobao"
    shop_id = sys.argv[2] if len(sys.argv) > 2 else "demo_shop"
    asyncio.run(sync_products(platform, shop_id))
