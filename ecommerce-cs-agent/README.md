# 电商智能客服Agent

覆盖拼多多/淘宝/京东/抖音等主流平台的AI智能客服系统，具备**智能问答 + 商品推荐 + 退换货决策 + 客户跟进**能力。

> 📦 **本目录为工具集内的副本。独立仓库 → [soyoung5565/ecommerce-cs-agent](https://github.com/soyoung5565/ecommerce-cs-agent)**
> 代码与独立仓库同步（5,455 行 Python 一致），独立仓库保留完整 commit 历史与密钥清理记录。
>
> ⚠️ 注意：本项目历史上曾把真实 Token Plan API Key 提交进 `.env`（`.gitignore` 换行符写坏导致规则失效）。
> 已在独立仓库用 `git filter-repo` 重写历史清除，**`.env` 已移出版本库**，仓库只提供 `.env.example`。

## 核心特性

- **🧠 LLM驱动** — MIMO/DeepSeek/任何OpenAI兼容模型，客户可自定义
- **🔧 工具调用** — LLM自动决定调用订单查询/物流/退款/推荐等工具
- **🛡️ 风控引擎** — 退换货决策矩阵，恶意退货检测，自动/转人工分流
- **📚 RAG知识库** — 商品/FAQ/政策/话术自动注入prompt
- **🔒 安全防护** — Prompt注入检测(42规则) + 输出过滤 + 速率限制
- **🔌 可插拔架构** — 每个平台独立适配器，新增平台只需实现一个类

## 快速开始

### 1. 环境要求
- Python 3.8+
- PostgreSQL (可选，Mock模式不需要)
- Redis (可选，Mock模式不需要)

### 2. 安装依赖
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入LLM API Key
```

### 4. 启动服务
```bash
python run.py
```

### 5. 测试对话
```bash
# 售前咨询
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "耳机多少钱？有什么颜色？", "buyer_id": "buyer_001"}'

# 售后退款（会触发工具调用 + 风控评估）
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "我要退款，订单号PDD20260701001，耳机有杂音", "buyer_id": "buyer_001"}'

# 查物流
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我查一下物流，订单号PDD20260704001", "buyer_id": "buyer_001"}'
```

## 架构

```
客户消息 → Webhook/API → Prompt注入检测 → L0意图路由(LLM)
    → L1专项Agent(LLM + 工具调用循环) → L2输出过滤 → 回复

工具调用: query_order / query_logistics / search_products / assess_refund_risk / transfer_to_human
```

## API文档

启动后访问 http://localhost:8000/docs

| 端点 | 说明 |
|------|------|
| `POST /api/chat` | 对话测试（完整Agent链路） |
| `POST /api/risk/assess` | 风控评估 |
| `POST /api/tools/*` | Agent工具（订单/物流/商品/退款） |
| `POST /webhook/pdd` | 拼多多消息Webhook |
| `GET /health` | 健康检查 |

## 客户自定义LLM

```bash
# 使用MIMO（默认）
LLM_PROVIDER=mimo
LLM_MODEL=mimo-v2.5-pro
LLM_API_KEY=your-key
LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

# 使用DeepSeek
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.deepseek.com

# 使用任何OpenAI兼容接口
LLM_PROVIDER=custom
LLM_MODEL=your-model
LLM_API_KEY=your-key
LLM_BASE_URL=https://your-api-endpoint/v1
```

## Docker部署

```bash
docker compose up -d
```

## 项目结构

```
app/
├── main.py              # FastAPI入口
├── core/config.py       # 配置管理
├── agents/orchestrator.py # Agent编排(L0-L3)
├── services/
│   ├── risk_engine.py   # 售后决策引擎
│   ├── knowledge_base.py # RAG知识库
│   ├── mock_data.py     # Mock测试数据
│   └── llm/             # LLM Provider(MIMO/DeepSeek/OpenAI)
├── adapters/
│   ├── pdd/adapter.py   # 拼多多适配器
│   ├── taobao/          # 淘宝(预留)
│   ├── douyin/          # 抖店(预留)
│   └── jd/              # 京东(预留)
├── api/                 # API路由
└── security/guard.py    # 安全防护
```

---

## 📈 开发轨迹（摘要）

本项目从零到可部署，经历了完整的 14 步迭代（原仓库 git 历史）：

1. 项目初始化（框架选型：FastAPI + 异步架构）
2. Phase 1 核心框架完成
3. 平台适配器 + 安全层 + 知识库同步
4. 聚焦拼多多平台优先开发
5. LLM 服务层 + Mock 数据 + Agent 编排 + 对话 API
6. MIMO 真机工具调用链路打通
7. RAG 知识库 + Docker 部署 + 启动脚本
8. 全面安全加固（10 项）
9. PDD Webhook 真实消息接入（OAuth + 签名验证 + 消息解析）
10. 部署安全加固 + 数据库 + 监控 + GitHub 托管
11. 上传脚本 + 部署配置完善
12. 模型服务切换（MiniMax-M3）
13. 文档与进度记录持续维护
