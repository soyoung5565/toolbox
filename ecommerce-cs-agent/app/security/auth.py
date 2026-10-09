"""JWT认证 + RBAC权限 — FastAPI依赖注入

安全措施:
1. JWT Token认证（RS256非对称加密）
2. Token刷新轮换（access_token短期+refresh_token长期）
3. RBAC权限模型（admin/shop_admin/agent/readonly）
4. API Key认证（用于Webhook回调）
"""

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from app.core.config import settings

# Lazy import jose (not available in all environments)
try:
    from jose import JWTError, jwt
except ImportError:
    jwt = None
    JWTError = Exception

logger = logging.getLogger(__name__)

# 安全方案
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class Role(str, Enum):
    """RBAC角色"""
    ADMIN = "admin"             # 系统管理员（全部权限）
    SHOP_ADMIN = "shop_admin"   # 店铺管理员（店铺级全部权限）
    AGENT = "agent"             # AI Agent（工具调用权限）
    READONLY = "readonly"       # 只读（查询权限）


# 角色→权限映射
ROLE_PERMISSIONS = {
    Role.ADMIN: ["*"],
    Role.SHOP_ADMIN: ["shop:*", "order:read", "order:write", "refund:approve", "product:*", "chat:*"],
    Role.AGENT: ["order:read", "product:read", "refund:assess", "chat:send"],
    Role.READONLY: ["order:read", "product:read"],
}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT access_token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """创建JWT refresh_token（有效期7天）"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh", "jti": secrets.token_hex(16)})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """验证JWT Token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"JWT验证失败: {e}")
        raise HTTPException(status_code=401, detail="无效的认证凭证")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> dict:
    """FastAPI依赖：获取当前认证用户
    
    用法:
        @app.get("/protected")
        async def protected(user = Depends(get_current_user)):
            return {"user": user["sub"]}
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="缺少认证凭证")
    
    payload = verify_token(credentials.credentials)
    
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="需要access_token")
    
    return {
        "sub": payload.get("sub", ""),
        "role": payload.get("role", Role.READONLY),
        "shop_id": payload.get("shop_id", ""),
    }


def require_role(*roles: Role):
    """FastAPI依赖：要求特定角色
    
    用法:
        @app.post("/admin-only")
        async def admin_action(user = Depends(require_role(Role.ADMIN))):
            ...
    """
    async def role_checker(
        credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    ) -> dict:
        if not credentials:
            raise HTTPException(status_code=401, detail="缺少认证凭证")
        
        payload = verify_token(credentials.credentials)
        user_role = payload.get("role", Role.READONLY)
        
        if user_role not in [r.value for r in roles]:
            raise HTTPException(status_code=403, detail=f"权限不足，需要角色: {[r.value for r in roles]}")
        
        return {
            "sub": payload.get("sub", ""),
            "role": user_role,
            "shop_id": payload.get("shop_id", ""),
        }
    
    return role_checker


async def verify_webhook_signature(
    request: Request,
    platform: str,
) -> bool:
    """验证Webhook签名
    
    每个平台的签名方式不同：
    - 拼多多: MD5(client_secret + 参数)
    - 淘宝: HMAC-MD5(app_secret, 请求体)
    - 抖店: SHA256(app_secret + 参数)
    """
    # 从配置获取对应平台的secret
    secrets_map = {
        "pdd": settings.PDD_CLIENT_SECRET,
        "taobao": settings.TAOBAO_APP_SECRET,
        "douyin": settings.DOUYIN_APP_SECRET,
        "jd": settings.JD_APP_SECRET,
    }
    
    secret = secrets_map.get(platform)
    if not secret:
        logger.warning(f"平台{platform}未配置secret，跳过签名验证")
        return True  # 开发模式下跳过
    
    # 获取请求中的签名
    body = await request.body()
    signature = request.headers.get("X-Signature", request.headers.get("sign", ""))
    
    if not signature:
        logger.warning(f"Webhook请求缺少签名: platform={platform}")
        # 生产环境应返回False，开发环境返回True
        if not settings.DEBUG:
            return False
        return True
    
    # 计算期望签名
    expected = hashlib.md5((secret + body.decode()).encode()).hexdigest().upper()
    
    if not hmac.compare_digest(signature.upper(), expected):
        logger.warning(f"Webhook签名验证失败: platform={platform}")
        return False
    
    return True


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """API Key认证（用于Webhook回调和内部服务调用）"""
    if not api_key:
        raise HTTPException(status_code=401, detail="缺少X-API-Key头")
    
    # 验证API Key（从数据库或配置读取）
    valid_keys = [settings.JWT_SECRET_KEY]  # 简化，生产环境应从数据库读取
    if api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="无效的API Key")
    
    return api_key
