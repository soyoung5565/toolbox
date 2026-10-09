# 电商智能客服Agent — 开发进度

> 每完成一步打✅，每改一次代码都git commit
> **当前聚焦：拼多多平台**，其他平台留好位置但暂不实装

## 开发规划

### Phase 1: 核心框架 ✅
- [x] 1.1 项目初始化（git + 目录结构 + PROGRESS.md）
- [x] 1.2 配置管理（config.yaml + 环境变量 + Pydantic Settings）
- [x] 1.3 统一消息格式（UnifiedMessage + Platform枚举）
- [x] 1.4 数据库模型（SQLAlchemy：Shop/Order/Buyer/Conversation/Message/Refund/AuditLog）
- [x] 1.5 FastAPI应用骨架（23个路由 + 中间件 + 异常处理）
- [ ] 1.6 数据库迁移（Alembic）— 待数据库环境就绪后执行

### Phase 2: 售后决策引擎 ✅
- [x] 2.1 决策矩阵（Decision枚举 + RefundContext + assess_refund_risk）
- [x] 2.2 恶意退货检测（退货率>30% / 7天>=3次 / 新号+大额）
- [x] 2.3 风控评估API（POST /api/risk/assess）
- [x] 2.4 安全规则（日限额¥5000 / 单笔上限¥500 / 审计日志）
- [x] 2.5 测试覆盖（24个测试全通过）

### Phase 3: 平台适配器 [聚焦拼多多]
- [x] 3.1 适配器基类（EcommerceAdapter ABC）
- [x] 3.2 拼多多适配器（PDD API：OAuth2 + 订单 + 商品 + 售后 + 消息）✅ 优先
- [x] 3.3 淘宝适配器（留好位置，暂不实装）
- [x] 3.4 抖店适配器（留好位置，暂不实装）
- [ ] 3.5 京东适配器（留好位置，暂不实装）
- [ ] 3.6 Mock数据层（用于无API key时的本地测试）

### Phase 4: Agent编排层 [待开始]
- [x] 4.1 L0 意图路由器（规则引擎占位，待接入LLM）
- [x] 4.2 L1-L3 Agent框架（售前/售后/推荐/投诉/转人工骨架）
- [ ] 4.3 接入DeepSeek LLM（替换规则引擎为LLM分类）
- [ ] 4.4 RAG知识库对接
- [ ] 4.5 工具调用链路打通（Agent→工具API→平台适配器）

### Phase 5: 知识库与RAG [待开始]
- [x] 5.1 商品知识库同步脚本框架
- [ ] 5.2 接入Dify知识库API
- [ ] 5.3 FAQ知识库
- [ ] 5.4 售后政策库
- [ ] 5.5 话术库

### Phase 6: Dify工作流 [待开始]
- [ ] 6.1 Dify环境部署
- [ ] 6.2 Chatflow配置
- [ ] 6.3 HTTP工具注册
- [ ] 6.4 变量记忆配置

### Phase 7: 安全层 ✅ (基础完成)
- [x] 7.1 Prompt注入检测（42条中英文规则）
- [x] 7.2 输出过滤（防泄露系统提示词/API密钥）
- [x] 7.3 API速率限制（内存版，生产用Redis）
- [x] 7.4 敏感操作审批（大额退款/批量操作需人工）
- [ ] 7.5 JWT认证 + RBAC权限
- [ ] 7.6 数据加密 + PII脱敏
- [x] 7.7 测试覆盖（18个测试全通过）

### Phase 8: 部署 [待开始]
- [ ] 8.1 Docker Compose
- [ ] 8.2 Nginx + HTTPS
- [ ] 8.3 监控
- [ ] 8.4 文档

---

## Git提交记录

| 日期 | Hash | 说明 |
|------|------|------|
| 2026-07-06 | 23e70e5 | init: 项目初始化 |
| 2026-07-06 | cabb810 | feat: Phase 1 核心框架（配置+消息+模型+FastAPI+Webhook+工具API+决策引擎+Agent编排）|
| 2026-07-06 | 0451814 | feat: 平台适配器+安全层+知识库同步（42测试全通过）|
| 2026-07-09 | 99d8d1c | chore: 切到 minimax (MiniMax-M3) 套餐 (.env本地配置+ mimo_provider.py 改造) |

---

## 项目结构

```
D:\ecommerce-cs-agent\
├── app/
│   ├── main.py              ← FastAPI入口（23个路由）
│   ├── core/config.py       ← Pydantic Settings配置
│   ├── schemas/messages.py  ← 统一消息格式
│   ├── models/database.py   ← SQLAlchemy ORM（7张表）
│   ├── api/
│   │   ├── health.py        ← 健康检查
│   │   ├── webhooks.py      ← 平台消息Webhook入口
│   │   ├── tools.py         ← Agent工具API（Dify调用）
│   │   └── risk.py          ← 风控评估API
│   ├── services/
│   │   └── risk_engine.py   ← 售后决策引擎（核心）
│   ├── adapters/
│   │   ├── base.py          ← 适配器基类ABC
│   │   ├── registry.py      ← 适配器工厂
│   │   ├── pdd/adapter.py   ← ✅ 拼多多适配器（优先）
│   │   ├── taobao/adapter.py← 淘宝适配器（位置留好）
│   │   ├── douyin/adapter.py← 抖店适配器（位置留好）
│   │   └── jd/              ← 京东适配器（位置留好）
│   ├── agents/
│   │   └── orchestrator.py  ← L0-L3 Agent编排
│   └── security/
│       └── guard.py         ← Prompt注入检测+输出过滤+限流
├── tests/                   ← 42个测试全通过
├── scripts/sync_knowledge.py← 知识库同步脚本
├── config/config.yaml       ← 配置文件
├── requirements.txt
├── Dockerfile
└── PROGRESS.md              ← 本文件
```
