"""淘宝/天猫适配器 — 对接 TOP (Taobao Open Platform)

API文档: https://open.taobao.com/api.htm
签名方式: MD5 (参数按key排序拼接 + app_secret)

主要API:
- taobao.trade.get → 查询订单
- taobao.logistics.trace.search → 查询物流
- taobao.refund.agree → 同意退款
- taobao.refund.refuse → 拒绝退款
- taobao.items.onsale.get → 在售商品列表
- taobao.item.get → 商品详情
"""

import hashlib
import time
import logging
from typing import Optional, Dict, Any
import httpx

from app.adapters.base import EcommerceAdapter, PlatformConfig
from app.core.config import settings

logger = logging.getLogger(__name__)


class TaobaoAdapter(EcommerceAdapter):
    """淘宝/天猫适配器"""

    BASE_URL = "https://eco.taobao.com/router/rest"

    def __init__(self, config: PlatformConfig = None):
        if config is None:
            config = PlatformConfig(
                app_key=settings.TAOBAO_APP_KEY,
                app_secret=settings.TAOBAO_APP_SECRET,
            )
        super().__init__(config)
        self._tokens: Dict[str, dict] = {}  # shop_id -> token_info

    @property
    def platform_name(self) -> str:
        return "taobao"

    # ========== 认证 ==========

    async def auth(self, shop_id: str) -> dict:
        """淘宝 OAuth2 授权流程:
        1. 引导商家访问: https://oauth.taobao.com/authorize?response_type=code&client_id={app_key}&redirect_uri={callback}&view=web
        2. 回调获取 authorization_code
        3. 用 code 换 token: POST https://oauth.taobao.com/token
        """
        # TODO: 实现完整OAuth流程
        logger.info(f"淘宝授权: shop={shop_id}")
        return {"status": "pending", "message": "需引导商家完成OAuth授权"}

    async def refresh_access_token(self) -> dict:
        """刷新token"""
        # TODO: POST https://oauth.taobao.com/token
        # grant_type=refresh_token&client_id={app_key}&client_secret={app_secret}&refresh_token={refresh_token}
        return {"status": "not_implemented"}

    # ========== API调用基础 ==========

    async def _call_api(self, method: str, params: dict, shop_id: str = "") -> dict:
        """调用TOP API
        
        签名规则:
        1. 除sign外所有参数按key的ASCII码升序排序
        2. 拼接: app_secret + key1value1key2value2... + app_secret
        3. MD5后转大写
        """
        # 公共参数
        common_params = {
            "method": method,
            "app_key": self.config.app_key,
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 合并参数
        all_params = {**common_params, **params}

        # 添加token
        if shop_id and shop_id in self._tokens:
            all_params["session"] = self._tokens[shop_id].get("access_token", "")
        elif self._access_token:
            all_params["session"] = self._access_token

        # 计算签名
        all_params["sign"] = self._sign(all_params)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.BASE_URL, data=all_params)
                result = resp.json()

                # 检查错误
                if "error_response" in result:
                    error = result["error_response"]
                    logger.error(f"淘宝API错误: {method} - {error}")
                    return {"success": False, "error": error.get("msg", "未知错误"), "code": error.get("code")}

                return {"success": True, "data": result}
        except httpx.TimeoutException:
            logger.error(f"淘宝API超时: {method}")
            return {"success": False, "error": "请求超时"}
        except Exception as e:
            logger.error(f"淘宝API异常: {method} - {e}")
            return {"success": False, "error": str(e)}

    def _sign(self, params: dict) -> str:
        """计算API签名 (MD5)"""
        # 按key排序
        sorted_keys = sorted(params.keys())
        # 拼接
        sign_str = self.config.app_secret
        for key in sorted_keys:
            if key == "sign":
                continue
            value = params[key]
            if value is not None and str(value) != "":
                sign_str += f"{key}{value}"
        sign_str += self.config.app_secret
        # MD5
        return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

    # ========== 消息 ==========

    async def send_message(self, shop_id: str, buyer_id: str, content: str, msg_type: str = "text") -> dict:
        """发送消息给买家
        
        TODO: 使用淘宝消息发送API (需申请消息权限)
        暂用千牛API或淘宝站内信
        """
        logger.info(f"淘宝发送消息: shop={shop_id} -> buyer={buyer_id}: {content[:30]}")
        # TODO: 实际实现
        # 可能的API: taobao.miniapp.message.send 或 通过千牛WebSocket
        return {"success": False, "error": "消息发送需对接千牛API，暂未实现"}

    async def get_message_history(self, shop_id: str, buyer_id: str, limit: int = 20) -> list:
        """获取聊天记录"""
        logger.info(f"淘宝获取聊天记录: shop={shop_id} buyer={buyer_id}")
        return []

    # ========== 订单 ==========

    async def query_order(self, order_id: str) -> dict:
        """查询订单详情
        
        API: taobao.trade.get
        参数: fields=交易结构字段, tid=订单号
        """
        result = await self._call_api("taobao.trade.get", {
            "fields": "tid,status,payment,created,orders.price,orders.num,orders.title,"
                      "orders.sku_properties_name,receiver_name,receiver_state,receiver_city,"
                      "receiver_district,receiver_address,receiver_mobile,seller_memo",
            "tid": order_id,
        })

        if not result.get("success"):
            return result

        # 解析返回数据
        trade = result["data"].get("trade_get_response", {}).get("trade", {})
        if not trade:
            return {"success": False, "error": "订单不存在"}

        orders = trade.get("orders", {}).get("order", [])
        products = []
        for order in orders:
            products.append({
                "name": order.get("title", ""),
                "sku": order.get("sku_properties_name", ""),
                "price": float(order.get("price", 0)),
                "quantity": int(order.get("num", 1)),
            })

        return {
            "success": True,
            "order": {
                "order_id": trade.get("tid", order_id),
                "status": self._map_order_status(trade.get("status", "")),
                "total_amount": float(trade.get("payment", 0)),
                "products": products,
                "receiver_name": trade.get("receiver_name", ""),
                "receiver_phone": trade.get("receiver_mobile", ""),
                "receiver_address": (
                    f"{trade.get('receiver_state', '')}"
                    f"{trade.get('receiver_city', '')}"
                    f"{trade.get('receiver_district', '')}"
                    f"{trade.get('receiver_address', '')}"
                ),
                "created_at": trade.get("created", ""),
                "seller_memo": trade.get("seller_memo", ""),
            }
        }

    async def query_logistics(self, order_id: str) -> dict:
        """查询物流信息
        
        API: taobao.logistics.trace.search
        """
        result = await self._call_api("taobao.logistics.trace.search", {
            "tid": order_id,
        })

        if not result.get("success"):
            return result

        traces_data = result["data"].get("logistics_trace_search_response", {}).get("trace_list", {}).get("transit_step_info", [])
        tracks = []
        for trace in traces_data:
            tracks.append({
                "time": trace.get("time", ""),
                "content": trace.get("desc", ""),
            })

        return {
            "success": True,
            "logistics": {
                "company": "",
                "tracking_no": "",
                "status": tracks[-1]["content"] if tracks else "暂无物流信息",
                "tracks": tracks,
            }
        }

    # ========== 售后 ==========

    async def create_refund(self, order_id: str, reason: str, amount: float, refund_type: str = "refund_only") -> dict:
        """创建退款申请
        
        API: taobao.refund.apply (仅退款) / taobao.rp.returngoods.agree (退货退款)
        """
        logger.info(f"淘宝创建退款: order={order_id} amount={amount} reason={reason}")
        result = await self._call_api("taobao.refund.apply", {
            "tid": order_id,
            "refund_fee": str(amount),
            "reason": reason,
            "refund_type": "0" if refund_type == "refund_only" else "1",
        })
        return result

    async def approve_return(self, refund_id: str) -> dict:
        """同意退款
        
        API: taobao.refund.agree
        """
        logger.info(f"淘宝同意退款: refund={refund_id}")
        result = await self._call_api("taobao.refund.agree", {
            "refund_id": refund_id,
        })
        return result

    async def reject_return(self, refund_id: str, reason: str) -> dict:
        """拒绝退款
        
        API: taobao.refund.refuse
        """
        logger.info(f"淘宝拒绝退款: refund={refund_id} reason={reason}")
        result = await self._call_api("taobao.refund.refuse", {
            "refund_id": refund_id,
            "refuse_reason": reason,
        })
        return result

    async def modify_address(self, order_id: str, new_address: dict) -> dict:
        """修改收货地址
        
        淘宝没有直接的修改地址API，通过卖家备注实现
        API: taobao.trade.memo.update
        """
        address_str = (
            f"【地址变更】{new_address.get('name', '')} {new_address.get('phone', '')} "
            f"{new_address.get('province', '')}{new_address.get('city', '')}"
            f"{new_address.get('district', '')}{new_address.get('detail', '')}"
        )
        logger.info(f"淘宝修改地址: order={order_id} -> {address_str[:50]}")
        result = await self._call_api("taobao.trade.memo.update", {
            "tid": order_id,
            "memo": address_str,
        })
        return result

    # ========== 商品 ==========

    async def search_products(self, shop_id: str, keyword: str, **kwargs) -> dict:
        """搜索店铺商品
        
        API: taobao.items.onsale.get
        """
        result = await self._call_api("taobao.items.onsale.get", {
            "fields": "num_iid,title,price,num,pic_url,approve_status",
            "q": keyword,
            "page_size": kwargs.get("page_size", 20),
            "page_no": kwargs.get("page_no", 1),
        })
        return result

    async def get_product_detail(self, product_id: str) -> dict:
        """获取商品详情
        
        API: taobao.item.get
        """
        result = await self._call_api("taobao.item.get", {
            "fields": "num_iid,title,desc,price,num,pic_url,props_name,approve_status,stuff_status",
            "num_iid": product_id,
        })
        return result

    async def get_all_products(self, shop_id: str, page: int = 1, page_size: int = 50) -> dict:
        """获取全店商品列表"""
        result = await self._call_api("taobao.items.onsale.get", {
            "fields": "num_iid,title,price,num,pic_url,approve_status",
            "page_size": page_size,
            "page_no": page,
        })
        return result

    # ========== 买家信息 ==========

    async def get_buyer_info(self, buyer_id: str) -> dict:
        """获取买家信息"""
        # 淘宝API不直接提供买家退货率，需从订单历史统计
        logger.info(f"淘宝获取买家信息: {buyer_id}")
        return {
            "success": True,
            "buyer": {
                "buyer_id": buyer_id,
                "total_orders": 0,
                "total_refunds": 0,
                "refund_rate": 0.0,
                "refund_count_7d": 0,
                "account_age_days": 365,
            },
            "note": "需从历史订单统计"
        }

    # ========== 工具方法 ==========

    def _map_order_status(self, taobao_status: str) -> str:
        """淘宝订单状态映射"""
        status_map = {
            "WAIT_BUYER_PAY": "待付款",
            "WAIT_SELLER_SEND_GOODS": "待发货",
            "WAIT_BUYER_CONFIRM_GOODS": "已发货",
            "TRADE_BUYER_SIGNED": "已签收",
            "TRADE_FINISHED": "已完成",
            "TRADE_CLOSED": "已关闭",
            "TRADE_CLOSED_BY_TAOBAO": "已关闭",
        }
        return status_map.get(taobao_status, taobao_status)
