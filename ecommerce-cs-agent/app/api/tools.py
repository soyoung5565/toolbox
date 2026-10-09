"""Agent工具API — Dify/Agent通过HTTP调用这些接口执行操作"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== 请求/响应模型 ==========

class QueryOrderRequest(BaseModel):
    platform: str
    order_id: str
    shop_id: str

class QueryLogisticsRequest(BaseModel):
    platform: str
    order_id: str
    shop_id: str

class SearchProductsRequest(BaseModel):
    platform: str
    shop_id: str
    keyword: str
    category: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None

class GetProductDetailRequest(BaseModel):
    platform: str
    product_id: str

class CreateRefundRequest(BaseModel):
    platform: str
    order_id: str
    shop_id: str
    buyer_id: str
    reason: str
    amount: float
    refund_type: str = "refund_only"  # refund_only / return_refund
    description: str = ""

class ApproveReturnRequest(BaseModel):
    platform: str
    refund_id: str
    shop_id: str

class RejectReturnRequest(BaseModel):
    platform: str
    refund_id: str
    shop_id: str
    reason: str

class ModifyAddressRequest(BaseModel):
    platform: str
    order_id: str
    shop_id: str
    name: str
    phone: str
    province: str
    city: str
    district: str
    detail: str

class RecommendProductsRequest(BaseModel):
    platform: str
    shop_id: str
    buyer_id: str
    context: str = ""  # 当前咨询内容
    category: Optional[str] = None

class FollowUpRequest(BaseModel):
    platform: str
    shop_id: str
    buyer_id: str
    message: str

class TransferToHumanRequest(BaseModel):
    platform: str
    shop_id: str
    buyer_id: str
    reason: str
    priority: str = "normal"  # low / normal / high / urgent


# ========== 订单工具 ==========

@router.post("/query_order")
async def query_order(req: QueryOrderRequest):
    """查询订单详情（含状态、金额、商品、收货地址）"""
    logger.info(f"查询订单: [{req.platform}] {req.order_id}")
    # TODO: 调用对应平台适配器
    # adapter = get_adapter(req.platform, req.shop_id)
    # return await adapter.query_order(req.order_id)
    return {
        "success": True,
        "order": {
            "order_id": req.order_id,
            "platform": req.platform,
            "status": "已签收",
            "total_amount": 99.00,
            "payment_amount": 89.00,
            "products": [
                {"name": "示例商品", "sku": "默认规格", "quantity": 1, "price": 89.00}
            ],
            "receiver_name": "张三",
            "receiver_phone": "138****1234",
            "receiver_address": "广东省东莞市xxx",
            "created_at": "2026-07-01T10:00:00",
            "delivered_at": "2026-07-04T14:30:00",
        },
        "note": "⚠️ 示例数据，需接入真实平台API"
    }


@router.post("/query_logistics")
async def query_logistics(req: QueryLogisticsRequest):
    """查询物流信息（快递公司、运单号、轨迹）"""
    logger.info(f"查询物流: [{req.platform}] {req.order_id}")
    return {
        "success": True,
        "logistics": {
            "company": "圆通速递",
            "tracking_no": "YT1234567890",
            "status": "已签收",
            "tracks": [
                {"time": "2026-07-02 10:00", "content": "已揽收"},
                {"time": "2026-07-03 08:00", "content": "到达东莞转运中心"},
                {"time": "2026-07-04 14:30", "content": "已签收"},
            ]
        },
        "note": "⚠️ 示例数据，需接入真实平台API"
    }


# ========== 商品工具 ==========

@router.post("/search_products")
async def search_products(req: SearchProductsRequest):
    """搜索店铺内商品"""
    logger.info(f"搜索商品: [{req.platform}] {req.keyword}")
    return {
        "success": True,
        "products": [
            {
                "product_id": "12345",
                "title": f"与'{req.keyword}'相关的商品",
                "price": 59.00,
                "stock": 100,
                "image": "https://placeholder.com/300",
            }
        ],
        "total": 1,
        "note": "⚠️ 示例数据，需接入真实平台API"
    }


@router.post("/get_product_detail")
async def get_product_detail(req: GetProductDetailRequest):
    """获取商品详情（标题、描述、价格、库存、规格、图片）"""
    logger.info(f"商品详情: [{req.platform}] {req.product_id}")
    return {
        "success": True,
        "product": {
            "product_id": req.product_id,
            "title": "示例商品",
            "description": "这是一个示例商品描述",
            "price": 59.00,
            "stock": 100,
            "skus": [
                {"sku_id": "1", "spec": "默认", "price": 59.00, "stock": 100}
            ],
            "images": ["https://placeholder.com/300"],
            "category": "示例类目",
        },
        "note": "⚠️ 示例数据，需接入真实平台API"
    }


@router.post("/recommend_products")
async def recommend_products(req: RecommendProductsRequest):
    """商品推荐（互补/替代/凑单/上新）"""
    logger.info(f"商品推荐: [{req.platform}] buyer={req.buyer_id} context={req.context[:30]}")
    # TODO: 基于买家咨询内容 + 购买历史 + 店铺商品做智能推荐
    return {
        "success": True,
        "recommendations": [
            {"product_id": "101", "title": "相关推荐商品1", "price": 39.00, "reason": "与咨询商品互补"},
            {"product_id": "102", "title": "相关推荐商品2", "price": 69.00, "reason": "同类热销商品"},
        ],
        "note": "⚠️ 示例数据，需接入真实平台API"
    }


# ========== 售后工具 ==========

@router.post("/create_refund")
async def create_refund(req: CreateRefundRequest):
    """创建退款申请（先过风控再执行）"""
    logger.info(f"创建退款: [{req.platform}] order={req.order_id} amount={req.amount} reason={req.reason}")

    # 先调风控评估
    from app.services.risk_engine import assess_refund_risk, RefundContext, RefundReason

    ctx = RefundContext(
        order_id=req.order_id,
        order_amount=req.amount * 1.1,  # 简化，实际从订单获取
        refund_amount=req.amount,
        reason=req.reason,
        order_status="已签收",
        days_since_delivery=3,
        buyer_refund_rate=0.1,
        buyer_refund_count_7d=0,
        max_return_days=15,
        product_category="默认",
        account_age_days=365,
    )

    decision = assess_refund_risk(ctx)

    return {
        "success": True,
        "decision": decision.value,
        "refund": {
            "order_id": req.order_id,
            "amount": req.amount,
            "reason": req.reason,
            "status": "pending" if decision.value == "need_review" else "approved",
        },
        "note": "⚠️ 风控引擎已接入，需对接真实平台退款API执行"
    }


@router.post("/approve_return")
async def approve_return(req: ApproveReturnRequest):
    """同意退货退款"""
    logger.info(f"同意退款: [{req.platform}] refund={req.refund_id}")
    # TODO: 调用平台API执行同意退款
    return {
        "success": True,
        "message": "已同意退款",
        "refund_id": req.refund_id,
        "note": "⚠️ 需对接真实平台API"
    }


@router.post("/reject_return")
async def reject_return(req: RejectReturnRequest):
    """拒绝退货退款"""
    logger.info(f"拒绝退款: [{req.platform}] refund={req.refund_id} reason={req.reason}")
    # TODO: 调用平台API执行拒绝退款
    return {
        "success": True,
        "message": f"已拒绝退款，原因：{req.reason}",
        "refund_id": req.refund_id,
        "note": "⚠️ 需对接真实平台API"
    }


@router.post("/modify_address")
async def modify_address(req: ModifyAddressRequest):
    """修改收货地址（仅限未发货订单）"""
    logger.info(f"修改地址: [{req.platform}] order={req.order_id}")
    new_address = f"{req.province}{req.city}{req.district}{req.detail}"
    return {
        "success": True,
        "message": f"地址已修改为: {req.name} {req.phone} {new_address}",
        "note": "⚠️ 需对接真实平台API"
    }


# ========== 客服工具 ==========

@router.post("/follow_up")
async def follow_up(req: FollowUpRequest):
    """客户跟进（向咨询未下单客户推送消息）"""
    logger.info(f"客户跟进: [{req.platform}] buyer={req.buyer_id}")
    return {
        "success": True,
        "message": f"已向客户发送跟进消息",
        "note": "⚠️ 需对接真实平台消息API"
    }


@router.post("/transfer_to_human")
async def transfer_to_human(req: TransferToHumanRequest):
    """转人工客服"""
    logger.info(f"转人工: [{req.platform}] buyer={req.buyer_id} reason={req.reason}")
    return {
        "success": True,
        "message": "已转接人工客服",
        "ticket_id": "T-20260706-001",
        "note": "⚠️ 需对接TGO工单系统或企业微信/钉钉通知"
    }
