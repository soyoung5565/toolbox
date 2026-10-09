"""拼多多Webhook — 真实消息接入

PDD开放平台消息推送文档: https://open.pinduoduo.com/application/document/api?id=pdd.pop.im.msg.push

消息推送流程:
1. PDD服务器POST消息到我们的/callback/pdd端点
2. 验证签名(MD5)
3. 解析消息格式
4. 转为UnifiedMessage送入Agent处理
5. 将Agent回复通过PDD IM API发回

OAuth授权流程:
1. 引导商家访问授权页
2. 获取authorization_code
3. 换取access_token + refresh_token
4. Token自动刷新
"""

import hashlib
import json
import logging
import time
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.security.auth import verify_webhook_signature
from app.security.audit import audit_log

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== PDD消息解析 ==========

def parse_pdd_message(data: dict) -> Optional[dict]:
    """解析PDD推送消息
    
    PDD消息推送格式:
    {
        "msg_push_dto": {
            "msg_type": 1,          # 1=文本 2=图片 3=商品卡
            "text": "消息内容",
            "uid": "买家ID",
            "user_name": "买家昵称",
            "mall_id": "店铺ID",
            "msg_id": "消息ID",
            "timestamp": 1234567890
        }
    }
    """
    msg_dto = data.get("msg_push_dto", data)
    
    if not msg_dto:
        return None
    
    msg_type = msg_dto.get("msg_type", 1)
    content = ""
    
    if msg_type == 1:  # 文本
        content = msg_dto.get("text", "")
    elif msg_type == 2:  # 图片
        content = f"[图片] {msg_dto.get('image_url', '')}"
    elif msg_type == 3:  # 商品卡
        content = f"[商品卡] {msg_dto.get('goods_name', '')}"
    else:
        content = msg_dto.get("text", str(msg_dto))
    
    return {
        "platform": "pdd",
        "shop_id": msg_dto.get("mall_id", ""),
        "buyer_id": msg_dto.get("uid", ""),
        "buyer_name": msg_dto.get("user_name", ""),
        "content": content,
        "msg_id": msg_dto.get("msg_id", ""),
        "msg_type": msg_type,
        "timestamp": msg_dto.get("timestamp", int(time.time())),
    }


# ========== PDD签名验证 ==========

def verify_pdd_signature(params: dict, client_secret: str) -> bool:
    """验证PDD API签名
    
    签名规则:
    1. 将所有请求参数按key的ASCII码排序
    2. 拼接: client_secret + key1value1key2value2... + client_secret
    3. MD5后转大写
    """
    sign = params.pop("sign", "")
    if not sign:
        return False
    
    sorted_keys = sorted(params.keys())
    sign_str = client_secret
    for key in sorted_keys:
        value = params[key]
        if value is not None and str(value) != "":
            sign_str += f"{key}{value}"
    sign_str += client_secret
    
    expected = hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()
    return sign.upper() == expected


# ========== Webhook端点 ==========

