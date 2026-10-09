"""统一消息格式 — 所有平台消息的标准化表示"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Platform(str, Enum):
    """支持的电商平台"""
    TAOBAO = "taobao"       # 淘宝/天猫
    PDD = "pdd"             # 拼多多
    DOUYIN = "douyin"       # 抖音电商/抖店
    JD = "jd"               # 京东
    XIANFISH = "xianyu"     # 闲鱼
    ALI1688 = "1688"        # 1688


class MessageType(str, Enum):
    """消息类型"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    PRODUCT_CARD = "product_card"
    ORDER_CARD = "order_card"
    SYSTEM = "system"


class MessageDirection(str, Enum):
    """消息方向"""
    INBOUND = "inbound"     # 买家→卖家
    OUTBOUND = "outbound"   # 卖家→买家


class UnifiedMessage(BaseModel):
    """统一消息格式 — 各平台消息转为此格式后送入Agent处理"""
    platform: Platform
    shop_id: str
    buyer_id: str
    buyer_name: str = ""
    direction: MessageDirection = MessageDirection.INBOUND
    message_type: MessageType = MessageType.TEXT
    content: str
    raw_data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    conversation_id: Optional[str] = None

    class Config:
        use_enum_values = True


class UnifiedReply(BaseModel):
    """统一回复格式 — Agent生成的回复转为此格式后发送到各平台"""
    platform: Platform
    shop_id: str
    buyer_id: str
    message_type: MessageType = MessageType.TEXT
    content: str
    metadata: Optional[Dict[str, Any]] = None


# ========== 订单相关 ==========

class OrderStatus(str, Enum):
    """订单状态"""
    PENDING_PAYMENT = "待付款"
    PENDING_SHIPMENT = "待发货"
    SHIPPED = "已发货"
    DELIVERED = "已签收"
    COMPLETED = "已完成"
    CLOSED = "已关闭"
    REFUNDING = "退款中"
    REFUNDED = "已退款"


class OrderInfo(BaseModel):
    """订单信息"""
    order_id: str
    platform: Platform
    shop_id: str
    buyer_id: str
    status: OrderStatus
    total_amount: float
    payment_amount: float
    created_at: datetime
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    products: List[Dict[str, Any]] = []
    receiver_name: str = ""
    receiver_phone: str = ""
    receiver_address: str = ""
    logistics_company: str = ""
    logistics_no: str = ""


# ========== 退款相关 ==========

class RefundType(str, Enum):
    """退款类型"""
    REFUND_ONLY = "refund_only"         # 仅退款
    RETURN_REFUND = "return_refund"     # 退货退款


class RefundReason(str, Enum):
    """退款原因"""
    QUALITY_ISSUE = "质量问题"
    WRONG_ITEM = "发错货"
    LOGISTICS_DAMAGE = "物流损坏"
    MISSING_PARTS = "少件"
    SEVEN_DAY_NO_REASON = "七天无理由"
    NOT_WANTED = "不想要"
    WRONG_ORDER = "拍错了"
    OTHER = "其他"


class RefundRequest(BaseModel):
    """退款请求"""
    order_id: str
    platform: Platform
    shop_id: str
    buyer_id: str
    refund_type: RefundType
    reason: RefundReason
    amount: float
    description: str = ""
    images: List[str] = []
