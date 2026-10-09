"""数据库初始化脚本 — 生成建表SQL + 可选直接执行

用法:
    python scripts/init_db.py --sql          # 输出SQL到stdout
    python scripts/init_db.py --sql > init.sql  # 保存到文件
    python scripts/init_db.py --execute       # 直接执行(需要数据库连接)
"""

import sys
import os
import argparse

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 表定义SQL（独立于SQLAlchemy，可直接执行）
INIT_SQL = """
-- 电商智能客服Agent 数据库初始化
-- PostgreSQL 16+

-- 店铺表
CREATE TABLE IF NOT EXISTS shops (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(20) NOT NULL,
    shop_id VARCHAR(100) NOT NULL,
    shop_name VARCHAR(200) DEFAULT '',
    access_token TEXT DEFAULT '',
    refresh_token TEXT DEFAULT '',
    token_expires_at TIMESTAMP,
    config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_shops_platform ON shops(platform);
CREATE INDEX IF NOT EXISTS idx_shops_shop_id ON shops(shop_id);

-- 买家表
CREATE TABLE IF NOT EXISTS buyers (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(20) NOT NULL,
    buyer_id VARCHAR(100) NOT NULL,
    buyer_name VARCHAR(200) DEFAULT '',
    tags JSONB DEFAULT '[]',
    total_orders INTEGER DEFAULT 0,
    total_refunds INTEGER DEFAULT 0,
    refund_rate FLOAT DEFAULT 0.0,
    refund_count_7d INTEGER DEFAULT 0,
    last_active_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_buyers_platform ON buyers(platform);
CREATE INDEX IF NOT EXISTS idx_buyers_buyer_id ON buyers(buyer_id);

-- 订单表
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    platform VARCHAR(20) NOT NULL,
    shop_id INTEGER REFERENCES shops(id),
    buyer_id INTEGER REFERENCES buyers(id),
    status VARCHAR(50) DEFAULT '',
    total_amount FLOAT DEFAULT 0.0,
    payment_amount FLOAT DEFAULT 0.0,
    products JSONB DEFAULT '[]',
    receiver_name VARCHAR(100) DEFAULT '',
    receiver_phone VARCHAR(20) DEFAULT '',
    receiver_address TEXT DEFAULT '',
    logistics_company VARCHAR(100) DEFAULT '',
    logistics_no VARCHAR(100) DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW(),
    shipped_at TIMESTAMP,
    delivered_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_platform ON orders(platform);

-- 退款表
CREATE TABLE IF NOT EXISTS refunds (
    id SERIAL PRIMARY KEY,
    refund_id VARCHAR(100) NOT NULL,
    order_id INTEGER REFERENCES orders(id),
    platform VARCHAR(20) NOT NULL,
    refund_type VARCHAR(30) DEFAULT '',
    reason VARCHAR(100) DEFAULT '',
    amount FLOAT DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'pending',
    decision VARCHAR(30) DEFAULT '',
    decision_reason TEXT DEFAULT '',
    risk_score FLOAT DEFAULT 0.0,
    auto_approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_refunds_refund_id ON refunds(refund_id);

-- 会话表
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(20) NOT NULL,
    shop_id INTEGER REFERENCES shops(id),
    buyer_id INTEGER REFERENCES buyers(id),
    conversation_id VARCHAR(100) NOT NULL,
    status VARCHAR(30) DEFAULT 'active',
    assigned_to VARCHAR(100) DEFAULT '',
    context JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversations_conversation_id ON conversations(conversation_id);

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    direction VARCHAR(10) DEFAULT 'inbound',
    message_type VARCHAR(20) DEFAULT 'text',
    content TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- 审计日志表
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    action VARCHAR(100) NOT NULL,
    actor VARCHAR(100) DEFAULT 'system',
    platform VARCHAR(20) DEFAULT '',
    shop_id VARCHAR(100) DEFAULT '',
    target_type VARCHAR(50) DEFAULT '',
    target_id VARCHAR(100) DEFAULT '',
    details JSONB DEFAULT '{}',
    risk_level VARCHAR(20) DEFAULT 'low',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- LLM配置表（店铺级自定义LLM）
CREATE TABLE IF NOT EXISTS shop_llm_configs (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES shops(id) UNIQUE,
    provider VARCHAR(50) DEFAULT 'mimo',
    model VARCHAR(100) DEFAULT 'mimo-v2.5-pro',
    api_key TEXT DEFAULT '',
    base_url VARCHAR(500) DEFAULT '',
    temperature FLOAT DEFAULT 0.3,
    max_tokens INTEGER DEFAULT 2048,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER update_shops_updated_at BEFORE UPDATE ON shops
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_shop_llm_configs_updated_at BEFORE UPDATE ON shop_llm_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 插入默认测试数据
INSERT INTO shops (platform, shop_id, shop_name) VALUES
    ('pdd', 'pdd_shop_001', '测试数码旗舰店')
ON CONFLICT DO NOTHING;
"""


def main():
    parser = argparse.ArgumentParser(description="数据库初始化")
    parser.add_argument("--sql", action="store_true", help="输出SQL到stdout")
    parser.add_argument("--execute", action="store_true", help="直接执行(需要DATABASE_URL)")
    parser.add_argument("--output", "-o", help="输出到文件")
    args = parser.parse_args()

    if args.sql or args.output:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(INIT_SQL)
            print(f"SQL已写入: {args.output}")
        else:
            print(INIT_SQL)
    elif args.execute:
        try:
            import psycopg2
            from app.core.config import settings
            conn = psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))
            cur = conn.cursor()
            cur.execute(INIT_SQL)
            conn.commit()
            cur.close()
            conn.close()
            print("数据库初始化成功！")
        except ImportError:
            print("需要安装 psycopg2: pip install psycopg2-binary")
        except Exception as e:
            print(f"执行失败: {e}")
    else:
        print("用法: python scripts/init_db.py --sql > init.sql")
        print("  或: python scripts/init_db.py --execute")


if __name__ == "__main__":
    main()
