"""审计日志 — 全量操作记录，持久化存储"""

import json
import logging
import os
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# 审计日志目录
AUDIT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "audit")
os.makedirs(AUDIT_DIR, exist_ok=True)


@dataclass
class AuditEntry:
    """审计日志条目"""
    timestamp: str
    action: str                    # 操作类型: api_call / refund_approve / refund_reject / login / webhook ...
    actor: str                     # 操作者: system / ai / user:<id> / webhook:<platform>
    target_type: str               # 目标类型: order / refund / message / product / user
    target_id: str                 # 目标ID
    platform: str                  # 平台: pdd / taobao / douyin / jd
    shop_id: str                   # 店铺ID
    details: dict                  # 操作详情
    ip_address: str                # 请求IP
    risk_level: str                # 风险等级: low / medium / high / critical
    result: str                    # 操作结果: success / failure / blocked


class AuditLogger:
    """审计日志记录器
    
    特点:
    1. 按日期分文件存储
    2. JSON格式，便于分析
    3. 自动脱敏PII
    4. 高风险操作告警
    """

    def __init__(self):
        self._buffer: list = []
        self._flush_size = 10  # 每10条写一次磁盘

    def log(self, entry: AuditEntry):
        """记录审计日志"""
        self._buffer.append(entry)
        
        # 高风险操作立即写入+告警
        if entry.risk_level in ("high", "critical"):
            self._flush()
            self._alert(entry)
        
        # 缓冲区满则写入
        if len(self._buffer) >= self._flush_size:
            self._flush()

    def _flush(self):
        """将缓冲区写入磁盘"""
        if not self._buffer:
            return
        
        today = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(AUDIT_DIR, f"audit_{today}.jsonl")
        
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
            self._buffer.clear()
        except Exception as e:
            logger.error(f"审计日志写入失败: {e}")

    def _alert(self, entry: AuditEntry):
        """高风险操作告警"""
        logger.warning(
            f"🚨 审计告警: {entry.action} | "
            f"actor={entry.actor} | target={entry.target_type}:{entry.target_id} | "
            f"risk={entry.risk_level} | result={entry.result}"
        )

    def flush_all(self):
        """强制写入所有缓冲"""
        self._flush()


# 全局实例
_audit = AuditLogger()


def get_audit_logger() -> AuditLogger:
    return _audit


def audit_log(
    action: str,
    actor: str = "system",
    target_type: str = "",
    target_id: str = "",
    platform: str = "",
    shop_id: str = "",
    details: dict = None,
    ip_address: str = "",
    risk_level: str = "low",
    result: str = "success",
):
    """便捷审计记录函数"""
    from app.security.validation import sanitize_log_data
    
    safe_details = sanitize_log_data(details or {})
    
    _audit.log(AuditEntry(
        timestamp=datetime.now().isoformat(),
        action=action,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        platform=platform,
        shop_id=shop_id,
        details=safe_details,
        ip_address=ip_address,
        risk_level=risk_level,
        result=result,
    ))
