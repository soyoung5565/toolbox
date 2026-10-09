"""平台Webhook接收 — 各平台消息统一入口"""

import hashlib
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from app.schemas.messages import UnifiedMessage, Platform, MessageType, MessageDirection

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== 淘宝/天猫 ==========

@router.post("/taobao")
async def taobao_webhook(request: Request):
    """淘宝消息推送回调（TOP平台HTTP推送）
    
    文档: https://open.taobao.com/doc.htm?docId=103610&docType=1
    """
    data = await request.json()
    logger.info(f"淘宝消息: {data}")

    # TODO: 验签（淘宝用app_secret做HMAC-MD5）
    # TODO: 解析淘宝消息格式
    # TODO: 转为UnifiedMessage并送入Agent处理
    # TODO: 将Agent回复通过淘宝API发回

    msg = _parse_taobao_message(data)
    if msg:
        # 送入Agent处理
        reply = await _process_message(msg)
        if reply:
            await _send_taobao_reply(msg, reply)

    return {"success": True}


def _parse_taobao_message(data: dict) -> UnifiedMessage | None:
    """解析淘宝推送消息为统一格式"""
    try:
        # 淘宝消息推送格式：
        # {"type": "message", "content": "...", "from_user": "...", ...}
        # 实际格式需根据TOP文档调整
        if not data:
            return None
        return UnifiedMessage(
            platform=Platform.TAOBAO,
            shop_id=data.get("shop_id", ""),
            buyer_id=data.get("from_user", data.get("buyer_nick", "")),
            buyer_name=data.get("buyer_nick", ""),
            message_type=MessageType.TEXT,
            content=data.get("content", data.get("text", "")),
            raw_data=data,
        )
    except Exception as e:
        logger.error(f"解析淘宝消息失败: {e}")
        return None


async def _send_taobao_reply(msg: UnifiedMessage, reply_content: str):
    """通过淘宝API发送回复"""
    # TODO: 调用 taobao.miniapp.message.send 或千牛API
    logger.info(f"淘宝回复 -> {msg.buyer_id}: {reply_content[:50]}")


# ========== 拼多多 ==========

@router.post("/pdd")
async def pdd_webhook(request: Request):
    """拼多多消息推送回调
    
    文档: https://open.pinduoduo.com/application/document/api?id=pdd.pop.im.msg.push
    """
    data = await request.json()
    logger.info(f"拼多多消息: {data}")

    # TODO: 验签（PDD用client_secret做MD5签名）
    msg = _parse_pdd_message(data)
    if msg:
        reply = await _process_message(msg)
        if reply:
            await _send_pdd_reply(msg, reply)

    return {"success": True}


def _parse_pdd_message(data: dict) -> UnifiedMessage | None:
    """解析拼多多推送消息"""
    try:
        # 拼多多消息推送格式
        msg_data = data.get("msg_push_dto", data)
        return UnifiedMessage(
            platform=Platform.PDD,
            shop_id=msg_data.get("mall_id", ""),
            buyer_id=msg_data.get("uid", ""),
            buyer_name=msg_data.get("user_name", ""),
            message_type=MessageType.TEXT,
            content=msg_data.get("text", msg_data.get("content", "")),
            raw_data=data,
        )
    except Exception as e:
        logger.error(f"解析拼多多消息失败: {e}")
        return None


async def _send_pdd_reply(msg: UnifiedMessage, reply_content: str):
    """通过拼多多API发送回复"""
    # TODO: 调用 pdd.pop.im.msg.send
    logger.info(f"拼多多回复 -> {msg.buyer_id}: {reply_content[:50]}")


# ========== 抖店/飞鸽 ==========

@router.post("/douyin")
async def douyin_webhook(request: Request):
    """抖店消息推送回调（飞鸽官方IM API）
    
    文档: https://op.jinritemai.com/docs/guide-docs/10/28
    """
    data = await request.json()
    logger.info(f"抖店消息: {data}")

    # TODO: 验签（抖店用app_secret做SHA256签名）
    msg = _parse_douyin_message(data)
    if msg:
        reply = await _process_message(msg)
        if reply:
            await _send_douyin_reply(msg, reply)

    return {"success": True}


def _parse_douyin_message(data: dict) -> UnifiedMessage | None:
    """解析抖店推送消息"""
    try:
        return UnifiedMessage(
            platform=Platform.DOUYIN,
            shop_id=data.get("shop_id", ""),
            buyer_id=data.get("sender_id", ""),
            buyer_name=data.get("sender_name", ""),
            message_type=MessageType.TEXT,
            content=data.get("content", data.get("msg_content", "")),
            raw_data=data,
        )
    except Exception as e:
        logger.error(f"解析抖店消息失败: {e}")
        return None


async def _send_douyin_reply(msg: UnifiedMessage, reply_content: str):
    """通过飞鸽API发送回复"""
    # TODO: 调用飞鸽IM发送消息API
    logger.info(f"抖店回复 -> {msg.buyer_id}: {reply_content[:50]}")


# ========== 京东 ==========

@router.post("/jd")
async def jd_webhook(request: Request):
    """京东消息推送回调
    
    文档: https://jos.jd.com/api
    """
    data = await request.json()
    logger.info(f"京东消息: {data}")

    msg = _parse_jd_message(data)
    if msg:
        reply = await _process_message(msg)
        if reply:
            await _send_jd_reply(msg, reply)

    return {"success": True}


def _parse_jd_message(data: dict) -> UnifiedMessage | None:
    """解析京东推送消息"""
    try:
        return UnifiedMessage(
            platform=Platform.JD,
            shop_id=data.get("shop_id", ""),
            buyer_id=data.get("pin", data.get("buyer_id", "")),
            buyer_name=data.get("buyer_name", ""),
            message_type=MessageType.TEXT,
            content=data.get("content", ""),
            raw_data=data,
        )
    except Exception as e:
        logger.error(f"解析京东消息失败: {e}")
        return None


async def _send_jd_reply(msg: UnifiedMessage, reply_content: str):
    """通过京东API发送回复"""
    # TODO: 调用京东消息API
    logger.info(f"京东回复 -> {msg.buyer_id}: {reply_content[:50]}")


# ========== 统一处理 ==========

async def _process_message(msg: UnifiedMessage) -> str | None:
    """统一消息处理入口
    
    流程:
    1. Prompt注入检测
    2. L0意图路由
    3. L1专项Agent处理
    4. L2回复整合
    5. 安全审核
    """
    # TODO: 接入Agent编排层
    # 临时占位：返回固定回复
    logger.info(f"处理消息: [{msg.platform}] {msg.buyer_id}: {msg.content[:50]}")

    # 后续会替换为:
    # 1. prompt_injection_check(msg.content)
    # 2. intent = router_agent.classify(msg)
    # 3. response = specialist_agents[intent].handle(msg)
    # 4. final = integrator_agent.review(response)
    # 5. return final

    return None  # 暂不回复，等Agent接入后实现
