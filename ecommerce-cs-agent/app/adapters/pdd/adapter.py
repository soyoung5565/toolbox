"""拼多多适配器 — 对接多多开放平台

API文档: https://open.pinduoduo.com/application/document
签名方式: MD5 (client_secret + 参数按key排序 + client_secret)

主要API:
- pdd.order.information.get → 查询订单
- pdd.refund.information.inquiry → 查询退款
- pdd.refund.agree → 同意退款
- pdd.refund.rejection → 拒绝退款
- pdd.goods.search → 搜索商品
- pdd.goods.detail.get → 商品详情
"""

import hashlib
import time
import logging
from typing import Optional, Dict
import httpx

from app.adapters.base import EcommerceAdapter, PlatformConfig
from app.core.config import settings

logger = logging.getLogger(__name__)


class PddAdapter(EcommerceAdapter):
    """拼多多适配器"""

    BASE_URL = "https://gw-api.pinduoduo.com/api/router"

    def __init__(self, config: PlatformConfig = None):
        if config is None:
            config = PlatformConfig(
                app_key=settings.PDD_CLIENT_ID,
                app_secret=settings.PDD_CLIENT_SECRET,
            )
        super().__init__(config)
        self._tokens: Dict[str, dict] = {}

    @property
    def platform_name(self) -> str:
        return "pdd"

    # ========== 认证 ==========

    async def auth(self, shop_id: str) -> dict:
        """拼多多OAuth授权:
        1. 引导商家: https://mms.pinduoduo.com/open.html?client_id={client_id}&response_type=code&redirect_uri={callback}
        2. 回调获取code
        3. 换token: pdd.pop.auth.token.get
        """
        logger.info(f"拼多多授权: shop={shop_id}")
        return {"status": "pending", "message": "需引导商家完成OAuth授权"}

    async def refresh_access_token(self) -> dict:
        """刷新token: pdd.pop.auth.token.refresh"""
        return {"status": "not_implemented"}

    # ========== API调用基础 ==========

    async def _call_api(self, api_type: str, params: dict) -> dict:
        """调用拼多多API
        
        签名规则 (MD5):
        1. 将所有请求参数按key的ASCII码排序
        2. 拼接: client_secret + key1value1key2value2... + client_secret
        3. MD5后转大写
        """
        common_params = {
            "type": api_type,
            "client_id": self.config.app_key,
            "timestamp": str(int(time.time())),
            "data_type": "JSON",
        }

        all_params = {**common_params, **params}

        # 添加token
        if self._access_token:
            all_params["access_token"] = self._access_token

        # 签名
        all_params["sign"] = self._sign(all_params)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.BASE_URL, json=all_params)
                result = resp.json()

                if "error_response" in result:
                    error = result["error_response"]
                    logger.error(f"拼多多API错误: {api_type} - {error}")
                    return {"success": False, "error": error.get("error_msg", "未知错误"), "code": error.get("error_code")}

                return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"拼多多API异常: {api_type} - {e}")
            return {"success": False, "error": str(e)}

    def _sign(self, params: dict) -> str:
        """计算API签名 (MD5)"""
        sorted_keys = sorted(params.keys())
        sign_str = self.config.app_secret
        for key in sorted_keys:
            if key == "sign":
                continue
            value = params[key]
            if value is not None and str(value) != "":
                sign_str += f"{key}{value}"
        sign_str += self.config.app_secret
        return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

    # ========== 消息 ==========

    async def send_message(self, shop_id: str, buyer_id: str, content: str, msg_type: str = "text") -> dict:
        """发送消息: pdd.pop.im.msg.send"""
        logger.info(f"拼多多发送消息: shop={shop_id} -> buyer={buyer_id}")
        return {"success": False, "error": "消息发送需对接拼多多IM API，暂未实现"}

    async def get_message_history(self, shop_id: str, buyer_id: str, limit: int = 20) -> list:
        return []

    # ========== 订单 ==========

    async def query_order(self, order_id: str) -> dict:
        """查询订单: pdd.order.information.get"""
        result = await self._call_api("pdd.order.information.get", {
            "order_sn": order_id,
        })

        if not result.get("success"):
            return result

        order_data = result["data"].get("order_information_get_response", {})
        return {
            "success": True,
            "order": {
                "order_id": order_data.get("order_sn", order_id),
                "status": self._map_status(order_data.get("order_status", 0)),
                "total_amount": float(order_data.get("goods_amount", 0)) / 100,  # 拼多多金额单位是分
                "payment_amount": float(order_data.get("pay_amount", 0)) / 100,
                "products": [
                    {
                        "name": item.get("goods_name", ""),
                        "sku": item.get("goods_spec", ""),
                        "price": float(item.get("goods_price", 0)) / 100,
                        "quantity": int(item.get("goods_count", 1)),
                    }
                    for item in order_data.get("item_list", [])
                ],
                "receiver_name": order_data.get("receiver_name", ""),
                "receiver_phone": order_data.get("receiver_phone", ""),
                "receiver_address": order_data.get("address", ""),
                "created_at": order_data.get("created_at", ""),
            }
        }

    async def query_logistics(self, order_id: str) -> dict:
        """查询物流: pdd.logistics.online.send.query"""
        result = await self._call_api("pdd.logistics.online.send.query", {
            "order_sn": order_id,
        })
        return result

    # ========== 售后 ==========

    async def create_refund(self, order_id: str, reason: str, amount: float, refund_type: str = "refund_only") -> dict:
        """创建退款: pdd.refund.information.add"""
        logger.info(f"拼多多创建退款: order={order_id} amount={amount}")
        result = await self._call_api("pdd.refund.information.add", {
            "order_sn": order_id,
            "refund_amount": str(int(amount * 100)),  # 转为分
            "refund_reason": reason,
            "refund_type": 1 if refund_type == "refund_only" else 2,
        })
        return result

    async def approve_return(self, refund_id: str) -> dict:
        """同意退款: pdd.refund.agree"""
        logger.info(f"拼多多同意退款: refund={refund_id}")
        return await self._call_api("pdd.refund.agree", {
            "refund_id": refund_id,
        })

    async def reject_return(self, refund_id: str, reason: str) -> dict:
        """拒绝退款: pdd.refund.rejection"""
        logger.info(f"拼多多拒绝退款: refund={refund_id}")
        return await self._call_api("pdd.refund.rejection", {
            "refund_id": refund_id,
            "reject_reason": reason,
        })

    async def modify_address(self, order_id: str, new_address: dict) -> dict:
        """修改地址: 拼多多仅待发货订单可改"""
        logger.info(f"拼多多修改地址: order={order_id}")
        return {"success": False, "error": "拼多多修改地址API需待发货状态，暂未实现"}

    # ========== 商品 ==========

    async def search_products(self, shop_id: str, keyword: str, **kwargs) -> dict:
        """搜索商品: pdd.goods.search"""
        return await self._call_api("pdd.goods.search", {
            "keyword": keyword,
            "page": kwargs.get("page", 1),
            "page_size": kwargs.get("page_size", 20),
        })

    async def get_product_detail(self, product_id: str) -> dict:
        """商品详情: pdd.goods.detail.get"""
        return await self._call_api("pdd.goods.detail.get", {
            "goods_id": product_id,
        })

    async def get_all_products(self, shop_id: str, page: int = 1, page_size: int = 50) -> dict:
        """全店商品列表: pdd.goods.list.get"""
        return await self._call_api("pdd.goods.list.get", {
            "page": page,
            "page_size": page_size,
        })

    # ========== 买家信息 ==========

    async def get_buyer_info(self, buyer_id: str) -> dict:
        return {"success": True, "buyer": {"buyer_id": buyer_id}}

    # ========== 工具方法 ==========

    def _map_status(self, status_code: int) -> str:
        """拼多多订单状态映射"""
        status_map = {
            0: "待付款",
            1: "待发货",
            2: "已发货",
            3: "已签收",
            4: "已完成",
            5: "已关闭",
        }
        return status_map.get(status_code, f"未知({status_code})")
