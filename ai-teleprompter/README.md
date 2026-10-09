# AI Teleprompter · AI 提词器

> Android 智能提词器：**实时语音识别跟随朗读进度，自动滚动稿件** —— 不靠手动，靠"听"。
> *An Android teleprompter that follows your voice: on-device ASR tracks your reading progress and auto-scrolls the script.*

## 功能

- 🎙 **语音跟随**：sherpa-onnx Paraformer 中文离线模型，本地识别（不上传、无网络依赖）
- 📜 **稿件对齐**：ASR 文本与稿件实时模糊匹配，定位当前朗读位置，自动滚动
- 🖤 **极简界面**：Jetpack Compose 全黑主题，大字号高可读
- 🧪 支持 Intent 注入稿件（自动化测试 / 外部调用）

## 技术实现

- **ASR**: sherpa-onnx + Paraformer 离线模型（准流式：每 2 秒识别一次累积 PCM）
- **对齐**: `ScriptAligner` — ASR 结果与稿件做模糊匹配，跟踪当前句索引
- **UI**: Kotlin + Jetpack Compose (Material 3)
- **音频**: AudioRecord PCM 采集

## 构建

```bash
# 需要 JDK 17 + Android SDK
./gradlew assembleDebug
```

**依赖说明**：
- `app/libs/sherpa-onnx-*.aar`（sherpa-onnx Android 运行库）体积较大未入库，请从 [sherpa-onnx Releases](https://github.com/k2-fsa/sherpa-onnx/releases) 获取
- `app/src/main/assets/sherpa-onnx-paraformer-zh-2024-03-09/model.int8.onnx`（识别模型 ~217MB）未入库，请从 [sherpa-onnx 模型库](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models) 下载放入该目录

## 项目结构

```
app/src/main/java/com/ai/teleprompter/
├── MainActivity.kt        # Compose 界面 + 滚动逻辑
├── TeleprompterState.kt   # 状态管理（稿件/进度/ASR 文本）
├── align/ScriptAligner.kt # 稿件-语音对齐算法
├── asr/AsrEngine.kt       # sherpa-onnx ASR 封装
└── audio/AudioCapture.kt  # PCM 录音采集
```
