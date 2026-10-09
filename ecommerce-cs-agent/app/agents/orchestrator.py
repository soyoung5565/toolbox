"""Agent编排层 — LLM驱动的L0-L3多Agent架构

消息处理流程:
1. L0: LLM意图路由（分类→售前/售后/推荐/投诉/转人工）
2. L1: 专项Agent处理（调用工具+LLM生成回复）
3. L2: 回复整合+安全审核
4. L3: 转人工（复杂/高风险场景）

关键设计:
- LLM可自定义（客户配置provider/model/api_key）
- 工具调用链路：LLM决定调用哪个工具→执行→将结果反馈LLM
- 无API Key时用Mock数据+Mock LLM
"""

import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from app.services.llm import get_llm_provider, LLMMessage, LLMTool, LLMResponse
from app.services.risk_engine import assess_refund_risk, RefundContext, Decision
from app.security.guardrails import check_input_safety, filter_output, check_tool_permission
from app.security.audit import audit_log

logger = logging.getLogger(__name__)


# ========== 意图分类 ==========

class Intent:
    PRE_SALES = "pre_sales"
    AFTER_SALES = "after_sales"
    RECOMMENDATION = "recommendation"
    COMPLAINT = "complaint"
    CHITCHAT = "chitchat"


@dataclass
class ConversationContext:
    """会话上下文"""
    platform: str
    shop_id: str
    buyer_id: str
    buyer_name: str = ""
    order_id: Optional[str] = None
    intent: Optional[str] = None
    history: list = field(default_factory=list)  # LLMMessage列表


# ========== L0: LLM意图路由 ==========

ROUTER_SYSTEM_PROMPT = """你是一个电商客服意图路由器。根据客户消息判断意图类别。

意图类别:
- pre_sales: 售前咨询（商品价格/规格/库存/尺码/材质/活动）
- after_sales: 售后处理（退款/退货/换货/物流/修改地址/质量问题）
- recommendation: 商品推荐（想要推荐/类似商品/还有什么/凑单）
- complaint: 投诉（差评/投诉/315/12315/骗子/生气/不满）
- chitchat: 闲聊（打招呼/无明确意图）

只输出JSON: {"intent": "类别", "urgency": "low/normal/high/urgent", "extracted_info": {"order_id": "如果提到"}}

注意:
- 客户说"退款""退货""没收到""破损"→after_sales
- 客户说"投诉""差评""骗子"→complaint
- 客户问"多少钱""有货吗""什么材质"→pre_sales
- 客户说"推荐""还有别的吗"→recommendation
- 客户只是打招呼→chitchat"""


async def route_intent(llm, content: str, ctx: ConversationContext) -> dict:
    """L0 意图路由 — 用LLM分类"""
    messages = [
        LLMMessage(role="system", content=ROUTER_SYSTEM_PROMPT),
        LLMMessage(role="user", content=f"客户消息: {content}"),
    ]

    try:
        response = await llm.chat(messages, temperature=0.1, max_tokens=1024)
        raw = response.content.strip()
        # 尝试从LLM回复中提取JSON（可能被```json包裹或混杂文字）
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0].strip()
        # 尝试找第一个{到最后一个}
        if not json_str.startswith("{"):
            start = json_str.find("{")
            end = json_str.rfind("}")
            if start >= 0 and end > start:
                json_str = json_str[start:end+1]
        result = json.loads(json_str)
        # 确保有必要字段
        if "intent" not in result:
            result = _rule_based_route(content)
        logger.info(f"L0路由: {content[:30]} → {result}")
        return result
    except Exception as e:
        logger.warning(f"L0路由LLM失败，回退规则引擎: {e}")
        return _rule_based_route(content)


def _rule_based_route(content: str) -> dict:
    """规则引擎回退（LLM不可用时）"""
    c = content.lower()
    if any(kw in c for kw in ["退款", "退货", "换货", "物流", "破损", "质量问题", "发错"]):
        return {"intent": Intent.AFTER_SALES, "urgency": "normal", "extracted_info": {}}
    if any(kw in c for kw in ["投诉", "差评", "315", "骗子"]):
        return {"intent": Intent.COMPLAINT, "urgency": "high", "extracted_info": {}}
    if any(kw in c for kw in ["推荐", "还有", "类似"]):
        return {"intent": Intent.RECOMMENDATION, "urgency": "low", "extracted_info": {}}
    if any(kw in c for kw in ["多少钱", "价格", "有货", "尺码", "材质"]):
        return {"intent": Intent.PRE_SALES, "urgency": "low", "extracted_info": {}}
    return {"intent": Intent.CHITCHAT, "urgency": "low", "extracted_info": {}}