@router.post("/pdd")
async def pdd_webhook(request: Request):
    """PDD消息推送回调
    
    PDD开放平台会POST消息到此端点。
    需要在PDD开放平台配置回调URL: https://your-domain/webhook/pdd
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="无效的JSON")
    
    logger.info(f"PDD Webhook: {json.dumps(data, ensure_ascii=False)[:200]}")
    
    # 签名验证（生产环境必须开启）
    if not settings.DEBUG:
        if not verify_pdd_signature(data.copy(), settings.PDD_CLIENT_SECRET):
            logger.warning("PDD签名验证失败")
            raise HTTPException(status_code=401, detail="签名验证失败")
    
    # 解析消息
    msg = parse_pdd_message(data)
    if not msg:
        return {"success": True, "message": "非消息类型推送"}
    
    # 审计日志
    audit_log(
        action="webhook_received",
        actor=f"webhook:pdd",
        target_type="message",
        target_id=msg["msg_id"],
        platform="pdd",
        shop_id=msg["shop_id"],
        details={"buyer_id": msg["buyer_id"], "msg_type": msg["msg_type"]},
    )
    
    # 送入Agent处理
    try:
        from app.agents.orchestrator import process_message
        
        reply = await process_message(
            platform="pdd",
            shop_id=msg["shop_id"],
            buyer_id=msg["buyer_id"],
            buyer_name=msg["buyer_name"],
            content=msg["content"],
        )
        
        # 通过PDD API发回回复
        if reply:
            await send_pdd_reply(
                shop_id=msg["shop_id"],
                buyer_id=msg["buyer_id"],
                content=reply,
            )
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"PDD消息处理失败: {e}", exc_info=True)
        audit_log(
            action="webhook_error",
            actor="system",
            target_type="message",
            target_id=msg["msg_id"],
            platform="pdd",
            details={"error": str(e)},
            risk_level="medium",
            result="failure",
        )
        return {"success": False, "error": str(e)}


async def send_pdd_reply(shop_id: str, buyer_id: str, content: str):
    """通过PDD IM API发送回复
    
    API: pdd.pop.im.msg.send
    """
    import httpx
    
    # 构造请求
    params = {
        "type": "pdd.pop.im.msg.send",
        "client_id": settings.PDD_CLIENT_ID,
        "timestamp": str(int(time.time())),
        "data_type": "JSON",
    }
    
    # 消息内容
    msg_data = {
        "uid": buyer_id,
        "mall_id": shop_id,
        "text": content,
        "msg_type": 1,  # 文本
    }
    params["params_json"] = json.dumps(msg_data)
    
    # 签名
    sign_str = settings.PDD_CLIENT_SECRET
    for key in sorted(params.keys()):
        if params[key]:
            sign_str += f"{key}{params[key]}"
    sign_str += settings.PDD_CLIENT_SECRET
    params["sign"] = hashlib.md5(sign_str.encode()).hexdigest().upper()
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://gw-api.pinduoduo.com/api/router",
                json=params,
            )
            result = resp.json()
            if "error_response" in result:
                logger.error(f"PDD发送消息失败: {result['error_response']}")
            else:
                logger.info(f"PDD消息已发送: shop={shop_id} buyer={buyer_id}")
    except Exception as e:
        logger.error(f"PDD发送消息异常: {e}")


# ========== OAuth授权 ==========

@router.get("/pdd/auth")
async def pdd_auth_redirect():
    """引导商家进行PDD OAuth授权
    
    商家需要访问此URL完成授权，获取access_token。
    """
    auth_url = (
        f"https://mms.pinduoduo.com/open.html"
        f"?client_id={settings.PDD_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={settings.CALLBACK_BASE_URL}/webhook/pdd/callback"
        f"&state=pdd_auth"
    )
    return {"auth_url": auth_url}


@router.get("/pdd/callback")
async def pdd_auth_callback(code: str = "", state: str = ""):
    """PDD OAuth回调
    
    授权完成后PDD会回调此端点，携带authorization_code。
    用code换取access_token。
    """
    if not code:
        raise HTTPException(status_code=400, detail="缺少authorization_code")
    
    import httpx
    
    # 用code换token
    params = {
        "type": "pdd.pop.auth.token.get",
        "client_id": settings.PDD_CLIENT_ID,
        "timestamp": str(int(time.time())),
        "data_type": "JSON",
        "params_json": json.dumps({"code": code}),
    }
    
    # 签名
    sign_str = settings.PDD_CLIENT_SECRET
    for key in sorted(params.keys()):
        if params[key]:
            sign_str += f"{key}{params[key]}"
    sign_str += settings.PDD_CLIENT_SECRET
    params["sign"] = hashlib.md5(sign_str.encode()).hexdigest().upper()
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://gw-api.pinduoduo.com/api/router",
                json=params,
            )
            result = resp.json()
            
            token_data = result.get("pop_auth_token_get_response", {})
            access_token = token_data.get("access_token", "")
            refresh_token = token_data.get("refresh_token", "")
            expires_in = token_data.get("expires_in", 7200)
            
            if access_token:
                # TODO: 保存token到数据库
                logger.info(f"PDD授权成功: expires_in={expires_in}")
                audit_log(
                    action="oauth_success",
                    actor="shop_owner",
                    target_type="shop",
                    platform="pdd",
                    details={"expires_in": expires_in},
                )
                return {
                    "success": True,
                    "message": "授权成功！access_token已获取。",
                    "expires_in": expires_in,
                }
            else:
                logger.error(f"PDD授权失败: {result}")
                return {"success": False, "error": str(result)}
                
    except Exception as e:
        logger.error(f"PDD授权异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))
