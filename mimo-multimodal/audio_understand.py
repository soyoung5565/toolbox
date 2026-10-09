#!/usr/bin/env python3
"""minimax 音频理解工具 - 基于 minimax (MiniMax-M3) 视觉+音频多模态 API

(2026-07-09 改造说明)
原项目为 mimo-multimodal (使用 MiMo mimo-v2.5 视觉模型)。
切到 minimax 套餐后改用 MiniMax-M3 (支持视觉+音频多模态输入)。
环境变量名和 ~/.hermes/config.yaml 加载逻辑保持兼容 — 现在也接受
MINIMAX_API_KEY/minimax provider, 优先用 minimax, 退到 mimo。
"""
import os
import sys
import json
import base64
import argparse
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("请先安装 openai: pip install openai")
    sys.exit(1)

def get_client():
    api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("MIMO_API_KEY")
    if not api_key:
        config_path = Path.home() / ".hermes" / "config.yaml"
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                config = yaml.safe_load(f)
                # providers 是一个 dict，key 是 provider 名称
                providers = config.get("providers", {})
                if isinstance(providers, dict):
                    # 优先 minimax
                    for provider_name, provider_config in providers.items():
                        if "minimax" in provider_name.lower() and isinstance(provider_config, dict):
                            api_key = provider_config.get("api_key")
                            if api_key:
                                break
                    # 退到 mimo
                    if not api_key:
                        for provider_name, provider_config in providers.items():
                            if "mimo" in provider_name.lower() and isinstance(provider_config, dict):
                                api_key = provider_config.get("api_key")
                                if api_key:
                                    break
    if not api_key:
        print("错误: 未找到 MINIMAX_API_KEY/MIMO_API_KEY 环境变量或配置")
        sys.exit(1)

    return OpenAI(
        api_key=api_key,
        base_url="https://api.minimaxi.com/v1"
    )

def analyze_audio(audio_source, prompt="请详细描述音频内容", model="MiniMax-M3", max_tokens=4096, language=None):
    """分析音频内容"""
    client = get_client()
    
    # 处理音频源
    if audio_source.startswith(("http://", "https://")):
        audio_content = {
            "type": "input_audio",
            "input_audio": {
                "url": audio_source,
                "format": "mp3"
            }
        }
    else:
        audio_path = Path(audio_source)
        if not audio_path.exists():
            return f"错误: 文件不存在 - {audio_source}"
        
        file_size = audio_path.stat().st_size
        if file_size > 50 * 1024 * 1024:
            return f"错误: 文件过大 ({file_size / 1024 / 1024:.1f}MB)"
        
        with open(audio_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode()
        
        ext = audio_path.suffix.lower()
        format_map = {
            ".mp3": ("mp3", "audio/mpeg"),
            ".wav": ("wav", "audio/wav"),
            ".ogg": ("ogg", "audio/ogg"),
            ".flac": ("flac", "audio/flac"),
            ".m4a": ("m4a", "audio/mp4"),
            ".aac": ("aac", "audio/aac")
        }
        audio_format, mime_type = format_map.get(ext, ("mp3", "audio/mpeg"))
        
        audio_content = {
            "type": "input_audio",
            "input_audio": {
                "data": audio_data,
                "format": audio_format
            }
        }
    
    system_prompt = "你是一个专业的音频分析助手，能够详细分析音频内容、语音、音乐、音效等信息。"
    if language:
        system_prompt += f" 音频语言为{language}。"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [audio_content, {"type": "text", "text": prompt}]}
    ]
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"API调用失败: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description="MIMO 音频理解工具")
    parser.add_argument("audio", help="音频URL或本地文件路径")
    parser.add_argument("-p", "--prompt", default="请详细描述音频内容，包括语音内容、说话人、背景音等", help="分析提示词")
    parser.add_argument("--model", default="mimo-v2.5", help="模型名称")
    parser.add_argument("--max-tokens", type=int, default=4096, help="最大输出token数")
    parser.add_argument("--language", help="音频语言(如 zh, en, ja)")
    parser.add_argument("--json", action="store_true", help="输出JSON格式")
    parser.add_argument("--transcribe", action="store_true", help="仅转录音频内容")
    
    args = parser.parse_args()
    
    if args.transcribe:
        args.prompt = "请将音频中的语音内容完整转录为文字，保留原始语言，不要翻译。"
    
    result = analyze_audio(
        args.audio,
        prompt=args.prompt,
        model=args.model,
        max_tokens=args.max_tokens,
        language=args.language
    )
    
    if args.json:
        print(json.dumps({"result": result}, ensure_ascii=False, indent=2))
    else:
        print(result)

if __name__ == "__main__":
    main()
