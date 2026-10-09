#!/usr/bin/env python3
"""MIMO 多模态理解工具 - 统一入口"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python mimo_understand.py video <视频文件或URL> [选项]")
        print("  python mimo_understand.py audio <音频文件或URL> [选项]")
        print("")
        print("示例:")
        print('  python mimo_understand.py video "D:/video.mp4" -p "描述视频内容"')
        print('  python mimo_understand.py audio "https://example.com/audio.mp3" --transcribe')
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    sys.argv = [sys.argv[0]] + sys.argv[2:]  # 移除模式参数
    
    if mode == "video":
        from video_understand import main
        main()
    elif mode == "audio":
        from audio_understand import main
        main()
    else:
        print(f"未知模式: {mode}")
        print("支持的模式: video, audio")
        sys.exit(1)