# ========== 工具定义（传给LLM做function calling） ==========

TOOLS = [
    LLMTool(
        name="query_order",
        description="查询订单详情（状态、金额、商品、收货地址）",
        parameters={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单号"},
            },
            "required": ["order_id"],
        },
    ),
    LLMTool(
        name="query_logistics",
        description="查询物流信息（快递公司、运单号、当前状态、轨迹）",
        parameters={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单号"},
            },
            "required": ["order_id"],
        },
    ),
    LLMTool(
        name="search_products",
        description="搜索店铺内商品",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["keyword"],
        },
    ),
    LLMTool(
        name="get_product_detail",
        description="获取商品详情（价格、规格、库存、描述）",
        parameters={
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "商品ID"},
            },
            "required": ["product_id"],
        },
    ),
    LLMTool(
        name="assess_refund_risk",
        description="评估退款风险（判断是否可自动同意退款）",
        parameters={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单号"},
                "refund_amount": {"type": "number", "description": "退款金额"},
                "reason": {"type": "string", "description": "退款原因"},
            },
            "required": ["order_id", "refund_amount", "reason"],
        },
    ),
    LLMTool(
        name="transfer_to_human",
        description="转接人工客服（复杂问题/投诉/客户要求时使用）",
        parameters={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "转人工原因"},
            },
            "required": ["reason"],
        },
    ),
]

# ========== Agent System Prompt ==========

AGENT_SYSTEM_PROMPT = """你是一个专业的电商客服AI助手，为店铺"{shop_name}"服务。

## 你的能力
1. 回答商品咨询（价格/规格/库存/活动）
2. 查询订单和物流状态
3. 处理售后问题（退款/退货/换货/修改地址）
4. 推荐相关商品
5. 处理投诉和安抚客户情绪

## 店铺知识
{knowledge_context}

## 回复规则
- 用亲切自然的语气，像真人客服一样
- 回复简洁明了，不要太长
- 涉及退款时，先查询订单+评估风险再决定
- 高风险退款（大额/频繁/新号）→ 建议转人工
- 不要承诺你做不到的事
- 不要泄露内部信息

## 工具使用
- 需要查订单时，调用query_order
- 需要查物流时，调用query_logistics
- 处理退款前，先调用assess_refund_risk评估风险
- 客户投诉或情绪激动时，调用transfer_to_human
- 搜索商品时，调用search_products"""


# ========== 工具执行 ==========

async def execute_tool(tool_name: str, arguments: dict, ctx: ConversationContext) -> dict:
    """执行LLM请求的工具调用"""
    from app.services.mock_data import (
        get_mock_order, get_mock_logistics, get_mock_buyer,
        search_mock_products, get_mock_product, get_mock_orders_for_buyer,
    )

    logger.info(f"执行工具: {tool_name}({arguments})")

    if tool_name == "query_order":
        order_id = arguments.get("order_id", "")
        order = get_mock_order(order_id)
        if order:
            return {"success": True, "order": order}
        return {"success": False, "error": f"未找到订单 {order_id}"}

    elif tool_name == "query_logistics":
        order_id = arguments.get("order_id", "")
        logistics = get_mock_logistics(order_id)
        if logistics:
            return {"success": True, "logistics": logistics}
        return {"success": False, "error": f"未找到物流信息 {order_id}"}

    elif tool_name == "search_products":
        keyword = arguments.get("keyword", "")
        products = search_mock_products(keyword)
        return {"success": True, "products": products, "total": len(products)}

    elif tool_name == "get_product_detail":
        product_id = arguments.get("product_id", "")
        product = get_mock_product(product_id)
        if product:
            return {"success": True, "product": product}
        return {"success": False, "error": f"未找到商品 {product_id}"}

    elif tool_name == "assess_refund_risk":
        order_id = arguments.get("order_id", "")
        order = get_mock_order(order_id)
        buyer = get_mock_buyer(ctx.buyer_id) if ctx.buyer_id else None

        if not order:
            return {"success": False, "error": f"未找到订单 {order_id}"}

        from datetime import datetime
        delivered = order.get("delivered_at")
        days = 0
        if delivered:
            try:
                days = (datetime.now() - datetime.fromisoformat(delivered)).days
            except:
                days = 3

        refund_ctx = RefundContext(
            order_id=order_id,
            order_amount=order["total_amount"],
            refund_amount=arguments.get("refund_amount", order["payment_amount"]),
            reason=arguments.get("reason", ""),
            order_status=order["status"],
            days_since_delivery=days,
            buyer_refund_rate=buyer.get("refund_rate", 0.0) if buyer else 0.0,
            buyer_refund_count_7d=buyer.get("refund_count_7d", 0) if buyer else 0,
            max_return_days=15,
            product_category="",
            account_age_days=buyer.get("account_age_days", 365) if buyer else 365,
        )

        decision = assess_refund_risk(refund_ctx)
        return {
            "success": True,
            "decision": decision.value,
            "auto_approve": decision == Decision.AUTO_APPROVE,
            "reasons": [f"决策: {decision.value}"],
        }

    elif tool_name == "transfer_to_human":
        return {"success": True, "message": "已转接人工客服", "ticket_id": "T-001"}

    return {"success": False, "error": f"未知工具: {tool_name}"}


