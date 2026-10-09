#!/usr/bin/env python3
"""
MIMO 图片理解工具 — 替代丢失的 mimo-multimodal.cjs (--type image)
兼容旧命令行格式，可直接替换路径使用：
  旧: node "C:/Users/24378/.hermes/tools/mimo-multimodal.cjs" --type image --input "x.png" --prompt "问什么" --json
  新: python D:/mimo-multimodal/image_understand.py --type image --input "x.png" --prompt "问什么" --json
简洁格式: python D:/mimo-multimodal/image_understand.py x.png -p "问什么" --json
"""
import argparse, base64, json, os, sys, urllib.request

# 默认凭据（可用环境变量或 --api-key 覆盖）
API_KEY = os.environ.get('MIMO_API_KEY', 'YOUR_API_KEY')
BASE_URL = os.environ.get('MIMO_BASE_URL', 'https://token-plan-cn.xiaomimimo.com/v1')
MODEL = os.environ.get('MIMO_VISION_MODEL', 'mimo-v2-omni')

MIME = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png', 'webp': 'webp', 'gif': 'gif', 'bmp': 'bmp'}

def main():
    p = argparse.ArgumentParser(description='MIMO 图片理解')
    # 兼容旧 .cjs 参数
    p.add_argument('--type', choices=['image', 'audio', 'video'], default='image', help='兼容参数，仅支持 image')
    p.add_argument('--input', help='图片路径（兼容旧格式）')
    p.add_argument('-p', '--prompt', default='描述这张图片的内容', help='提问内容')
    p.add_argument('--json', action='store_true', help='输出 JSON（含 reasoning_content/usage）')
    p.add_argument('--model', default=MODEL, help=f'模型（默认 {MODEL}）')
    p.add_argument('--api-key', default=API_KEY, help='MIMO API key')
    p.add_argument('--base-url', default=BASE_URL)
    p.add_argument('path', nargs='?', help='图片路径（简洁格式）')
    args = p.parse_args()

    img = args.input or args.path
    if not img:
        print('错误: 请提供图片路径（--input 或位置参数）', file=sys.stderr)
        sys.exit(1)
    if args.type != 'image':
        print(f'错误: 本工具仅支持 image（{args.type} 请用 video_understand.py / audio_understand.py）', file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(img):
        print(f'错误: 文件不存在: {img}', file=sys.stderr)
        sys.exit(1)

    with open(img, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = os.path.splitext(img)[1].lstrip('.').lower()
    mime = MIME.get(ext, 'png')

    body = {
        'model': args.model,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': f'data:image/{mime};base64,{b64}'}},
                {'type': 'text', 'text': args.prompt},
            ],
        }],
        'max_tokens': 2000,
    }
    req = urllib.request.Request(
        args.base_url + '/chat/completions',
        data=json.dumps(body).encode('utf-8'),
        headers={'Authorization': f'Bearer {args.api_key}', 'Content-Type': 'application/json'},
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
    except Exception as e:
        print(f'API 调用失败: {e}', file=sys.stderr)
        sys.exit(1)

    msg = resp.get('choices', [{}])[0].get('message', {})
    out = {
        'content': msg.get('content', ''),
        'reasoning_content': msg.get('reasoning_content', ''),
        'usage': resp.get('usage', {}),
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(out['content'])

if __name__ == '__main__':
    main()
