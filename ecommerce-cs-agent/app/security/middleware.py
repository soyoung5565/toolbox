"""JWT认证中间件 — 挂载到FastAPI，自动验证所有非公开请求"""

import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.security.permissions import is_public_endpoint, is_webhook_endpoint, get_required_roles
from app.security.auth import verify_token

logger = logging.getLogger(__name__)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """JWT认证中间件
    
    规则:
    1. 公开端点(health/root/docs) → 放行
    2. Webhook端点 → 放行(由签名验证保护)
    3. 其他端点 → 必须携带有效JWT
    """

    async def dispatch(self, request: Request, call_next):
        # 获取端点名称
        endpoint = request.scope.get("endpoint")
        if not endpoint:
            return await call_next(request)
        
        endpoint_name = endpoint.__name__ if hasattr(endpoint, "__name__") else str(endpoint)
        
        # 公开端点放行
        if is_public_endpoint(endpoint_name):
            return await call_next(request)
        
        # 静态资源放行
        if request.url.path.startswith("/static"):
            return await call_next(request)
        
        # Webhook端点放行（由签名验证保护）
        if is_webhook_endpoint(endpoint_name):
            return await call_next(request)
        
        # OPTIONS请求放行（CORS预检）
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # 验证JWT
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "缺少Authorization头，需要Bearer token"},
            )
        
        token = auth_header[7:]
        try:
            payload = verify_token(token)
            # 将用户信息注入request.state
            request.state.user = {
                "sub": payload.get("sub", ""),
                "role": payload.get("role", "readonly"),
                "shop_id": payload.get("shop_id", ""),
            }
        except Exception as e:
            return JSONResponse(
                status_code=401,
                content={"detail": f"无效的token: {str(e)}"},
            )
        
        # 检查角色权限
        required_roles = get_required_roles(endpoint_name)
        user_role = request.state.user.get("role", "readonly")
        if required_roles and user_role not in [r.value for r in required_roles]:
            return JSONResponse(
                status_code=403,
                content={"detail": f"权限不足，需要角色: {[r.value for r in required_roles]}"},
            )
        
        return await call_next(request)
