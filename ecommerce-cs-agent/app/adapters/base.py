"""电商平台适配器基类 — 所有平台适配器的统一接口"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PlatformConfig:
    """平台配置"""
    app_key: str = ""
    app_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""
    shop_id: str = ""
    callback_url: str = ""


class EcommerceAdapter(ABC):
    """电商平台适配器抽象基类
    
    每个平台（淘宝/拼多多/抖店/京东）实现此接口，
    提供统一的消息收发、订单查询、商品管理、售后操作能力。
    """

    def __init__(self, config: PlatformConfig):
        self.config = config
        self._access_token = config.access_token

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台名称标识"""
        pass

    # ========== 认证 ==========

    @abstractmethod
    async def auth(self, shop_id: str) -> dict:
        """平台OAuth授权
        
        Returns:
            {"access_token": "...", "refresh_token": "...", "expires_in": 7200}
        """
        pass

    @abstractmethod
    async def refresh_access_token(self) -> dict:
        """刷新access_token"""
        pass

    # ========== 消息 ==========

    @abstractmethod
    async def send_message(self, shop_id: str, buyer_id: str, content: str, msg_type: str = "text") -> dict:
        """发送消息给买家
        
        Args:
            shop_id: 店铺ID
            buyer_id: 买家ID
            content: 消息内容
            msg_type: 消息类型(text/image/product_card)
        """
        pass

    @abstractmethod
    async def get_message_history(self, shop_id: str, buyer_id: str, limit: int = 20) -> list:
        """获取与买家的聊天记录"""
        pass

    # ========== 订单 ==========

    @abstractmethod
    async def query_order(self, order_id: str) -> dict:
        """查询订单详情
        
        Returns:
            {
                "order_id": "...",
                "status": "已签收",
                "total_amount": 99.00,
                "payment_amount": 89.00,
                "products": [...],
                "receiver": {...},
                "created_at": "...",
                "delivered_at": "..."
            }
        """
        pass

    @abstractmethod
    async def query_logistics(self, order_id: str) -> dict:
        """查询物流信息
        
        Returns:
            {
                "company": "圆通速递",
                "tracking_no": "YT...",
                "status": "已签收",
                "tracks": [{"time": "...", "content": "..."}]
            }
        """
        pass

    # ========== 售后 ==========

    @abstractmethod
    async def create_refund(self, order_id: str, reason: str, amount: float, refund_type: str = "refund_only") -> dict:
        """创建退款申请
        
        Args:
            order_id: 订单ID
            reason: 退款原因
            amount: 退款金额
            refund_type: "refund_only"(仅退款) / "return_refund"(退货退款)
        """
        pass

    @abstractmethod
    async def approve_return(self, refund_id: str) -> dict:
        """同意退货退款"""
        pass

    @abstractmethod
    async def reject_return(self, refund_id: str, reason: str) -> dict:
        """拒绝退货退款"""
        pass

    @abstractmethod
    async def modify_address(self, order_id: str, new_address: dict) -> dict:
        """修改收货地址（仅限未发货订单）
        
        Args:
            new_address: {"name": "...", "phone": "...", "province": "...", "city": "...", "district": "...", "detail": "..."}
        """
        pass

    # ========== 商品 ==========

    @abstractmethod
    async def search_products(self, shop_id: str, keyword: str, **kwargs) -> dict:
        """搜索店铺内商品"""
        pass

    @abstractmethod
    async def get_product_detail(self, product_id: str) -> dict:
        """获取商品详情"""
        pass

    @abstractmethod
    async def get_all_products(self, shop_id: str, page: int = 1, page_size: int = 50) -> dict:
        """获取全店商品列表（用于知识库同步）
        
        Returns:
            {
                "products": [...],
                "total": 100,
                "page": 1,
                "page_size": 50
            }
        """
        pass

    # ========== 买家信息 ==========

    @abstractmethod
    async def get_buyer_info(self, buyer_id: str) -> dict:
        """获取买家信息（退货率、订单数等）"""
        pass

    # ========== 工具方法 ==========

    def _sign(self, params: dict) -> str:
        """API签名（子类可覆盖）"""
        raise NotImplementedError("子类需实现签名逻辑")
