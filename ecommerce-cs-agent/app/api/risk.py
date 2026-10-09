"""风控评估API — Dify/Agent调用此接口评估退款风险"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.services.risk_engine import assess_refund_risk, RefundContext, Decision

logger = logging.getLogger(__name__)
router = APIRouter()


class RiskAssessRequest(BaseModel):
    """风控评估请求"""
    order_id: str
    platform: str
    order_amount: float
    refund_amount: float
    reason: str
    order_status: str = "已签收"
    days_since_delivery: int = 0
    buyer_refund_rate: float = 0.0
    buyer_refund_count_7d: int = 0
    max_return_days: int = 15
    product_category: str = ""
    account_age_days: int = 365


class RiskAssessResponse(BaseModel):
    """风控评估结果"""
    decision: str           # auto_approve / auto_reject / need_review / negotiate
    risk_level: str         # low / medium / high
    risk_score: float       # 0-1
    reasons: list[str]      # 决策原因列表
    suggested_action: str   # 建议操作
    auto_approve: bool      # 是否可自动执行


@router.post("/assess", response_model=RiskAssessResponse)
async def assess_risk(req: RiskAssessRequest):
    """评估退款风险，返回决策建议
    
    用于：
    1. Dify工作流中调用，判断退款是否可自动处理
    2. Agent在回复客户前评估风险等级
    3. 转人工时附带风险评估结果
    """
    ctx = RefundContext(
        order_id=req.order_id,
        order_amount=req.order_amount,
        refund_amount=req.refund_amount,
        reason=req.reason,
        order_status=req.order_status,
        days_since_delivery=req.days_since_delivery,
        buyer_refund_rate=req.buyer_refund_rate,
        buyer_refund_count_7d=req.buyer_refund_count_7d,
        max_return_days=req.max_return_days,
        product_category=req.product_category,
        account_age_days=req.account_age_days,
    )

    decision = assess_refund_risk(ctx)

    # 计算风险等级和分数
    risk_score = _calculate_risk_score(ctx)
    risk_level = "low" if risk_score < 0.3 else ("medium" if risk_score < 0.7 else "high")

    reasons = _get_decision_reasons(ctx, decision)

    return RiskAssessResponse(
        decision=decision.value,
        risk_level=risk_level,
        risk_score=risk_score,
        reasons=reasons,
        suggested_action=_get_suggested_action(decision),
        auto_approve=decision in (Decision.AUTO_APPROVE,),
    )


def _calculate_risk_score(ctx: RefundContext) -> float:
    """计算综合风险分数 (0-1)"""
    score = 0.0

    # 买家退货率
    if ctx.buyer_refund_rate > 0.5:
        score += 0.35
    elif ctx.buyer_refund_rate > 0.3:
        score += 0.2
    elif ctx.buyer_refund_rate > 0.1:
        score += 0.05

    # 近7天退款频率
    if ctx.buyer_refund_count_7d >= 5:
        score += 0.3
    elif ctx.buyer_refund_count_7d >= 3:
        score += 0.2
    elif ctx.buyer_refund_count_7d >= 1:
        score += 0.05

    # 退款金额
    if ctx.refund_amount > 1000:
        score += 0.2
    elif ctx.refund_amount > 500:
        score += 0.15
    elif ctx.refund_amount > 200:
        score += 0.1

    # 新账号
    if ctx.account_age_days < 7:
        score += 0.15
    elif ctx.account_age_days < 30:
        score += 0.05

    return min(score, 1.0)


def _get_decision_reasons(ctx: RefundContext, decision: Decision) -> list[str]:
    """获取决策原因说明"""
    reasons = []

    if decision == Decision.AUTO_REJECT:
        reasons.append(f"超过售后期限（签收{ctx.days_since_delivery}天 > 限制{ctx.max_return_days}天）")

    if decision == Decision.NEED_REVIEW:
        if ctx.buyer_refund_rate > 0.3:
            reasons.append(f"买家退货率异常（{ctx.buyer_refund_rate:.0%} > 30%）")
        if ctx.buyer_refund_count_7d >= 3:
            reasons.append(f"近7天退款次数过多（{ctx.buyer_refund_count_7d}次 ≥ 3次）")
        if ctx.refund_amount > 500:
            reasons.append(f"退款金额较大（¥{ctx.refund_amount} > ¥500）")
        if ctx.account_age_days < 7:
            reasons.append(f"新注册账号（{ctx.account_age_days}天 < 7天）")

    if decision == Decision.AUTO_APPROVE:
        if ctx.reason in ["质量问题", "发错货", "物流损坏", "少件"]:
            reasons.append(f"质量问题类退款，自动同意")
        if ctx.refund_amount <= 200 and ctx.reason == "七天无理由":
            reasons.append(f"小额七天无理由退款，自动同意")
        if ctx.order_status == "待发货":
            reasons.append("未发货订单，自动同意")

    if decision == Decision.NEGOTIATE:
        reasons.append("中等风险，建议与买家协商解决方案")

    return reasons


def _get_suggested_action(decision: Decision) -> str:
    """获取建议操作"""
    actions = {
        Decision.AUTO_APPROVE: "自动同意退款",
        Decision.AUTO_REJECT: "自动拒绝（超出售后期）",
        Decision.NEED_REVIEW: "提交人工审核",
        Decision.NEGOTIATE: "与买家协商（建议提供部分退款或换货方案）",
    }
    return actions.get(decision, "未知操作")
