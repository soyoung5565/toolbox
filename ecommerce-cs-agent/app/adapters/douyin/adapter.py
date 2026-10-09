"""抖店适配器 — 对接抖店开放平台 (飞鸽IM)

API文档: https://op.jinritemai.com/docs
签名方式: SHA256 (app_secret + param_json + timestamp + app_key + app_secret)

特点: 唯一拥有官方IM API的平台，消息收发零风险

主要API:
- /order/searchList → 订单列表
- /order/orderDetail → 订单详情
- /afterSale/sellerAgree → 卖家同意售后
- /afterSale/sellerRefuse → 卖家拒绝售后
- /im/sendMsg → 飞鸽IM发送消息
"""

import hashlib
import time
import json
import logging
from typing import Optional, Dict
import httpx

from app.adapters.base import EcommerceAdapter, PlatformConfig
from app.core.config import settings

logger = logging.getLogger(__name__)


class DouyinAdapter(EcommerceAdapter):
    """抖店/飞鸽适配器"""

    BASE_URL = "https://openapi-fxg.jinritemai.com"

    def __init__(self, config: PlatformConfig = None):
        if config is None:
            config = PlatformConfig(
                app_key=settings.DOUYIN_APP_KEY,
                app_secret=settings.DOUYIN_APP_SECRET,
            )
        super().__init__(config)
        self._tokens: Dict[str, dict] = {}

    @property
    def platform_name(self) -> str:
        return "douyin"

    # ========== 认证 ==========

    async def auth(self, shop_id: str) -> dict:
        """抖店OAuth授权:
        1. 引导商家: https://openapi-fxg.jinritemai.com/oauth2/authorize?app_id={app_key}&redirect_uri={callback}&scope=shop.order,shop.afterSale,shop.im
        2. 回调获取code
        3. 换token: /oauth2/access_token
        """
        logger.info(f"抖店授权: shop={shop_id}")
        return {"status": "pending", "message": "需引导商家完成OAuth授权"}

    async def refresh_access_token(self) -> dict:
        """刷新token: /oauth2/refresh_token"""
        return {"status": "not_implemented"}

    # ========== API调用基础 ==========

    async def _call_api(self, api_path: str, params: dict, method: str = "POST") -> dict:
        """调用抖店API
        
        签名规则:
        1. 将param_json按key排序序列化
        2. 拼接: app_secret + method + param_json + timestamp + app_key + app_secret
        3. SHA256
        """
        timestamp = str(int(time.time()))
        param_json = json.dumps(params, separators=(",", ":"), ensure_ascii=False)

        # 计算签名
        sign_str = f"{self.config.app_secret}{api_path}{param_json}{timestamp}{self.config.app_key}{self.config.app_secret}"
        sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest()

        url = f"{self.BASE_URL}{api_path}"

        headers = {
            "Content-Type": "application/json",
        }

        body = {
            "app_key": self.config.app_key,
            "method": api_path,
            "param_json": param_json,
            "timestamp": timestamp,
            "sign": sign,
            "sign_method": "SHA256",
            "v": "2",
        }

        if self._access_token:
            body["access_token"] = self._access_token

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=body, headers=headers)
                result = resp.json()

                if result.get("err_no", 0) != 0:
                    logger.error(f"抖店API错误: {api_path} - {result}")
                    return {"success": False, "error": result.get("message", "未知错误"), "code": result.get("err_no")}

                return {"success": True, "data": result.get("data", result)}
        except Exception as e:
            logger.error(f"抖店API异常: {api_path} - {e}")
            return {"success": False, "error": str(e)}

    # ========== 消息 ==========

    async def send_message(self, shop_id: str, buyer_id: str, content: str, msg_type: str = "text") -> dict:
        """通过飞鸽IM发送消息
        
        API: /im/sendMsg
        这是所有平台中唯一完全合规的消息发送API！
        """
        logger.info(f"抖店发送消息: shop={shop_id} -> buyer={buyer_id}")
        result = await self._call_api("/im/sendMsg", {
            "shop_id": shop_id,
            "to_user_id": buyer_id,
            "content": content,
            "msg_type": 0 if msg_type == "text" else 1,  # 0=文本 1=图片
        })
        return result

    async def get_message_history(self, shop_id: str, buyer_id: str, limit: int = 20) -> list:
        """获取聊天记录: /im/getMsgList"""
        return await self._call_api("/im/getMsgList", {
            "shop_id": shop_id,
            "to_user_id": buyer_id,
            "count": limit,
        })

    # ========== 订单 ==========

    async def query_order(self, order_id: str) -> dict:
        """查询订单: /order/orderDetail"""
        result = await self._call_api("/order/orderDetail", {
            "order_id": order_id,
        })

        if not result.get("success"):
            return result

        order = result["data"]
        return {
            "success": True,
            "order": {
                "order_id": order.get("order_id", order_id),
                "status": self._map_status(order.get("order_status", 0)),
                "total_amount": float(order.get("post_amount", 0)) / 100,
                "payment_amount": float(order.get("pay_amount", 0)) / 100,
                "products": [
                    {
                        "name": item.get("product_name", ""),
                        "sku": item.get("spec_desc", ""),
                        "price": float(item.get("origin_amount", 0)) / 100,
                        "quantity": int(item.get("item_num", 1)),
                    }
                    for item in order.get("sku_order_list", [])
                ],
                "receiver_name": order.get("post_receiver", {}).get("user_name", ""),
                "receiver_phone": order.get("post_receiver", {}).get("user_phone", ""),
                "receiver_address": order.get("post_receiver", {}).get("detail", ""),
                "created_at": str(order.get("create_time", "")),
            }
        }

    async def query_logistics(self, order_id: str) -> dict:
        """查询物流: /order/logisticsTrace"""
        return await self._call_api("/order/logisticsTrace", {
            "order_id": order_id,
        })

    # ========== 售后 ==========

    async def create_refund(self, order_id: str, reason: str, amount: float, refund_type: str = "refund_only") -> dict:
        """创建退款: /afterSale/create"""
        logger.info(f"抖店创建退款: order={order_id} amount={amount}")
        return await self._call_api("/afterSale/create", {
            "order_id": order_id,
            "refund_amount": str(int(amount * 100)),
            "reason": reason,
        })

    async def approve_return(self, refund_id: str) -> dict:
        """同意退款: /afterSale/sellerAgree"""
        logger.info(f"抖店同意退款: refund={refund_id}")
        return await self._call_api("/afterSale/sellerAgree", {
            "after_sale_id": refund_id,
        })

    async def reject_return(self, refund_id: str, reason: str) -> dict:
        """拒绝退款: /afterSale/sellerRefuse"""
        logger.info(f"抖店拒绝退款: refund={refund_id}")
        return await self._call_api("/afterSale/sellerRefuse", {
            "after_sale_id": refund_id,
            "refuse_reason": reason,
        })

    async def modify_address(self, order_id: str, new_address: dict) -> dict:
        """修改地址: /order/editAddress (发货前)"""
        logger.info(f"抖店修改地址: order={order_id}")
        return await self._call_api("/order/editAddress", {
            "order_id": order_id,
            "user_name": new_address.get("name", ""),
            "user_phone": new_address.get("phone", ""),
            "province": {"name": new_address.get("province", "")},
            "city": {"name": new_address.get("city", "")},
            "district": {"name": new_address.get("district", "")},
            "detail": new_address.get("detail", ""),
        })

    # ========== 商品 ==========

    async def search_products(self, shop_id: str, keyword: str, **kwargs) -> dict:
        """搜索商品: /product/listV2"""
        return await self._call_api("/product/listV2", {
            "keyword": keyword,
            "page": kwargs.get("page", 1),
            "size": kwargs.get("page_size", 20),
        })

    async def get_product_detail(self, product_id: str) -> dict:
        """商品详情: /product/detail"""
        return await self._call_api("/product/detail", {
            "product_id": product_id,
        })

    async def get_all_products(self, shop_id: str, page: int = 1, page_size: int = 50) -> dict:
        """全店商品: /product/listV2"""
        return await self._call_api("/product/listV2", {
            "page": page,
            "size": page_size,
        })

    # ========== 买家信息 ==========

    async def get_buyer_info(self, buyer_id: str) -> dict:
        return {"success": True, "buyer": {"buyer_id": buyer_id}}

    # ========== 工具方法 ==========

    def _map_status(self, status_code: int) -> str:
        """抖店订单状态映射"""
        status_map = {
            1: "待付款",
            2: "待发货",
            3: "已发货",
            4: "已完成",
            5: "已关闭",
            6: "售后中",
        }
        return status_map.get(status_code, f"未知({status_code})")
