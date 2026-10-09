"""对话测试API — 无需Webhook即可测试完整Agent链路

POST /api/chat 发送消息，走完 LLM路由→工具调用→回复 的全流程。
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    """对话请求"""
    message: str
    platform: str = "pdd"
    shop_id: str = "pdd_shop_001"
    buyer_id: str = "buyer_001"
    buyer_name: str = "张三"
    # 客户自定义LLM配置（可选，不填用全局配置）
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None


class ChatResponse(BaseModel):
    """对话响应"""
    reply: str
    intent: str = ""
    tools_used: list = []


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """测试对话 — 完整Agent链路
    
    流程: 消息 → Prompt注入检测 → L0意图路由(LLM) → L1 Agent处理(LLM+工具) → L2输出过滤 → 回复
    
    支持客户自定义LLM:
    - 不传llm_*参数: 使用全局配置（MIMO）
    - 传llm_*参数: 使用客户自己的模型（DeepSeek/OpenAI/任何兼容接口）
    """
    from app.agents.orchestrator import process_message

    reply = await process_message(
        platform=req.platform,
        shop_id=req.shop_id,
        buyer_id=req.buyer_id,
        buyer_name=req.buyer_name,
        content=req.message,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
        llm_api_key=req.llm_api_key,
        llm_base_url=req.llm_base_url,
    )

    return ChatResponse(
        reply=reply,
        intent="",  # TODO: 从process_message返回中提取
    )
