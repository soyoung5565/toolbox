"""Mock数据层 — 无平台API Key时的本地测试数据

提供:
1. 模拟订单数据
2. 模拟商品数据
3. 模拟买家数据
4. 模拟退款数据

用于:
- 本地开发调试
- Agent对话测试
- 风控引擎测试
- 集成测试
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any


# ========== 模拟店铺 ==========
MOCK_SHOPS = {
    "pdd_shop_001": {
        "shop_id": "pdd_shop_001",
        "platform": "pdd",
        "shop_name": "测试数码旗舰店",
        "config": {
            "llm_provider": "mimo",
            "llm_model": "mimo-v2.5",
        }
    }
}

# ========== 模拟商品 ==========
MOCK_PRODUCTS = {
    "P10001": {
        "product_id": "P10001",
        "title": "无线蓝牙耳机 降噪运动跑步适用",
        "price": 89.00,
        "original_price": 129.00,
        "stock": 523,
        "sales": 1876,
        "category": "数码配件",
        "description": "蓝牙5.3，40小时续航，主动降噪，IPX5防水",
        "skus": [
            {"sku_id": "S001", "spec": "黑色-标准版", "price": 89.00, "stock": 200},
            {"sku_id": "S002", "spec": "白色-标准版", "price": 89.00, "stock": 180},
            {"sku_id": "S003", "spec": "黑色-升级版", "price": 119.00, "stock": 143},
        ],
        "image": "https://placeholder.com/300",
    },
    "P10002": {
        "product_id": "P10002",
        "title": "手机支架 桌面可折叠铝合金",
        "price": 29.90,
        "original_price": 49.90,
        "stock": 1200,
        "sales": 5680,
        "category": "手机配件",
        "description": "铝合金材质，可折叠，兼容4-12寸设备",
        "skus": [
            {"sku_id": "S004", "spec": "银色", "price": 29.90, "stock": 600},
            {"sku_id": "S005", "spec": "黑色", "price": 29.90, "stock": 600},
        ],
        "image": "https://placeholder.com/300",
    },
    "P10003": {
        "product_id": "P10003",
        "title": "Type-C数据线 快充100W 2米",
        "price": 15.90,
        "original_price": 25.90,
        "stock": 3000,
        "sales": 12340,
        "category": "数码配件",
        "description": "100W快充，2米长度，编织线材，兼容所有Type-C设备",
        "skus": [
            {"sku_id": "S006", "spec": "白色-2米", "price": 15.90, "stock": 1500},
            {"sku_id": "S007", "spec": "黑色-2米", "price": 15.90, "stock": 1500},
        ],
        "image": "https://placeholder.com/300",
    },
    "P10004": {
        "product_id": "P10004",
        "title": "充电宝 20000mAh 22.5W快充",
        "price": 69.00,
        "original_price": 99.00,
        "stock": 800,
        "sales": 3210,
        "category": "数码配件",
        "description": "20000mAh大容量，22.5W快充，可充手机4-5次",
        "skus": [
            {"sku_id": "S008", "spec": "白色", "price": 69.00, "stock": 400},
            {"sku_id": "S009", "spec": "黑色", "price": 69.00, "stock": 400},
        ],
        "image": "https://placeholder.com/300",
    },
}

# ========== 模拟买家 ==========
MOCK_BUYERS = {
    "buyer_001": {
        "buyer_id": "buyer_001",
        "buyer_name": "张三",
        "platform": "pdd",
        "total_orders": 15,
        "total_refunds": 1,
        "refund_rate": 0.067,
        "refund_count_7d": 0,
        "account_age_days": 365,
        "tags": ["老客"],
    },
    "buyer_002": {
        "buyer_id": "buyer_002",
        "buyer_name": "李四",
        "platform": "pdd",
        "total_orders": 3,
        "total_refunds": 2,
        "refund_rate": 0.667,
        "refund_count_7d": 2,
        "account_age_days": 5,
        "tags": ["新客", "疑似恶意"],
    },
    "buyer_003": {
        "buyer_id": "buyer_003",
        "buyer_name": "王五",
        "platform": "pdd",
        "total_orders": 50,
        "total_refunds": 0,
        "refund_rate": 0.0,
        "refund_count_7d": 0,
        "account_age_days": 730,
        "tags": ["老客", "高价值"],
    },
}

# ========== 模拟订单 ==========
_now = datetime.now()

MOCK_ORDERS = {
    "PDD20260701001": {
        "order_id": "PDD20260701001",
        "platform": "pdd",
        "shop_id": "pdd_shop_001",
        "buyer_id": "buyer_001",
        "status": "已签收",
        "total_amount": 89.00,
        "payment_amount": 85.00,
        "products": [
            {"product_id": "P10001", "name": "无线蓝牙耳机", "sku": "黑色-标准版", "price": 89.00, "quantity": 1}
        ],
        "receiver_name": "张三",
        "receiver_phone": "138****1234",
        "receiver_address": "广东省东莞市松山湖xxx",
        "logistics_company": "圆通速递",
        "logistics_no": "YT20260701001",
        "created_at": (_now - timedelta(days=5)).isoformat(),
        "shipped_at": (_now - timedelta(days=4)).isoformat(),
        "delivered_at": (_now - timedelta(days=2)).isoformat(),
    },
    "PDD20260702001": {
        "order_id": "PDD20260702001",
        "platform": "pdd",
        "shop_id": "pdd_shop_001",
        "buyer_id": "buyer_002",
        "status": "已签收",
        "total_amount": 69.00,
        "payment_amount": 65.00,
        "products": [
            {"product_id": "P10004", "name": "充电宝 20000mAh", "sku": "白色", "price": 69.00, "quantity": 1}
        ],
        "receiver_name": "李四",
        "receiver_phone": "139****5678",
        "receiver_address": "北京市朝阳区xxx",
        "logistics_company": "中通快递",
        "logistics_no": "ZT20260702001",
        "created_at": (_now - timedelta(days=3)).isoformat(),
        "shipped_at": (_now - timedelta(days=2)).isoformat(),
        "delivered_at": (_now - timedelta(days=1)).isoformat(),
    },
    "PDD20260703001": {
        "order_id": "PDD20260703001",
        "platform": "pdd",
        "shop_id": "pdd_shop_001",
        "buyer_id": "buyer_003",
        "status": "待发货",
        "total_amount": 119.00,
        "payment_amount": 115.00,
        "products": [
            {"product_id": "P10001", "name": "无线蓝牙耳机", "sku": "黑色-升级版", "price": 119.00, "quantity": 1}
        ],
        "receiver_name": "王五",
        "receiver_phone": "137****9012",
        "receiver_address": "上海市浦东新区xxx",
        "logistics_company": "",
        "logistics_no": "",
        "created_at": (_now - timedelta(hours=2)).isoformat(),
        "shipped_at": None,
        "delivered_at": None,
    },
    "PDD20260704001": {
        "order_id": "PDD20260704001",
        "platform": "pdd",
        "shop_id": "pdd_shop_001",
        "buyer_id": "buyer_001",
        "status": "已发货",
        "total_amount": 45.80,
        "payment_amount": 42.80,
        "products": [
            {"product_id": "P10002", "name": "手机支架", "sku": "银色", "price": 29.90, "quantity": 1},
            {"product_id": "P10003", "name": "Type-C数据线", "sku": "白色-2米", "price": 15.90, "quantity": 1},
        ],
        "receiver_name": "张三",
        "receiver_phone": "138****1234",
        "receiver_address": "广东省东莞市松山湖xxx",
        "logistics_company": "韵达快递",
        "logistics_no": "YD20260704001",
        "created_at": (_now - timedelta(days=1)).isoformat(),
        "shipped_at": (_now - timedelta(hours=12)).isoformat(),
        "delivered_at": None,
    },
}

# ========== 模拟物流 ==========
MOCK_LOGISTICS = {
    "PDD20260701001": {
        "company": "圆通速递",
        "tracking_no": "YT20260701001",
        "status": "已签收",
        "tracks": [
            {"time": (_now - timedelta(days=4)).strftime("%Y-%m-%d 10:00"), "content": "已揽收"},
            {"time": (_now - timedelta(days=3)).strftime("%Y-%m-%d 18:00"), "content": "到达东莞转运中心"},
            {"time": (_now - timedelta(days=2)).strftime("%Y-%m-%d 09:00"), "content": "派件中"},
            {"time": (_now - timedelta(days=2)).strftime("%Y-%m-%d 14:30"), "content": "已签收"},
        ]
    },
    "PDD20260704001": {
        "company": "韵达快递",
        "tracking_no": "YD20260704001",
        "status": "运输中",
        "tracks": [
            {"time": (_now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M"), "content": "已揽收"},
            {"time": (_now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M"), "content": "到达广州转运中心"},
        ]
    },
}

# ========== 模拟退款 ==========
MOCK_REFUNDS = {}


def get_mock_order(order_id: str) -> dict:
    """获取模拟订单"""
    return MOCK_ORDERS.get(order_id)


def get_mock_buyer(buyer_id: str) -> dict:
    """获取模拟买家"""
    return MOCK_BUYERS.get(buyer_id)


def get_mock_product(product_id: str) -> dict:
    """获取模拟商品"""
    return MOCK_PRODUCTS.get(product_id)


def search_mock_products(keyword: str) -> list:
    """搜索模拟商品"""
    results = []
    for pid, p in MOCK_PRODUCTS.items():
        if keyword.lower() in p["title"].lower() or keyword.lower() in p.get("description", "").lower():
            results.append(p)
    return results


def get_mock_logistics(order_id: str) -> dict:
    """获取模拟物流"""
    return MOCK_LOGISTICS.get(order_id)


def get_mock_orders_for_buyer(buyer_id: str) -> list:
    """获取买家的所有订单"""
    return [o for o in MOCK_ORDERS.values() if o["buyer_id"] == buyer_id]
