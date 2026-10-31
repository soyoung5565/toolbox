# Toolbox · 小工具与自动化合集

> 六个**独立开发、独立可运行**的小项目：AI 应用、桌面自动化、开发提效工具。
> 每个子目录保留完整源码、README 与依赖说明，可单独取用。

---

## 📦 子项目

### 🛒 [ecommerce-cs-agent](./ecommerce-cs-agent/) — 电商智能客服 Agent
覆盖拼多多 / 淘宝 / 京东 / 抖音的 AI 客服系统：智能问答 + 商品推荐 + 退换货决策 + 客户跟进。
**风控引擎**做退换货决策矩阵与恶意退货检测，**RAG 知识库**自动注入商品/FAQ/政策，**42 条规则**的 Prompt 注入检测。每平台一个适配器类，新增平台只需实现一个类。
`Python` `FastAPI` `RAG` `Docker`

### 🎙 [ai-teleprompter](./ai-teleprompter/) — Android AI 提词器
**实时语音识别跟随朗读进度，自动滚动稿件** —— 不靠手动，靠"听"。
sherpa-onnx Paraformer 中文离线模型（不上传、无网络依赖）+ `ScriptAligner` 模糊匹配定位当前句。Compose 全黑主题大字重排版。
`Kotlin` `Jetpack Compose` `sherpa-onnx`

### 🏁 [fh6-afk](./fh6-afk/) — 极限竞速挂机自动化
《极限竞速：地平线 6》自动刷技能点：直线加速 + 撞击循环。
**AI Guardian** 用视觉模型定期检查比赛进度与卡死状态并自动恢复；`macro_recorder.py` 录制操作轨迹生成自定义路线。基础模式纯 Python + Windows API，**零第三方依赖**。
`Python` `Windows API` `视觉模型`

### 🔀 [codex-proxy](./codex-proxy/) — OpenAI Responses ↔ Chat Completions 流式代理
让 Codex IDE / CLI 通过 cc-switch 接任意模型：**完整 Function Calling**（工具定义透传、并行调用合并、tool 消息排序修复），SSE 流式响应翻译回 Responses 语义事件。
`Python` `SSE` `Function Calling`

### 🎧 [mimo-multimodal](./mimo-multimodal/) — 多模态理解工具
视频理解 / 音频提取 / 音频转录 —— 一套脚本跑完"下载 → 抽取 → 理解"链路，支持指定时间段裁剪。
`Python` `MIMO API`

### 🖥️ [screen-translator](./screen-translator/) — 屏幕实时翻译（悬浮窗）
框选屏幕任意区域 → OCR + 翻译 → 悬浮覆盖在原文上，不打断阅读。刷新间隔 / 字号 / 透明度均可调。
`Python` `PyQt5` `mss`

> **注**：这是早期的 OCR 版本（单文件）。已重构为独立应用的版本在 **[screen-translator-standalone](https://github.com/soyoung5565/screen-translator-standalone)** —— 用视觉大模型直接返回译文 + 坐标，**原位像素级覆盖**，无 OCR 引擎依赖，并带墨迹校正与打包自检闭环。

---

## 📁 组织说明

这些项目各自独立开发、体量较小，为便于管理与浏览合并到本仓库。每个子目录保留完整源码、README 与运行说明，可单独取用。

---

*本仓库为大项目之外的"工具集"。主力项目见个人主页置顶。*
