"""应用配置管理 — Pydantic Settings"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置，支持环境变量和.env文件"""

    # 应用
    APP_NAME: str = "ecommerce-cs-agent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ecommerce_cs"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM
    LLM_PROVIDER: str = "deepseek"
    LLM_MODEL: str = "deepseek-chat"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2048

    # Dify
    DIFY_API_URL: str = "http://localhost/v1"
    DIFY_API_KEY: str = ""

    # 淘宝
    TAOBAO_APP_KEY: str = ""
    TAOBAO_APP_SECRET: str = ""

    # 拼多多
    PDD_CLIENT_ID: str = ""
    PDD_CLIENT_SECRET: str = ""

    # 抖店
    DOUYIN_APP_KEY: str = ""
    DOUYIN_APP_SECRET: str = ""

    # 京东
    JD_APP_KEY: str = ""
    JD_APP_SECRET: str = ""

    # 回调地址
    CALLBACK_BASE_URL: str = "http://localhost:8000"

    # 风控
    RISK_MAX_AUTO_APPROVE_AMOUNT: float = 200
    RISK_MAX_DAILY_AUTO_REFUND: float = 5000
    RISK_SUSPICIOUS_REFUND_RATE: float = 0.3
    RISK_SUSPICIOUS_REFUND_COUNT_7D: int = 3
    RISK_MAX_RETURN_DAYS: int = 15
    RISK_NEW_ACCOUNT_DAYS: int = 7
    RISK_HIGH_VALUE_THRESHOLD: float = 500

    # 安全
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    RATE_LIMIT_PER_MINUTE: int = 60
    ENABLE_PROMPT_INJECTION_DETECTION: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
