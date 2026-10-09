"""FastAPI 主应用入口 — 含完整安全中间件"""

import logging
import secrets
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    
    # 安全检查：生产环境必须修改JWT密钥
    if not settings.DEBUG and settings.JWT_SECRET_KEY in ("change-me-in-production", ""):
        logger.error("🚨 JWT_SECRET_KEY必须在生产环境修改！")
        raise RuntimeError("不安全的JWT密钥")
    
    yield
    
    # 关闭时刷新审计日志
    from app.security.audit import get_audit_logger
    get_audit_logger().flush_all()
    logger.info("🛑 应用关闭")


app = FastAPI(
    title="电商智能客服Agent",
    description="覆盖淘宝/拼多多/京东/抖音等主流平台的智能客服系统",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,  # 生产环境关闭Swagger
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ========== 安全中间件 ==========

# CORS — 限制允许的来源（生产环境必须配置具体域名）
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
if settings.DEBUG:
    ALLOWED_ORIGINS.append("*")  # 开发环境允许所有

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Signature"],
    max_age=600,  # 预检缓存10分钟
)

# 安全响应头
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """添加安全响应头"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# 请求耗时 + 请求ID
@app.middleware("http")
async def request_tracking_middleware(request: Request, call_next):
    """请求追踪：耗时、请求ID、审计"""
    request_id = secrets.token_hex(8)
    request.state.request_id = request_id
    start = time.time()

    response = await call_next(request)

    elapsed = time.time() - start
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"

    # 慢请求告警
    if elapsed > 10:
        logger.warning(f"慢请求: {request.method} {request.url.path} 耗时 {elapsed:.2f}s id={request_id}")

    return response


# 请求体大小限制
@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next):
    """限制请求体大小（防止大payload攻击）"""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1_000_000:  # 1MB限制
        return JSONResponse(
            status_code=413,
            content={"detail": "请求体过大"},
        )
    return await call_next(request)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"未处理异常: {request.method} {request.url.path} id={request_id} - {exc}", exc_info=True)
    
    # 生产环境不暴露错误详情
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误", "error": str(exc), "request_id": request_id},
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误", "request_id": request_id},
    )


# ========== 路由注册 ==========

from app.api.health import router as health_router
from app.api.webhooks import router as webhook_router
from app.api.tools import router as tools_router
from app.api.risk import router as risk_router
from app.api.chat import router as chat_router
from app.api.pdd_webhook import router as pdd_router

app.include_router(health_router, tags=["健康检查"])
app.include_router(webhook_router, prefix="/webhook", tags=["平台Webhook"])
app.include_router(pdd_router, prefix="/webhook", tags=["PDD真实Webhook"])
app.include_router(tools_router, prefix="/api/tools", tags=["Agent工具"])
app.include_router(risk_router, prefix="/api/risk", tags=["风控评估"])
app.include_router(chat_router, prefix="/api", tags=["对话测试"])


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled",
    }
