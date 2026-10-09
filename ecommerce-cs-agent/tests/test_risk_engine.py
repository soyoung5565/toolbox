"""售后决策引擎单元测试"""

import pytest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.risk_engine import (
    Decision,
    RefundContext,
    assess_refund_risk,
    _is_suspicious_buyer,
    check_daily_refund_limit,
)


def make_ctx(**kwargs) -> RefundContext:
    """创建测试用的RefundContext，默认值覆盖常见场景"""
    defaults = dict(
        order_id="TEST-001",
        order_amount=100.0,
        refund_amount=100.0,
        reason="七天无理由",
        order_status="已签收",
        days_since_delivery=3,
        buyer_refund_rate=0.05,
        buyer_refund_count_7d=0,
        max_return_days=15,
        product_category="服装",
        account_age_days=365,
    )
    defaults.update(kwargs)
    return RefundContext(**defaults)


class TestHardReject:
    """硬规则：超期直接拒绝"""

    def test_beyond_return_window(self):
        ctx = make_ctx(days_since_delivery=20, max_return_days=15)
        assert assess_refund_risk(ctx) == Decision.AUTO_REJECT

    def test_exactly_at_return_window(self):
        ctx = make_ctx(days_since_delivery=15, max_return_days=15, reason="不想要")
        assert assess_refund_risk(ctx) != Decision.AUTO_REJECT  # 等于期限不算超

    def test_within_return_window(self):
        ctx = make_ctx(days_since_delivery=14, max_return_days=15, reason="不想要")
        assert assess_refund_risk(ctx) != Decision.AUTO_REJECT


class TestPreShipAutoApprove:
    """待发货状态自动同意"""

    def test_pending_shipment(self):
        ctx = make_ctx(order_status="待发货", refund_amount=500)
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE


class TestSuspiciousBuyer:
    """恶意退货检测"""

    def test_high_refund_rate(self):
        ctx = make_ctx(buyer_refund_rate=0.35)
        assert assess_refund_risk(ctx) == Decision.NEED_REVIEW

    def test_normal_refund_rate(self):
        ctx = make_ctx(buyer_refund_rate=0.1)
        assert assess_refund_risk(ctx) != Decision.NEED_REVIEW  # 仅退货率不算可疑

    def test_frequent_refunds(self):
        ctx = make_ctx(buyer_refund_count_7d=4)
        assert assess_refund_risk(ctx) == Decision.NEED_REVIEW

    def test_new_account_high_refund(self):
        ctx = make_ctx(account_age_days=5, refund_amount=200)
        assert assess_refund_risk(ctx) == Decision.NEED_REVIEW

    def test_new_account_low_refund_quality_reason(self):
        """新账号但金额小且是质量问题→仍自动同意"""
        ctx = make_ctx(account_age_days=5, refund_amount=50, reason="质量问题")
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE


class TestHighValueRefund:
    """高金额退款"""

    def test_high_amount(self):
        ctx = make_ctx(refund_amount=600)
        assert assess_refund_risk(ctx) == Decision.NEED_REVIEW

    def test_medium_amount(self):
        ctx = make_ctx(refund_amount=300, reason="七天无理由")
        assert assess_refund_risk(ctx) == Decision.NEGOTIATE


class TestQualityReasons:
    """质量问题类自动同意"""

    def test_quality_issue(self):
        ctx = make_ctx(reason="质量问题", refund_amount=800)
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE

    def test_wrong_item(self):
        ctx = make_ctx(reason="发错货")
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE

    def test_logistics_damage(self):
        ctx = make_ctx(reason="物流损坏")
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE

    def test_missing_parts(self):
        ctx = make_ctx(reason="少件")
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE


class TestSevenDayNoReason:
    """七天无理由退款"""

    def test_small_amount_within_7_days(self):
        ctx = make_ctx(reason="七天无理由", refund_amount=150, days_since_delivery=5)
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE

    def test_over_7_days(self):
        ctx = make_ctx(reason="七天无理由", days_since_delivery=10)
        assert assess_refund_risk(ctx) == Decision.AUTO_REJECT


class TestSubjectiveReasons:
    """买家主观原因"""

    def test_small_amount_not_wanted(self):
        ctx = make_ctx(reason="不想要", refund_amount=50)
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE

    def test_wrong_order(self):
        ctx = make_ctx(reason="拍错了", refund_amount=80)
        assert assess_refund_risk(ctx) == Decision.AUTO_APPROVE


class TestDailyLimit:
    """单日退款限额"""

    def test_within_limit(self):
        assert check_daily_refund_limit("shop-1", 3000) is True

    def test_at_limit(self):
        assert check_daily_refund_limit("shop-1", 5000) is False

    def test_over_limit(self):
        assert check_daily_refund_limit("shop-1", 6000) is False


class TestEdgeCases:
    """边界情况"""

    def test_zero_refund_amount(self):
        ctx = make_ctx(refund_amount=0)
        # 0元退款不触发任何规则，走默认协商
        result = assess_refund_risk(ctx)
        assert result in (Decision.AUTO_APPROVE, Decision.NEGOTIATE)

    def test_all_suspicious_signals(self):
        """所有可疑信号都触发"""
        ctx = make_ctx(
            buyer_refund_rate=0.6,
            buyer_refund_count_7d=5,
            account_age_days=3,
            refund_amount=1000,
        )
        assert assess_refund_risk(ctx) == Decision.NEED_REVIEW


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
