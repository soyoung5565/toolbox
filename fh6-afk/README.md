# FH6 AFK · 地平线6 自动刷技能点

> 《极限竞速：地平线 6》自动化脚本：直线撞击赛道无限刷技能点，含 AI 状态监控防卡死。
> *Forza Horizon 6 AFK skill-farming automation: collision-track grinding loop with AI-based state monitoring.*

## 功能

- 🏁 **挂机循环**：自动完成"直线加速 + 撞击"刷技能点循环（F9 启停 / F10 退出）
- 🧠 **AI Guardian 监控**：视觉模型定期检查游戏状态（比赛进度/卡死检测），异常自动恢复
- 🎥 **宏录制器**：`macro_recorder.py` 录制操作轨迹，生成自定义路线配置
- ⚙️ **零依赖模式**：纯 Python + Windows API（`fh6_afk.py` 不需要任何第三方库）

## 快速开始

```bash
# 基础挂机（零依赖）
python fh6_afk.py

# 打开游戏 → 进入赛道 → 切到游戏窗口 → F9 开始（3 秒倒计时）
# F9 暂停/继续 · F10 退出
```

### 自定义路线

```bash
python fh6_afk.py --example   # 生成示例配置 my_route.json
```

### AI 监控（可选）

`ai_guardian.py` 使用多模态模型（MIMO）识别游戏画面状态，配合 `config.json` 中的状态参考描述进行异常检测。需配置 API Key（`config.json` 的 `ai.api_key`）。

### 宏录制

```bash
python macro_recorder.py   # 录制鼠标/键盘操作，生成可回放的宏
```

## 文件说明

| 文件 | 说明 |
|---|---|
| `fh6_afk.py` | 主挂机脚本（零依赖） |
| `ai_guardian.py` | AI 状态监控模块 |
| `macro_recorder.py` | 操作宏录制器 |
| `config.json` | 配置（AI 参考描述/路线参数） |
| `CHANGELOG.md` | 版本记录 |
