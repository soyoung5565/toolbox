"""健康检查API"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "ecommerce-cs-agent"}


@router.get("/health/ready")
async def readiness():
    """就绪检查 — 检查数据库/Redis/LLM是否可用"""
    # TODO: 实际检查各组件连接状态
    return {
        "status": "ready",
        "components": {
            "database": "ok",
            "redis": "ok",
            "llm": "ok",
        }
    }
