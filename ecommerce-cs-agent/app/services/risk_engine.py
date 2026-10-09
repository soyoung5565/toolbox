"""售后决策引擎 — 核心差异化能力

不只是执行退款，而是权衡利弊后做决策：
1. 检查是否超过售后期
2. 检测是否恶意退货（退货率/频率/金额/新账号）
3. 根据退款原因+金额+买家画像综合判断
4. 输出决策：自动同意/自动拒绝/需审核/需协商
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class Decision(Enum):
    """退款决策"""
    AUTO_APPROVE = "auto_approve"      # 自动同意
    AUTO_REJECT = "auto_reject"        # 自动拒绝（超售后期）
    NEED_REVIEW = "need_review"        # 需人工审核
    NEGOTIATE = "negotiate"            # 需协商


@dataclass
class RefundContext:
    """退款上下文 — 做决策所需的全部信息"""
    order_id: str
    order_amount: float          # 订单总金额
    refund_amount: float         # 退款金额
    reason: str                  # 退款原因
    order_status: str            # 待发货/已发货/已签收/已完成
    days_since_delivery: int     # 签收后天数
    buyer_refund_rate: float     # 买家近30天退货率 (0-1)
    buyer_refund_count_7d: int   # 买家近7天退款次数
    max_return_days: int         # 店铺/平台售后期限
    product_category: str        # 商品类目
    account_age_days: int = 365  # 买家账号注册天数


# 质量问题类原因（通常自动同意）
QUALITY_REASONS = {"质量问题", "发错货", "物流损坏", "少件", "破损", "与描述不符"}
# 买家主观原因（需更严格审核）
SUBJECTIVE_REASONS = {"不想要", "拍错了", "不喜欢", "七天无理由"}


def assess_refund_risk(ctx: RefundContext) -> Decision:
    """退换货决策引擎 — 核心逻辑
    
    决策流程：
    1. 硬规则检查（超期→拒绝）
    2. 恶意退货检测（可疑→人工审核）
    3. 按原因+金额+状态综合判断
    """
    logger.info(
        f"风控评估: order={ctx.order_id} amount=¥{ctx.refund_amount} "
        f"reason={ctx.reason} status={ctx.order_status} "
        f"days={ctx.days_since_delivery} refund_rate={ctx.buyer_refund_rate:.0%} "
        f"refund_7d={ctx.buyer_refund_count_7d} account_age={ctx.account_age_days}d"
    )

    # ===== 第1层：硬规则 — 直接拒绝 =====
    if ctx.days_since_delivery > ctx.max_return_days:
        logger.info(f"→ AUTO_REJECT: 超过售后期({ctx.days_since_delivery} > {ctx.max_return_days}天)")
        return Decision.AUTO_REJECT

    # 待发货状态：修改地址/取消订单 → 自动同意
    if ctx.order_status == "待发货":
        logger.info("→ AUTO_APPROVE: 待发货订单")
        return Decision.AUTO_APPROVE

    # ===== 第2层：恶意退货检测 — 交人工 =====
    if _is_suspicious_buyer(ctx):
        logger.info("→ NEED_REVIEW: 疑似恶意买家")
        return Decision.NEED_REVIEW

    # ===== 第3层：按原因+金额判断 =====

    # 质量问题类 → 自动同意（不限金额，因为是卖家责任，优先于高金额检测）
    if ctx.reason in QUALITY_REASONS:
        logger.info(f"→ AUTO_APPROVE: 质量问题({ctx.reason})")
        return Decision.AUTO_APPROVE

    # 高金额 → 人工审核（非质量问题才走这里）
    if ctx.refund_amount > settings.RISK_HIGH_VALUE_THRESHOLD:
        logger.info(f"→ NEED_REVIEW: 高金额退款(¥{ctx.refund_amount} > ¥{settings.RISK_HIGH_VALUE_THRESHOLD})")
        return Decision.NEED_REVIEW

    # 新账号 + 非质量问题 → 人工审核
    if ctx.account_age_days < settings.RISK_NEW_ACCOUNT_DAYS and ctx.reason not in QUALITY_REASONS:
        logger.info(f"→ NEED_REVIEW: 新账号({ctx.account_age_days}天) + 非质量问题")
        return Decision.NEED_REVIEW

    # 小额七天无理由 → 自动同意
    if ctx.reason == "七天无理由" and ctx.refund_amount <= settings.RISK_MAX_AUTO_APPROVE_AMOUNT:
        if ctx.days_since_delivery <= 7:
            logger.info(f"→ AUTO_APPROVE: 七天无理由+小额(¥{ctx.refund_amount})")
            return Decision.AUTO_APPROVE
        else:
            logger.info(f"→ AUTO_REJECT: 七天无理由但超过7天")
            return Decision.AUTO_REJECT

    # 小额主观原因 → 自动同意
    if ctx.reason in SUBJECTIVE_REASONS and ctx.refund_amount <= settings.RISK_MAX_AUTO_APPROVE_AMOUNT:
        logger.info(f"→ AUTO_APPROVE: 小额主观原因({ctx.reason}, ¥{ctx.refund_amount})")
        return Decision.AUTO_APPROVE

    # 中等金额 → 需协商
    if ctx.refund_amount > settings.RISK_MAX_AUTO_APPROVE_AMOUNT:
        logger.info(f"→ NEGOTIATE: 中等金额(¥{ctx.refund_amount} > ¥{settings.RISK_MAX_AUTO_APPROVE_AMOUNT})")
        return Decision.NEGOTIATE

    # 默认 → 协商
    logger.info("→ NEGOTIATE: 默认协商")
    return Decision.NEGOTIATE


def _is_suspicious_buyer(ctx: RefundContext) -> bool:
    """检测是否疑似恶意买家
    
    恶意退货特征：
    1. 近30天退货率 > 30%
    2. 近7天退款次数 >= 3次
    3. 近30天退款总金额 > 2000元
    4. 注册不到7天的新号 + 非质量问题
    """
    # 高退货率
    if ctx.buyer_refund_rate > settings.RISK_SUSPICIOUS_REFUND_RATE:
        logger.info(f"  疑似恶意: 退货率{ctx.buyer_refund_rate:.0%} > {settings.RISK_SUSPICIOUS_REFUND_RATE:.0%}")
        return True

    # 高频退款
    if ctx.buyer_refund_count_7d >= settings.RISK_SUSPICIOUS_REFUND_COUNT_7D:
        logger.info(f"  疑似恶意: 7天退款{ctx.buyer_refund_count_7d}次 >= {settings.RISK_SUSPICIOUS_REFUND_COUNT_7D}次")
        return True

    # 新号 + 大额退款
    if ctx.account_age_days < 7 and ctx.refund_amount > 100:
        logger.info(f"  疑似恶意: 新号({ctx.account_age_days}天) + 大额(¥{ctx.refund_amount})")
        return True

    return False


def check_daily_refund_limit(shop_id: str, today_total: float) -> bool:
    """检查单日自动退款总额是否超限
    
    Returns:
        True = 在限额内，可以继续自动退款
        False = 已超限，需人工审核
    """
    if today_total >= settings.RISK_MAX_DAILY_AUTO_REFUND:
        logger.warning(f"店铺{shop_id} 今日自动退款已达限额: ¥{today_total} >= ¥{settings.RISK_MAX_DAILY_AUTO_REFUND}")
        return False
    return True
