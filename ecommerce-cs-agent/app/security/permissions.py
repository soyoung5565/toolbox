"""路由权限配置 — 定义每个端点的认证要求

安全原则: 默认需要认证，公开端点显式标注
"""

from app.security.auth import Role

# 公开端点（不需要认证）
PUBLIC_ENDPOINTS = {
    "health_check",
    "readiness",
    "root",
    "openapi",
    "swagger_ui_html",
    "swagger_ui_redirect",
    "redoc_html",
}

# Webhook端点（用签名验证代替JWT）
WEBHOOK_ENDPOINTS = {
    "pdd_webhook",
    "taobao_webhook",
    "douyin_webhook",
    "jd_webhook",
}

# 角色要求映射
ENDPOINT_ROLES = {
    # 对话测试 — 需要Agent角色
    "chat": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    
    # 风控评估 — 需要Agent角色
    "assess_risk": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    
    # 工具API — Agent可调用
    "query_order": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    "query_logistics": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    "search_products": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    "get_product_detail": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    "recommend_products": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    "create_refund": [Role.SHOP_ADMIN, Role.ADMIN],
    "approve_return": [Role.SHOP_ADMIN, Role.ADMIN],
    "reject_return": [Role.SHOP_ADMIN, Role.ADMIN],
    "modify_address": [Role.SHOP_ADMIN, Role.ADMIN],
    "follow_up": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    "transfer_to_human": [Role.AGENT, Role.SHOP_ADMIN, Role.ADMIN],
    
    # OAuth授权 — 需要店铺管理员
    "pdd_auth_redirect": [Role.SHOP_ADMIN, Role.ADMIN],
    "pdd_auth_callback": [Role.SHOP_ADMIN, Role.ADMIN],
}


def is_public_endpoint(endpoint_name: str) -> bool:
    """检查端点是否公开"""
    return endpoint_name in PUBLIC_ENDPOINTS


def is_webhook_endpoint(endpoint_name: str) -> bool:
    """检查端点是否为Webhook（用签名验证）"""
    return endpoint_name in WEBHOOK_ENDPOINTS


def get_required_roles(endpoint_name: str) -> list:
    """获取端点所需角色"""
    return ENDPOINT_ROLES.get(endpoint_name, [Role.ADMIN])
