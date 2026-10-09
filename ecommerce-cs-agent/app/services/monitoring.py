"""监控告警模块 — 应用指标收集 + 错误告警

提供:
1. Prometheus指标暴露(/metrics)
2. 错误率监控
3. 响应时间监控
4. 业务指标(退款数/对话数/工具调用数)
"""

import time
import logging
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self._counters = defaultdict(int)
        self._histograms = defaultdict(list)
        self._gauges = {}
        self._start_time = datetime.now()

    def inc(self, name: str, value: int = 1, labels: dict = None):
        """计数器+1"""
        key = f"{name}:{labels}" if labels else name
        self._counters[key] += value

    def observe(self, name: str, value: float, labels: dict = None):
        """记录直方图值"""
        key = f"{name}:{labels}" if labels else name
        self._histograms[key].append(value)
        # 只保留最近1000个值
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]

    def set_gauge(self, name: str, value: float):
        """设置仪表盘值"""
        self._gauges[name] = value

    def get_metrics(self) -> dict:
        """获取所有指标"""
        uptime = (datetime.now() - self._start_time).total_seconds()
        return {
            "uptime_seconds": uptime,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: {
                    "count": len(v),
                    "sum": sum(v),
                    "avg": sum(v) / len(v) if v else 0,
                    "p50": sorted(v)[len(v)//2] if v else 0,
                    "p95": sorted(v)[int(len(v)*0.95)] if v else 0,
                    "p99": sorted(v)[int(len(v)*0.99)] if v else 0,
                }
                for k, v in self._histograms.items()
            },
        }

    def to_prometheus(self) -> str:
        """导出Prometheus格式"""
        lines = []
        
        for key, value in self._counters.items():
            safe_key = key.replace(":", "_").replace("'", "").replace('"', "")
            lines.append(f"# TYPE ecommerce_{safe_key} counter")
            lines.append(f"ecommerce_{safe_key} {value}")
        
        for key, value in self._gauges.items():
            lines.append(f"# TYPE ecommerce_{key} gauge")
            lines.append(f"ecommerce_{key} {value}")
        
        uptime = (datetime.now() - self._start_time).total_seconds()
        lines.append(f"# TYPE ecommerce_uptime_seconds gauge")
        lines.append(f"ecommerce_uptime_seconds {uptime}")
        
        return "\n".join(lines) + "\n"


# 全局实例
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    return _metrics


def record_request(method: str, path: str, status: int, duration: float):
    """记录请求指标"""
    _metrics.inc("http_requests_total", labels={"method": method, "status": str(status)})
    _metrics.observe("http_request_duration_seconds", duration, labels={"method": method, "path": path})


def record_tool_call(tool_name: str, success: bool):
    """记录工具调用"""
    _metrics.inc("tool_calls_total", labels={"tool": tool_name, "success": str(success)})


def record_refund(amount: float, decision: str):
    """记录退款操作"""
    _metrics.inc("refunds_total", labels={"decision": decision})
    _metrics.observe("refund_amount", amount)


def record_llm_call(provider: str, model: str, duration: float, tokens: int):
    """记录LLM调用"""
    _metrics.inc("llm_calls_total", labels={"provider": provider, "model": model})
    _metrics.observe("llm_duration_seconds", duration)
    _metrics.observe("llm_tokens", tokens)
