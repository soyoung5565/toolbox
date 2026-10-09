#!/usr/bin/env python3
"""电商智能客服Agent — 启动脚本

用法:
    python run.py                # 开发模式（热重载）
    python run.py --prod         # 生产模式
    python run.py --port 9000    # 自定义端口
"""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="电商智能客服Agent")
    parser.add_argument("--prod", action="store_true", help="生产模式")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    args = parser.parse_args()

    if args.prod:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            workers=4,
            log_level="info",
        )
    else:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=True,
            log_level="debug",
        )


if __name__ == "__main__":
    main()
