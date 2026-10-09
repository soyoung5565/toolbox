"""安全层 — Prompt注入检测 + 输出过滤 + 速率限制"""

import re
import time
import logging
from typing import Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# ========== Prompt注入检测 ==========

# 常见注入攻击模式
INJECTION_PATTERNS = [
    # 直接指令覆盖
    r"忽略(之前|上面|所有|一切)(的)?(指令|规则|提示|要求)",
    r"ignore\s+(all\s+)?(previous|above|earlier)\s+(instructions?|rules?|prompts?)",
    r"disregard\s+(all\s+)?(previous|above)\s+(instructions?|rules?)",
    r"从现在起你(是|变成|扮演)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"system\s*:\s*",
    r"assistant\s*:\s*",
    r"\[system\]",
    r"\[INST\]",
    r"<<SYS>>",
    # 诱导泄露
    r"你的(系统|初始)(提示|指令|prompt)",
    r"what\s+(is|are)\s+your\s+(system|initial)\s+(prompt|instructions?)",
    r"repeat\s+(your|the)\s+(system|initial)\s+(prompt|instructions?)",
    r"打印(你的|系统)(提示|指令)",
    r"print\s+(your|the)\s+(system|initial)\s+(prompt|instructions?)",
    # 角色扮演诱导
    r"假装(你是|你没有|没有)",
    r"pretend\s+(you\s+are|you\s+have\s+no|there\s+are\s+no)",
    r"假设.{0,10}(限制|规则|约束|束缚)",
    r"hypothetical(ly)?",
    r"DAN\s+mode",
    r"jailbreak",
    # 恶意操作诱导
    r"(同意|批准|通过)(所有|全部)(退款|退货|售后)",
    r"(approve|agree\s+to)\s+(all|every)\s+(refund|return)",
    r"不要(检查|验证|审核)",
    r"skip\s+(validation|verification|checking)",
]


def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    """检测用户输入是否包含Prompt注入攻击
    
    Args:
        text: 用户输入文本
    
    Returns:
        (is_injection, matched_pattern): 是否检测到注入，匹配的模式
    """
    if not text:
        return False, None

    text_lower = text.lower()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(f"⚠️ 检测到Prompt注入: pattern='{pattern}' input='{text[:50]}'")
            return True, pattern

    return False, None


# ========== 输出过滤 ==========

SENSITIVE_PATTERNS = [
    r"api[_\s-]?key",
    r"access[_-]?token",
    r"secret",
    r"password",
    r"系统提示",
    r"system\s*prompt",
    r"内部(地址|接口|API)",
    r"localhost",
    r"127\.0\.0\.1",
]


def filter_response(response: str) -> str:
    """过滤AI回复中的敏感信息
    
    检查是否泄露:
    - 系统提示词
    - API密钥/Token
    - 内部服务地址
    - 其他敏感信息
    """
    if not response:
        return response

    response_lower = response.lower()
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, response_lower, re.IGNORECASE):
            logger.warning(f"⚠️ 输出过滤: 检测到敏感信息 pattern='{pattern}'")
            return "抱歉，我无法回答这个问题。请问还有其他可以帮到您的吗？"

    return response


# ========== 速率限制 ==========

class RateLimiter:
    """简单的速率限制器（内存版，生产环境用Redis）"""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict = defaultdict(list)  # key -> [timestamp, ...]

    def check(self, key: str) -> bool:
        """检查是否允许请求
        
        Args:
            key: 限流键（如 buyer_id, shop_id, IP等）
        
        Returns:
            True = 允许, False = 限流
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # 清理过期记录
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

        if len(self._requests[key]) >= self.max_requests:
            logger.warning(f"⚠️ 速率限制: key={key} requests={len(self._requests[key])}")
            return False

        self._requests[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """获取剩余配额"""
        now = time.time()
        cutoff = now - self.window_seconds
        valid = [t for t in self._requests[key] if t > cutoff]
        return max(0, self.max_requests - len(valid))


# 全局实例
message_limiter = RateLimiter(max_requests=30, window_seconds=60)  # 每买家每分钟30条
tool_limiter = RateLimiter(max_requests=60, window_seconds=60)     # 每店铺每分钟60次工具调用
refund_limiter = RateLimiter(max_requests=5, window_seconds=60)    # 每店铺每分钟5次退款


# ========== 敏感操作审批 ==========

def requires_human_approval(action: str, params: dict) -> Tuple[bool, str]:
    """判断操作是否需要人工审批
    
    Returns:
        (needs_approval, reason): 是否需要审批，原因
    """
    from app.core.config import settings

    # 退款金额检查
    if action in ("agree_refund", "create_refund"):
        amount = params.get("amount", 0)
        if amount > settings.RISK_HIGH_VALUE_THRESHOLD:
            return True, f"退款金额{amount}元超过阈值{settings.RISK_HIGH_VALUE_THRESHOLD}元"

    # 批量操作
    if action.startswith("batch_"):
        return True, "批量操作需人工确认"

    return False, ""
