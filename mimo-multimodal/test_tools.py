#!/usr/bin/env python3
"""测试脚本：验证MIMO多模态工具"""
import subprocess
import sys
import os
import tempfile

def test_ffmpeg():
    """测试ffmpeg是否可用"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ ffmpeg 可用")
            return True
        else:
            print("❌ ffmpeg 不可用")
            return False
    except Exception as e:
        print(f"❌ ffmpeg 测试失败: {e}")
        return False

def test_openai():
    """测试openai库是否可用"""
    try:
        import openai
        print(f"✅ openai 库可用 (版本: {openai.__version__})")
        return True
    except ImportError:
        print("❌ openai 库未安装")
        return False

def test_mimo_config():
    """测试MIMO配置"""
    config_path = os.path.expanduser("~/.hermes/config.yaml")
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'mimo' in content.lower():
                print("✅ 配置文件中找到 MIMO 相关配置")
                return True
            else:
                print("⚠️ 配置文件中未找到 MIMO 相关配置")
                return False
    else:
        print("❌ 配置文件不存在")
        return False

def test_video_tool():
    """测试视频工具"""
    try:
        result = subprocess.run(
            ['python', 'D:/mimo-multimodal/video_understand.py', '--help'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✅ video_understand.py 可用")
            return True
        else:
            print("❌ video_understand.py 不可用")
            return False
    except Exception as e:
        print(f"❌ video_understand.py 测试失败: {e}")
        return False

def test_audio_tool():
    """测试音频工具"""
    try:
        result = subprocess.run(
            ['python', 'D:/mimo-multimodal/audio_understand.py', '--help'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✅ audio_understand.py 可用")
            return True
        else:
            print("❌ audio_understand.py 不可用")
            return False
    except Exception as e:
        print(f"❌ audio_understand.py 测试失败: {e}")
        return False

def test_audio_extraction():
    """测试音频提取功能"""
    temp_dir = tempfile.gettempdir()
    test_video = os.path.join(temp_dir, "test_video.mp4")
    test_audio = os.path.join(temp_dir, "test_audio_extracted.mp3")
    
    try:
        # 创建测试视频
        subprocess.run([
            'ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono',
            '-t', '1', '-q:v', '9', '-c:v', 'libx264', '-c:a', 'aac',
            test_video
        ], capture_output=True, check=True)
        
        # 测试音频提取（指定输出路径）
        result = subprocess.run(
            ['python', 'D:/mimo-multimodal/video_understand.py', 
             test_video, '--extract-audio', '--output', test_audio],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0 and os.path.exists(test_audio):
            print("✅ 音频提取功能正常")
            # 清理测试文件
            os.remove(test_video)
            os.remove(test_audio)
            return True
        else:
            print(f"❌ 音频提取功能异常 (返回码: {result.returncode})")
            if result.stdout:
                print(f"输出: {result.stdout}")
            if result.stderr:
                print(f"错误: {result.stderr}")
            # 清理测试文件
            if os.path.exists(test_video):
                os.remove(test_video)
            if os.path.exists(test_audio):
                os.remove(test_audio)
            return False
            
    except Exception as e:
        print(f"❌ 音频提取测试失败: {e}")
        # 清理可能创建的文件
        if os.path.exists(test_video):
            os.remove(test_video)
        if os.path.exists(test_audio):
            os.remove(test_audio)
        return False

def main():
    print("🔍 MIMO 多模态工具测试")
    print("=" * 50)
    
    tests = [
        ("环境检查", [
            ("ffmpeg", test_ffmpeg),
            ("openai", test_openai),
            ("MIMO配置", test_mimo_config),
        ]),
        ("工具检查", [
            ("video_understand.py", test_video_tool),
            ("audio_understand.py", test_audio_tool),
        ]),
        ("功能检查", [
            ("音频提取", test_audio_extraction),
        ]),
    ]
    
    all_passed = True
    
    for category, category_tests in tests:
        print(f"\n📋 {category}")
        print("-" * 30)
        
        for test_name, test_func in category_tests:
            try:
                if not test_func():
                    all_passed = False
            except Exception as e:
                print(f"❌ {test_name} 测试异常: {e}")
                all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 所有测试通过！")
        print("\n可以开始使用MIMO多模态工具了。")
        print("\n快速开始:")
        print("1. 视频理解: python D:/mimo-multimodal/video_understand.py '视频.mp4' -p '描述内容'")
        print("2. 音频提取: python D:/mimo-multimodal/video_understand.py '视频.mp4' --extract-audio -o '输出.mp3'")
        print("3. 音频转录: python D:/mimo-multimodal/audio_understand.py '音频.mp3' --transcribe")
    else:
        print("⚠️ 部分测试失败，请检查上述错误信息。")
        print("\n常见解决方案:")
        print("1. 安装ffmpeg: https://www.gyan.dev/ffmpeg/builds/")
        print("2. 安装openai: pip install openai")
        print("3. 配置MIMO API Key: ~/.hermes/config.yaml")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
