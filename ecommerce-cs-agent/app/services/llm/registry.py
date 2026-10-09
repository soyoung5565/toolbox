"""LLM Provider注册表 — 工厂模式，配置驱动

客户通过config.yaml或数据库配置自己的LLM:
  provider: mimo / deepseek / openai / custom
  model: 模型名称
  api_key: API密钥
  base_url: API地址（自定义时必填）
"""

import logging
from typing import Dict, Optional, Type

from app.services.llm.base import LLMProvider, LLMConfig
from app.services.llm.mimo_provider import MIMOProvider
from app.services.llm.openai_provider import OpenAICompatibleProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

# Provider注册表
_PROVIDERS: Dict[str, Type[LLMProvider]] = {
    "mimo": MIMOProvider,
    "deepseek": OpenAICompatibleProvider,
    "openai": OpenAICompatibleProvider,
    "custom": OpenAICompatibleProvider,
}

# 已实例化的Provider缓存
_instances: Dict[str, LLMProvider] = {}


def get_llm_provider(
    provider: str = None,
    model: str = None,
    api_key: str = None,
    base_url: str = None,
) -> LLMProvider:
    """获取LLM Provider实例
    
    优先使用传入参数，其次从settings读取全局配置。
    支持店铺级自定义（数据库中的shop_llm_config表）。
    """
    provider = provider or settings.LLM_PROVIDER
    model = model or settings.LLM_MODEL
    api_key = api_key or settings.LLM_API_KEY
    base_url = base_url or settings.LLM_BASE_URL

    if not api_key:
        logger.warning("LLM API Key未配置，使用Mock Provider")
        return MockLLMProvider(LLMConfig(provider="mock", model="mock"))

    cache_key = f"{provider}:{model}:{api_key[:8]}"
    if cache_key not in _instances:
        if provider not in _PROVIDERS:
            logger.warning(f"未知Provider '{provider}'，使用OpenAI兼容接口")
            provider = "custom"

        config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        _instances[cache_key] = _PROVIDERS[provider](config)
        logger.info(f"创建LLM Provider: {provider} / {model}")

    return _instances[cache_key]


def get_llm_for_shop(shop_config: dict) -> LLMProvider:
    """根据店铺配置获取LLM Provider
    
    店铺可以在数据库中配置自己的LLM:
    {
        "llm_provider": "deepseek",
        "llm_model": "deepseek-chat",
        "llm_api_key": "sk-xxx",
        "llm_base_url": "https://api.deepseek.com"
    }
    """
    return get_llm_provider(
        provider=shop_config.get("llm_provider"),
        model=shop_config.get("llm_model"),
        api_key=shop_config.get("llm_api_key"),
        base_url=shop_config.get("llm_base_url"),
    )


class MockLLMProvider(LLMProvider):
    """Mock Provider — 无API Key时用于本地测试
    
    返回预设回复，不调用任何外部API。
    """

    async def chat(
        self,
        messages,
        tools=None,
        temperature=None,
        max_tokens=None,
    ):
        from app.services.llm.base import LLMResponse
        user_msg = ""
        for msg in reversed(messages):
            if msg.role == "user":
                user_msg = msg.content
                break

        # 根据用户消息返回模拟回复
        if any(kw in user_msg for kw in ["退款", "退货", "退换"]):
            reply = "好的，我来帮您处理售后问题。请提供您的订单号，我为您查询。"
        elif any(kw in user_msg for kw in ["多少钱", "价格", "有货"]):
            reply = "您好！这款商品目前售价XX元，库存充足。需要我为您详细介绍吗？"
        elif any(kw in user_msg for kw in ["推荐", "还有"]):
            reply = "为您推荐以下几款热销商品，性价比都很高哦！"
        else:
            reply = "您好！有什么可以帮到您的吗？"

        return LLMResponse(
            content=reply,
            tool_calls=None,
            model="mock",
            provider="mock",
        )

    async def chat_stream(self, messages, tools=None):
        yield "Mock流式回复暂未实现"
