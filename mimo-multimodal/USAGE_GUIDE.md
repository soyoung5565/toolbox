# MIMO 多模态理解工具使用指南

## 快速开始

### 1. 从视频中提取音频并转录（货币战争公式提取）

```bash
# 提取音频（4:44-6:26）
python D:/mimo-multimodal/video_understand.py "你的视频文件.mp4" --extract-audio --start 04:44 --end 06:26

# 转录音频
python D:/mimo-multimodal/audio_understand.py "/tmp/extracted_audio.mp3" --transcribe --language zh
```

### 2. 分析视频内容

```bash
python D:/mimo-multimodal/video_understand.py "你的视频文件.mp4" -p "描述视频内容"
```

### 3. 转录音频文件

```bash
python D:/mimo-multimodal/audio_understand.py "你的音频文件.mp3" --transcribe --language zh
```

## 完整工作流示例

### 从游戏视频中提取攻略语音

```bash
# 1. 提取攻略部分的音频
python D:/mimo-multimodal/video_understand.py "D:/崩铁攻略.mp4" --extract-audio --start 04:44 --end 06:26

# 2. 转录音频内容
python D:/mimo-multimodal/audio_understand.py "/tmp/extracted_audio.mp3" --transcribe --language zh

# 3. 将转录结果保存到文件
python D:/mimo-multimodal/audio_understand.py "/tmp/extracted_audio.mp3" --transcribe --language zh > 货币战争公式.txt
```

## 高级用法

### 分析视频中的特定内容

```bash
# 分析游戏中的角色技能
python D:/mimo-multimodal/video_understand.py "D:/游戏视频.mp4" -p "识别游戏中的角色和技能"

# 分析视频中的文字信息
python D:/mimo-multimodal/video_understand.py "D:/教程视频.mp4" -p "提取视频中的所有文字说明"
```

### 提取不同格式的音频

```bash
# 提取为WAV格式（无损）
python D:/mimo-multimodal/video_understand.py "D:/视频.mp4" --extract-audio --audio-format wav

# 提取为FLAC格式（无损压缩）
python D:/mimo-multimodal/video_understand.py "D:/视频.mp4" --extract-audio --audio-format flac
```

### 使用JSON格式输出

```bash
# 获取JSON格式的分析结果
python D:/mimo-multimodal/video_understand.py "D:/视频.mp4" -p "描述视频内容" --json

# 获取JSON格式的转录结果
python D:/mimo-multimodal/audio_understand.py "D:/音频.mp3" --transcribe --json
```

## 工具对比

| 功能 | video_understand.py | audio_understand.py |
|------|---------------------|---------------------|
| 视频理解 | ✅ | ❌ |
| 音频提取 | ✅ | ❌ |
| 音频转录 | ❌ | ✅ |
| 音频分析 | ❌ | ✅ |
| 指定时间段 | ✅ | ❌ |
| 多种格式 | ✅ | ✅ |

## 支持的格式

### 视频格式
- MP4 (推荐)
- AVI
- MOV
- MKV
- WebM

### 音频格式
- MP3 (推荐)
- WAV
- OGG
- FLAC
- M4A
- AAC

## 常见问题

### Q: 如何获取视频中的特定时间段音频？

A: 使用 `--start` 和 `--end` 参数：
```bash
python D:/mimo-multimodal/video_understand.py "视频.mp4" --extract-audio --start 04:44 --end 06:26
```

### Q: 如何提高转录准确率？

A: 使用 `--language` 参数指定语言：
```bash
python D:/mimo-multimodal/audio_understand.py "音频.mp3" --transcribe --language zh
```

### Q: 如何批量处理多个视频？

A: 使用循环脚本：
```bash
for video in *.mp4; do
    python D:/mimo-multimodal/video_understand.py "$video" --extract-audio
    python D:/mimo-multimodal/audio_understand.py "/tmp/extracted_audio.mp3" --transcribe
done
```

### Q: 如何获取更详细的视频分析？

A: 使用更具体的提示词：
```bash
python D:/mimo-multimodal/video_understand.py "视频.mp4" -p "详细描述视频中的每个场景、人物动作、对话内容、背景音乐等"
```

## 性能优化

### 降低API调用成本

1. **降低抽帧频率**：使用 `--fps 0.5` 减少视频分析的帧数
2. **限制输出长度**：使用 `--max-tokens 1024` 减少输出token数
3. **使用更小的模型**：如果不需要高级分析，使用 `--model mimo-v2.5`

### 提高处理速度

1. **并行处理**：同时处理多个视频
2. **预处理视频**：压缩视频文件大小
3. **使用本地缓存**：避免重复处理相同视频

## 故障排除

### 问题：找不到MIMO API Key

**解决方案：**
1. 检查 `~/.hermes/config.yaml` 中是否有MIMO配置
2. 手动设置环境变量：`export MIMO_API_KEY=your_key`

### 问题：ffmpeg未找到

**解决方案：**
1. 下载并安装ffmpeg：https://www.gyan.dev/ffmpeg/builds/
2. 将ffmpeg添加到系统PATH

### 问题：视频文件过大

**解决方案：**
1. 使用视频压缩工具减小文件大小
2. 提取视频片段而非整个视频
3. 使用 `--start` 和 `--end` 参数提取特定时间段

### 问题：转录结果不准确

**解决方案：**
1. 指定正确的语言参数
2. 确保音频质量清晰
3. 尝试调整 `--max-tokens` 参数

## 最佳实践

1. **明确目标**：先确定需要分析或提取的内容
2. **选择合适的工具**：视频分析用 `video_understand.py`，音频转录用 `audio_understand.py`
3. **优化参数**：根据需求调整 `--fps`、`--max-tokens` 等参数
4. **保存结果**：使用 `--json` 参数保存结构化结果
5. **批量处理**：对多个文件使用循环脚本

## 示例脚本

### 批量提取视频中的音频

```bash
#!/bin/bash
# batch_extract.sh

for video in *.mp4; do
    echo "处理: $video"
    python D:/mimo-multimodal/video_understand.py "$video" --extract-audio
    echo "完成: $video"
done
```

### 批量转录音频文件

```bash
#!/bin/bash
# batch_transcribe.sh

for audio in *.mp3; do
    echo "转录: $audio"
    python D:/mimo-multimodal/audio_understand.py "$audio" --transcribe --language zh > "${audio%.mp3}.txt"
    echo "完成: $audio"
done
```

## 更新日志

### v1.0.0 (2026-05-27)
- 初始版本
- 支持视频理解
- 支持音频提取
- 支持音频转录
- 支持指定时间段提取
- 支持多种格式
