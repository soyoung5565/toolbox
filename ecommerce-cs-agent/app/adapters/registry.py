"""平台适配器注册表 — 工厂模式，根据平台名获取对应适配器"""

import logging
from typing import Dict, Type

from app.adapters.base import EcommerceAdapter, PlatformConfig
from app.adapters.taobao.adapter import TaobaoAdapter
from app.adapters.pdd.adapter import PddAdapter
from app.adapters.douyin.adapter import DouyinAdapter

logger = logging.getLogger(__name__)


# 平台适配器注册表
_ADAPTERS: Dict[str, Type[EcommerceAdapter]] = {
    "taobao": TaobaoAdapter,
    "pdd": PddAdapter,
    "douyin": DouyinAdapter,
    # "jd": JdAdapter,  # TODO: 京东适配器
}

# 已实例化的适配器缓存
_instances: Dict[str, EcommerceAdapter] = {}


def get_adapter(platform: str, shop_id: str = "") -> EcommerceAdapter:
    """获取平台适配器实例
    
    Args:
        platform: 平台名称 (taobao/pdd/douyin/jd)
        shop_id: 店铺ID（用于获取店铺级token）
    
    Returns:
        对应平台的适配器实例
    
    Raises:
        ValueError: 不支持的平台
    """
    platform = platform.lower().strip()

    if platform not in _ADAPTERS:
        raise ValueError(f"不支持的平台: {platform}，可选: {list(_ADAPTERS.keys())}")

    # 使用缓存
    cache_key = f"{platform}:{shop_id}" if shop_id else platform
    if cache_key not in _instances:
        _instances[cache_key] = _ADAPTERS[platform]()
        logger.info(f"创建适配器: {platform} (shop={shop_id})")

    return _instances[cache_key]


def register_adapter(platform: str, adapter_class: Type[EcommerceAdapter]):
    """注册新的平台适配器（用于扩展）"""
    _ADAPTERS[platform] = adapter_class
    logger.info(f"注册适配器: {platform} -> {adapter_class.__name__}")


def list_platforms() -> list:
    """列出所有支持的平台"""
    return list(_ADAPTERS.keys())
