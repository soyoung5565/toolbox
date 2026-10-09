"""LLM服务层 — 可插拔Provider架构

客户可自定义LLM，只需配置 provider/model/api_key/base_url。
内置支持: MIMO、DeepSeek、OpenAI兼容接口。

设计原则:
1. 统一接口: 所有Provider实现LLMProvider抽象类
2. 配置驱动: 从config.yaml或数据库读取店铺级LLM配置
3. 支持工具调用: Agent需要function calling能力
4. 流式输出: 支持SSE流式回复（后续）
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass, field
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    """统一消息格式"""
    role: str          # system / user / assistant / tool
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None


@dataclass
class LLMTool:
    """工具定义（传给LLM做function calling）"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema


@dataclass
class LLMResponse:
    """统一响应格式"""
    content: str
    tool_calls: Optional[List[Dict]] = None
    usage: Optional[Dict] = None
    model: str = ""
    provider: str = ""


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: str = "mimo"       # mimo / deepseek / openai / custom
    model: str = "mimo-v2.5"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.3
    max_tokens: int = 2048
    timeout: int = 30


class LLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMTool]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """发送对话请求
        
        Args:
            messages: 对话历史
            tools: 可调用的工具列表（function calling）
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大token
        
        Returns:
            LLMResponse 包含回复内容和工具调用请求
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMTool]] = None,
    ) -> AsyncIterator[str]:
        """流式对话（SSE）"""
        yield ""
        return

    def _format_tools_for_api(self, tools: List[LLMTool]) -> List[Dict]:
        """将工具定义转为OpenAI兼容格式"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            }
            for tool in tools
        ]

    def _format_messages_for_api(self, messages: List[LLMMessage]) -> List[Dict]:
        """将消息转为OpenAI兼容格式"""
        result = []
        for msg in messages:
            entry = {"role": msg.role, "content": msg.content}
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            result.append(entry)
        return result