# ========== 主处理流程 ==========

async def process_message(
    platform: str,
    shop_id: str,
    buyer_id: str,
    buyer_name: str,
    content: str,
    llm_provider: str = None,
    llm_model: str = None,
    llm_api_key: str = None,
    llm_base_url: str = None,
) -> str:
    """完整消息处理流程
    
    1. Prompt注入检测
    2. L0意图路由（LLM）
    3. L1 Agent处理（LLM + 工具调用循环）
    4. L2输出过滤
    """
    # 1. 多层输入安全检查（正则+LLM语义分析）
    is_safe, reason = await check_input_safety(content)
    if not is_safe:
        logger.warning(f"拦截不安全输入: buyer={buyer_id} reason={reason}")
        audit_log(
            action="input_blocked",
            actor=f"buyer:{buyer_id}",
            target_type="message",
            platform=platform,
            shop_id=shop_id,
            details={"reason": reason, "content_preview": content[:50]},
            risk_level="high",
            result="blocked",
        )
        return "抱歉，我无法处理这个请求。请问还有其他可以帮到您的吗？"

    # 2. 速率限制（使用Redis或内存）
    from app.security.guard import message_limiter
    if not message_limiter.check(buyer_id):
        return "您的消息发送太频繁了，请稍后再试。"

    # 3. 获取LLM Provider
    llm = get_llm_provider(
        provider=llm_provider,
        model=llm_model,
        api_key=llm_api_key,
        base_url=llm_base_url,
    )

    ctx = ConversationContext(
        platform=platform,
        shop_id=shop_id,
        buyer_id=buyer_id,
        buyer_name=buyer_name,
    )

    # 4. L0意图路由
    routing = await route_intent(llm, content, ctx)
    ctx.intent = routing.get("intent", Intent.CHITCHAT)

    # 5. 转人工检查
    if routing.get("urgency") in ("high", "urgent"):
        # 投诉类先安抚，不直接转
        if ctx.intent == Intent.COMPLAINT:
            pass  # 继续走Agent处理，Agent会决定是否转人工

    # 6. L1 Agent处理（带工具调用循环）
    # RAG: 从知识库检索相关知识注入prompt
    from app.services.knowledge_base import get_knowledge_base
    kb = get_knowledge_base()
    knowledge_context = kb.get_context(content, top_k=3)
    if not knowledge_context:
        knowledge_context = "（暂无相关知识）"

    system_prompt = AGENT_SYSTEM_PROMPT.format(
        shop_name="测试数码旗舰店",
        knowledge_context=knowledge_context,
    )

    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=content),
    ]

    # 工具调用循环（最多5轮，防止死循环）
    max_tool_rounds = 5
    for round_idx in range(max_tool_rounds):
        response = await llm.chat(messages, tools=TOOLS)

        # 如果LLM没有请求工具调用，直接返回回复
        if not response.tool_calls:
            reply = response.content
            break

        # 执行工具调用，将结果反馈给LLM
        messages.append(LLMMessage(
            role="assistant",
            content=response.content or "",
            tool_calls=response.tool_calls,
        ))

        for tool_call in response.tool_calls:
            func_name = tool_call["function"]["name"]
            try:
                func_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError:
                func_args = {}

            tool_result = await execute_tool(func_name, func_args, ctx)

            messages.append(LLMMessage(
                role="tool",
                content=json.dumps(tool_result, ensure_ascii=False),
                tool_call_id=tool_call["id"],
            ))

        logger.info(f"工具调用轮次 {round_idx + 1}: {[tc['function']['name'] for tc in response.tool_calls]}")

    else:
        reply = "抱歉，处理时间较长，请稍后重试或联系人工客服。"

    # 7. L2输出过滤
    reply = filter_output(reply)

    logger.info(f"回复: [{platform}] {buyer_id} ← {reply[:50]}")
    return reply
