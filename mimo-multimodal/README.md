# MIMO 多模态理解工具

基于 MIMO 原生 API 的视频和音频理解工具。

## 功能

- **视频理解**: 分析视频内容、画面、动作、对话等
- **音频提取**: 从视频中提取音频（支持指定时间段）
- **音频理解**: 转录音频内容、分析音频信息

## 快速开始

### 1. 从视频中提取音频并转录

```bash
# 提取音频（4:44-6:26）
python D:/mimo-multimodal/video_understand.py "你的视频.mp4" --extract-audio --start 04:44 --end 06:26 -o "输出.mp3"

# 转录音频
python D:/mimo-multimodal/audio_understand.py "输出.mp3" --transcribe --language zh
```

### 2. 分析视频内容

```bash
python D:/mimo-multimodal/video_understand.py "你的视频.mp4" -p "描述视频内容"
```

### 3. 转录音频文件

```bash
python D:/mimo-multimodal/audio_understand.py "你的音频.mp3" --transcribe --language zh
```

## 工具列表

| 文件 | 功能 |
|------|------|
| `video_understand.py` | 视频理解 + 音频提取 |
| `audio_understand.py` | 音频理解 |
| `mimo_understand.py` | 统一入口 |
| `example_extract_and_transcribe.py` | 示例：提取音频并转录 |
| `test_tools.py` | 测试脚本 |

## 参数说明

### video_understand.py

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `video` | 视频文件路径或URL | 必填 |
| `-p, --prompt` | 分析提示词 | "请详细描述视频内容" |
| `--fps` | 抽帧频率(每秒帧数) | 1 |
| `--model` | 模型名称 | mimo-v2.5 |
| `--max-tokens` | 最大输出token数 | 4096 |
| `--json` | JSON格式输出 | false |
| `--extract-audio` | 仅提取音频 | false |
| `--start` | 开始时间(HH:MM:SS或秒数) | 无 |
| `--end` | 结束时间(HH:MM:SS或秒数) | 无 |
| `--audio-format` | 音频输出格式 | mp3 |
| `--output`, `-o` | 输出文件路径 | 自动生成 |

### audio_understand.py

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `audio` | 音频文件路径或URL | 必填 |
| `-p, --prompt` | 分析提示词 | "请详细描述音频内容" |
| `--model` | 模型名称 | mimo-v2.5 |
| `--max-tokens` | 最大输出token数 | 4096 |
| `--language` | 音频语言(如zh, en, ja) | 无 |
| `--transcribe` | 仅转录音频内容 | false |
| `--json` | JSON格式输出 | false |

## 使用场景

1. **游戏攻略提取**: 从游戏视频中提取攻略语音并转录
2. **会议记录**: 从会议录音中提取关键信息
3. **字幕生成**: 从视频中提取音频并转录生成字幕
4. **内容分析**: 分析视频中的角色、场景、动作等

## 依赖

```bash
pip install openai
```

ffmpeg 需要单独安装：
- Windows: 下载 https://www.gyan.dev/ffmpeg/builds/
- Linux: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`

## API Key 配置

工具会自动从以下位置读取 MIMO API Key：

1. 环境变量 `MIMO_API_KEY`
2. `~/.hermes/.env` 文件
3. `~/.hermes/config.yaml` 中的配置

## 测试

```bash
python D:/mimo-multimodal/test_tools.py
```

## 示例

### 从游戏视频中提取攻略

```bash
# 提取攻略部分的音频
python D:/mimo-multimodal/video_understand.py "D:/崩铁攻略.mp4" --extract-audio --start 04:44 --end 06:26 -o "货币战争公式.mp3"

# 转录音频
python D:/mimo-multimodal/audio_understand.py "货币战争公式.mp3" --transcribe --language zh
```

### 批量处理

```bash
# 批量提取音频
for video in *.mp4; do
    python D:/mimo-multimodal/video_understand.py "$video" --extract-audio -o "${video%.mp4}.mp3"
done

# 批量转录音频
for audio in *.mp3; do
    python D:/mimo-multimodal/audio_understand.py "$audio" --transcribe --language zh > "${audio%.mp3}.txt"
done
```

## 更新日志

### v1.0.0 (2026-05-27)
- 初始版本
- 支持视频理解
- 支持音频提取（指定时间段）
- 支持音频转录
- 支持指定输出路径
- 支持多种格式
- 完整测试通过
