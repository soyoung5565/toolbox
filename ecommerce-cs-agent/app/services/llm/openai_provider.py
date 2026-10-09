"""OpenAI兼容Provider — 覆盖DeepSeek/智谱/通义等所有OpenAI兼容接口

客户自定义模型时，只需设置 base_url + api_key + model 即可。
"""

import logging
import httpx
import json
from typing import List, Optional, AsyncIterator

from app.services.llm.base import LLMProvider, LLMMessage, LLMTool, LLMResponse, LLMConfig

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI兼容接口Provider
    
    适用于: DeepSeek、智谱GLM、通义千问、Moonshot、以及任何OpenAI兼容API。
    客户只需配置 base_url + api_key + model。
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        # 默认DeepSeek
        if not config.base_url:
            self.config.base_url = "https://api.deepseek.com"
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
                content=message.get("content", "") or "",
                tool_calls=tool_calls,
                usage=data.get("usage"),
                model=data.get("model", self.config.model),
                provider="openai_compatible",
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API HTTP错误: {e.response.status_code} {e.response.text[:200]}")
            raise
        except Exception as e:
            logger.error(f"LLM API异常: {e}")
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
            logger.error(f"LLM流式API异常: {e}")
            raise
