"""输入验证 + 数据脱敏 — 防止注入攻击和数据泄露"""

import re
import logging
from typing import Optional
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


# ========== 输入验证模型 ==========

class SafeString(str):
    """安全字符串 — 去除危险字符"""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise TypeError("string required")
        # 去除控制字符
        v = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v)
        # 限制长度
        if len(v) > 10000:
            raise ValueError("string too long (max 10000)")
        return v


class WebhookPayload(BaseModel):
    """Webhook通用验证模型"""
    class Config:
        extra = "allow"  # 允许平台特有字段

    @validator("*", pre=True)
    def sanitize_strings(cls, v):
        if isinstance(v, str):
            # 去除控制字符
            v = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v)
        return v


class ChatInput(BaseModel):
    """对话输入验证"""
    message: str = Field(..., min_length=1, max_length=5000, description="用户消息")
    platform: str = Field(default="pdd", pattern=r"^(pdd|taobao|douyin|jd|xianyu)$")
    shop_id: str = Field(default="pdd_shop_001", min_length=1, max_length=100)
    buyer_id: str = Field(default="buyer_001", min_length=1, max_length=100)
    buyer_name: str = Field(default="", max_length=200)
    llm_provider: Optional[str] = Field(default=None, max_length=50)
    llm_model: Optional[str] = Field(default=None, max_length=100)
    llm_api_key: Optional[str] = Field(default=None, max_length=200)
    llm_base_url: Optional[str] = Field(default=None, max_length=500)

    @validator("message")
    def sanitize_message(cls, v):
        # 去除控制字符
        v = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v)
        return v.strip()

    @validator("llm_base_url")
    def validate_url(cls, v):
        if v and not v.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("base_url必须是HTTPS或localhost")
        return v


class RiskAssessInput(BaseModel):
    """风控评估输入验证"""
    order_id: str = Field(..., min_length=1, max_length=50)
    platform: str = Field(..., pattern=r"^(pdd|taobao|douyin|jd)$")
    order_amount: float = Field(..., ge=0, le=1000000)
    refund_amount: float = Field(..., ge=0, le=1000000)
    reason: str = Field(..., min_length=1, max_length=200)
    order_status: str = Field(default="已签收", max_length=50)
    days_since_delivery: int = Field(default=0, ge=0, le=365)
    buyer_refund_rate: float = Field(default=0.0, ge=0, le=1.0)
    buyer_refund_count_7d: int = Field(default=0, ge=0, le=100)
    max_return_days: int = Field(default=15, ge=0, le=365)
    product_category: str = Field(default="", max_length=100)
    account_age_days: int = Field(default=365, ge=0, le=36500)


# ========== PII脱敏 ==========

def mask_phone(phone: str) -> str:
    """手机号脱敏: 138****1234"""
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return "****"


def mask_name(name: str) -> str:
    """姓名脱敏: 张*三"""
    if not name:
        return ""
    chars = list(name)
    if len(chars) >= 2:
        # 至少保留首尾各1个字符，中间全部替换为*
        middle_count = max(1, len(chars) - 2)
        return chars[0] + "*" * middle_count + chars[-1]
    return "*"


def mask_address(address: str) -> str:
    """地址脱敏: 广东省东莞****"""
    if not address:
        return ""
    chars = list(address)
    if len(chars) > 6:
        return "".join(chars[:6]) + "****"
    return "****"


def mask_order_id(order_id: str) -> str:
    """订单号脱敏: PDD20****01"""
    if len(order_id) > 8:
        return order_id[:4] + "****" + order_id[-2:]
    return "****"


def sanitize_log_data(data: dict) -> dict:
    """日志数据脱敏 — 自动识别并脱敏PII字段"""
    sensitive_fields = {
        "phone", "receiver_phone", "mobile", "tel",
        "address", "receiver_address",
        "name", "receiver_name", "buyer_name",
        "id_card", "identity",
        "bank_card", "card_no",
        "password", "passwd",
    }
    
    result = {}
    for key, value in data.items():
        key_lower = key.lower()
        
        if any(s in key_lower for s in ["phone", "mobile", "tel"]):
            result[key] = mask_phone(str(value)) if value else value
        elif any(s in key_lower for s in ["name"]) and "product" not in key_lower:
            result[key] = mask_name(str(value)) if value else value
        elif "address" in key_lower:
            result[key] = mask_address(str(value)) if value else value
        elif any(s in key_lower for s in ["password", "secret", "token", "key"]):
            result[key] = "****"
        else:
            result[key] = value
    
    return result
