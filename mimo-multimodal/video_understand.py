#!/usr/bin/env python3
"""minimax 视频理解工具 - 基于 minimax (MiniMax-M3) 视觉多模态 API

(2026-07-09 改造说明)
原项目为 mimo-multimodal (使用 MiMo mimo-v2.5 视觉模型)。
切到 minimax 套餐后改用 MiniMax-M3 (支持视觉多模态输入)。
"""
import os
import sys
import json
import base64
import argparse
import tempfile
import subprocess
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
                for provider in config.get("providers", []):
                    if provider.get("name") == "minimax":
                        api_key = provider.get("api_key")
                        break
                if not api_key:
                    for provider in config.get("providers", []):
                        if provider.get("name") == "mimo":
                            api_key = provider.get("api_key")
                            break
    if not api_key:
        print("错误: 未找到 MINIMAX_API_KEY/MIMO_API_KEY 环境变量或配置")
        sys.exit(1)

    return OpenAI(
        api_key=api_key,
        base_url="https://api.minimaxi.com/v1"
    )

def extract_audio(video_path, start_time=None, end_time=None, output_format="mp3", output_path=None):
    """从视频中提取音频
    
    Args:
        video_path: 视频文件路径
        start_time: 开始时间(格式: HH:MM:SS 或秒数)
        end_time: 结束时间(格式: HH:MM:SS 或秒数)
        output_format: 输出格式(mp3, wav, etc.)
        output_path: 输出文件路径(可选)
    
    Returns:
        音频文件路径
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    
    # 如果未指定输出路径，使用默认路径
    if output_path is None:
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"extracted_audio.{output_format}")
    
    # 构建ffmpeg命令
    cmd = ["ffmpeg", "-y", "-i", video_path]
    
    if start_time:
        cmd.extend(["-ss", str(start_time)])
    if end_time:
        cmd.extend(["-to", str(end_time)])
    
    cmd.extend(["-vn", "-acodec", "libmp3lame" if output_format == "mp3" else "copy", output_path])
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"音频提取失败: {e.stderr.decode()}")

def analyze_video(video_source, prompt="请详细描述视频内容", fps=1, model="mimo-v2.5", max_tokens=4096):
    """分析视频内容"""
    client = get_client()
    
    # 处理视频源
    if video_source.startswith(("http://", "https://")):
        video_content = {
            "type": "video_url",
            "video_url": {"url": video_source},
            "fps": fps,
            "media_resolution": "default"
        }
    else:
        video_path = Path(video_source)
        if not video_path.exists():
            return f"错误: 文件不存在 - {video_source}"
        
        file_size = video_path.stat().st_size
        if file_size > 300 * 1024 * 1024:
            return f"错误: 文件过大 ({file_size / 1024 / 1024:.1f}MB)，最大支持300MB"
        
        with open(video_path, "rb") as f:
            video_data = base64.b64encode(f.read()).decode()
        
        ext = video_path.suffix.lower()
        mime_map = {
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
            ".mov": "video/quicktime",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm"
        }
        mime_type = mime_map.get(ext, "video/mp4")
        
        video_content = {
            "type": "video_url",
            "video_url": {"url": f"data:{mime_type};base64,{video_data}"},
            "fps": fps,
            "media_resolution": "default"
        }
    
    messages = [
        {"role": "system", "content": "你是一个专业的视频分析助手，能够详细分析视频内容、画面、动作、对话、场景等信息。"},
        {"role": "user", "content": [video_content, {"type": "text", "text": prompt}]}
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
    parser = argparse.ArgumentParser(description="MIMO 视频理解工具")
    parser.add_argument("video", help="视频URL或本地文件路径")
    parser.add_argument("-p", "--prompt", default="请详细描述视频内容，包括画面、动作、对话、场景等", help="分析提示词")
    parser.add_argument("--fps", type=float, default=1, help="抽帧频率(每秒帧数)")
    parser.add_argument("--model", default="mimo-v2.5", help="模型名称")
    parser.add_argument("--max-tokens", type=int, default=4096, help="最大输出token数")
    parser.add_argument("--json", action="store_true", help="输出JSON格式")
    parser.add_argument("--extract-audio", action="store_true", help="仅提取音频")
    parser.add_argument("--start", help="开始时间(HH:MM:SS或秒数)")
    parser.add_argument("--end", help="结束时间(HH:MM:SS或秒数)")
    parser.add_argument("--audio-format", default="mp3", help="音频输出格式")
    parser.add_argument("--output", "-o", help="输出文件路径")
    
    args = parser.parse_args()
    
    if args.extract_audio:
        try:
            output_path = extract_audio(args.video, args.start, args.end, args.audio_format, args.output)
            if args.json:
                print(json.dumps({"audio_path": output_path}, ensure_ascii=False, indent=2))
            else:
                print(f"音频已提取到: {output_path}")
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)
    else:
        result = analyze_video(
            args.video,
            prompt=args.prompt,
            fps=args.fps,
            model=args.model,
            max_tokens=args.max_tokens
        )
        
        if args.json:
            print(json.dumps({"result": result}, ensure_ascii=False, indent=2))
        else:
            print(result)

if __name__ == "__main__":
    main()
