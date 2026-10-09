"""数据库模型 — SQLAlchemy ORM"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class Shop(Base):
    """店铺"""
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False, index=True)  # taobao/pdd/douyin/jd
    shop_id = Column(String(100), nullable=False, index=True)
    shop_name = Column(String(200), default="")
    access_token = Column(Text, default="")       # 加密存储
    refresh_token = Column(Text, default="")      # 加密存储
    token_expires_at = Column(DateTime, nullable=True)
    config = Column(JSON, default={})              # 店铺级配置
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders = relationship("Order", back_populates="shop")
    conversations = relationship("Conversation", back_populates="shop")


class Buyer(Base):
    """买家"""
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False, index=True)
    buyer_id = Column(String(100), nullable=False, index=True)
    buyer_name = Column(String(200), default="")
    tags = Column(JSON, default=[])                # 标签: 新客/老客/高价值/疑似恶意
    total_orders = Column(Integer, default=0)
    total_refunds = Column(Integer, default=0)
    refund_rate = Column(Float, default=0.0)       # 近30天退货率
    refund_count_7d = Column(Integer, default=0)   # 近7天退款次数
    last_active_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="buyer")
    conversations = relationship("Conversation", back_populates="buyer")


class Order(Base):
    """订单"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100), nullable=False, index=True)
    platform = Column(String(20), nullable=False)
    shop_id = Column(Integer, ForeignKey("shops.id"))
    buyer_id = Column(Integer, ForeignKey("buyers.id"))
    status = Column(String(50), default="")
    total_amount = Column(Float, default=0.0)
    payment_amount = Column(Float, default=0.0)
    products = Column(JSON, default=[])            # 商品快照
    receiver_name = Column(String(100), default="")
    receiver_phone = Column(String(20), default="")
    receiver_address = Column(Text, default="")
    logistics_company = Column(String(100), default="")
    logistics_no = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    shipped_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    shop = relationship("Shop", back_populates="orders")
    buyer = relationship("Buyer", back_populates="orders")
    refunds = relationship("Refund", back_populates="order")


class Refund(Base):
    """退款记录"""
    __tablename__ = "refunds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    refund_id = Column(String(100), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    platform = Column(String(20), nullable=False)
    refund_type = Column(String(30), default="")   # refund_only / return_refund
    reason = Column(String(100), default="")
    amount = Column(Float, default=0.0)
    status = Column(String(50), default="pending") # pending/approved/rejected/completed
    decision = Column(String(30), default="")      # auto_approve/auto_reject/need_review/negotiate
    decision_reason = Column(Text, default="")
    risk_score = Column(Float, default=0.0)
    auto_approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="refunds")


class Conversation(Base):
    """会话"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False)
    shop_id = Column(Integer, ForeignKey("shops.id"))
    buyer_id = Column(Integer, ForeignKey("buyers.id"))
    conversation_id = Column(String(100), nullable=False, index=True)
    status = Column(String(30), default="active")  # active/closed/transferred
    assigned_to = Column(String(100), default="")  # AI / 人工客服ID
    context = Column(JSON, default={})             # 会话上下文(当前意图/订单号等)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop = relationship("Shop", back_populates="conversations")
    buyer = relationship("Buyer", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    """消息"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    direction = Column(String(10), default="inbound")  # inbound/outbound
    message_type = Column(String(20), default="text")
    content = Column(Text, default="")
    metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class AuditLog(Base):
    """审计日志"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)   # agree_refund / reject_refund / modify_address ...
    actor = Column(String(100), default="system")  # system / ai / human:<id>
    platform = Column(String(20), default="")
    shop_id = Column(String(100), default="")
    target_type = Column(String(50), default="")   # order / refund / message
    target_id = Column(String(100), default="")
    details = Column(JSON, default={})
    risk_level = Column(String(20), default="low")
    created_at = Column(DateTime, default=datetime.utcnow)
