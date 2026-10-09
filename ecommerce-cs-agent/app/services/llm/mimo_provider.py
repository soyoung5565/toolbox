"""MIMO Provider — 小米MIMO大模型

API兼容OpenAI格式，base_url: token-plan-cn.xiaomimimo.com/v1

(2026-07-09 改造为通用 minimax/OpenAI-compatible Provider)
实际上现在作为 minimax (MiniMax-M3) 的 Provider 使用 — MiniMax 同样走 OpenAI 兼容协议
(/v1/chat/completions) 且原生支持 reasoning_content 字段，与 MiMo 行为一致。
base_url 通过 LLMConfig 传入，保留名字以兼容现有调用方与配置。
"""

import logging
import httpx
import json
from typing import List, Optional, AsyncIterator

from app.services.llm.base import LLMProvider, LLMMessage, LLMTool, LLMResponse, LLMConfig

logger = logging.getLogger(__name__)


class MIMOProvider(LLMProvider):
    """通用 OpenAI 兼容 Provider (兼容 MiMo / minimax / DeepSeek 等)

    历史上专门给 MiMo 用 (MIMOProvider)，但行为其实和 OpenAI 兼容协议无差异 —
    都能正确处理 reasoning_content 字段。2026-07-09 切到 minimax 后保留类名以
    避免破坏调用方代码。
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not config.base_url:
            # 历史默认，保留兜底
            self.config.base_url = "https://api.minimaxi.com/v1"
        self._base_url = self.config.base_url.rstrip("/")

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMTool]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        url = f"{self._base_url}/chat/completions"

        payload = {
            "model": self.config.model,
            "messages": self._format_messages_for_api(messages),
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        if tools:
            payload["tools"] = self._format_tools_for_api(tools)
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            choice = data["choices"][0]
            message = choice["message"]

            # MIMO推理模型: 回复可能在reasoning_content中，content可能为空
            content = message.get("content", "") or ""
            reasoning = message.get("reasoning_content", "")
            if not content and reasoning:
                # 如果content为空但有reasoning，用reasoning的最后部分作为回复
                # 通常推理模型的结论在reasoning末尾
                content = reasoning

            tool_calls = None
            if message.get("tool_calls"):
                tool_calls = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        }
                    }
                    for tc in message["tool_calls"]
                ]

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage=data.get("usage"),
                model=data.get("model", self.config.model),
                provider="mimo",
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"MIMO API HTTP错误: {e.response.status_code} {e.response.text[:200]}")
            raise
        except Exception as e:
            logger.error(f"MIMO API异常: {e}")
            raise

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMTool]] = None,
    ) -> AsyncIterator[str]:
        url = f"{self._base_url}/chat/completions"

        payload = {
            "model": self.config.model,
            "messages": self._format_messages_for_api(messages),
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        if tools:
            payload["tools"] = self._format_tools_for_api(tools)
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                return
                            try:
                                data = json.loads(data_str)
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
        except Exception as e:
            logger.error(f"MIMO流式API异常: {e}")
            raise
