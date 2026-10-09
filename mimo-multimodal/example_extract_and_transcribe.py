#!/usr/bin/env python3
"""示例：从视频中提取音频并转录（货币战争公式提取）"""
import subprocess
import sys
import os

def extract_and_transcribe(video_path, start_time, end_time, output_audio="extracted_audio.mp3"):
    """从视频中提取音频并转录
    
    Args:
        video_path: 视频文件路径
        start_time: 开始时间(HH:MM:SS格式)
        end_time: 结束时间(HH:MM:SS格式)
        output_audio: 输出音频文件路径
    """
    print(f"📹 正在从视频中提取音频...")
    print(f"   时间段: {start_time} - {end_time}")
    print(f"   输出: {output_audio}")
    
    # 1. 提取音频
    extract_cmd = [
        'python', 'D:/mimo-multimodal/video_understand.py',
        video_path,
        '--extract-audio',
        '--start', start_time,
        '--end', end_time,
        '--audio-format', 'mp3',
        '-o', output_audio
    ]
    
    try:
        result = subprocess.run(
            extract_cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=120
        )
        
        if result.returncode != 0:
            print(f"❌ 音频提取失败: {result.stderr}")
            return None
        
        if not os.path.exists(output_audio):
            print(f"❌ 音频文件未创建")
            return None
        
        print(f"✅ 音频提取成功: {output_audio}")
        print(f"   文件大小: {os.path.getsize(output_audio)} bytes")
        
    except Exception as e:
        print(f"❌ 音频提取异常: {e}")
        return None
    
    # 2. 转录音频
    print(f"\n🎤 正在转录音频...")
    
    transcribe_cmd = [
        'python', 'D:/mimo-multimodal/audio_understand.py',
        output_audio,
        '--transcribe',
        '--language', 'zh'
    ]
    
    try:
        result = subprocess.run(
            transcribe_cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=300
        )
        
        if result.returncode != 0:
            print(f"❌ 音频转录失败: {result.stderr}")
            return None
        
        print(f"✅ 音频转录完成")
        print(f"\n📝 转录结果:")
        print("-" * 50)
        print(result.stdout)
        print("-" * 50)
        
        return result.stdout
        
    except Exception as e:
        print(f"❌ 音频转录异常: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("用法: python example_extract_and_transcribe.py <视频文件路径> [开始时间] [结束时间] [输出音频]")
        print("\n示例:")
        print('  python example_extract_and_transcribe.py "D:/video.mp4" "04:44" "06:26" "货币战争公式.mp3"')
        print('  python example_extract_and_transcribe.py "D:/video.mp4" "00:00" "10:00" "output.mp3"')
        print("\n说明:")
        print("  - 如果不指定开始时间和结束时间，默认提取整个视频的音频")
        print("  - 如果不指定输出音频文件名，默认使用 'extracted_audio.mp3'")
        sys.exit(1)
    
    video_path = sys.argv[1]
    start_time = sys.argv[2] if len(sys.argv) > 2 else "00:00"
    end_time = sys.argv[3] if len(sys.argv) > 3 else None
    output_audio = sys.argv[4] if len(sys.argv) > 4 else "extracted_audio.mp3"
    
    if not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        sys.exit(1)
    
    print(f"🎬 视频文件: {video_path}")
    print(f"⏱️  时间段: {start_time} - {end_time or '视频结尾'}")
    print(f"🎵 输出音频: {output_audio}")
    print()
    
    result = extract_and_transcribe(video_path, start_time, end_time, output_audio)
    
    if result:
        print(f"\n🎉 任务完成!")
        print(f"转录结果已保存到输出中")
        
        # 保存转录结果到文件
        transcript_file = output_audio.replace('.mp3', '_transcript.txt')
        with open(transcript_file, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"转录文本已保存到: {transcript_file}")
    else:
        print(f"\n❌ 任务失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
