#!/bin/bash
# GitHub私有仓库上传脚本
# 用法: bash scripts/push_to_github.sh <github-username> <repo-name>

set -e

USERNAME=${1:-soyoung5565}
REPO=${2:-ecommerce-cs-agent}
REMOTE_URL="https://github.com/$USERNAME/$REPO.git"

echo "=== 上传到GitHub私有仓库 ==="
echo "用户名: $USERNAME"
echo "仓库名: $REPO"
echo "远程URL: $REMOTE_URL"
echo ""

# 检查是否已有remote
if git remote get-url origin 2>/dev/null; then
    echo "已有remote，更新..."
    git remote set-url origin "$REMOTE_URL"
else
    echo "添加remote..."
    git remote add origin "$REMOTE_URL"
fi

# 确保.gitignore包含敏感文件
echo "检查.gitignore..."
for pattern in ".env" "*.pyc" "__pycache__" ".venv" "node_modules" "*.log" "logs/"; do
    grep -q "^$pattern$" .gitignore 2>/dev/null || echo "$pattern" >> .gitignore
done

# 确保.env不被提交
git rm --cached .env 2>/dev/null || true

# 推送
echo "推送到GitHub..."
git push -u origin master

echo ""
echo "✅ 上传完成！"
echo "仓库地址: https://github.com/$USERNAME/$REPO"
echo ""
echo "⚠️  注意事项:"
echo "1. 确保仓库是Private（私有）"
echo "2. .env文件不会被提交（已在.gitignore中）"
echo "3. 部署时需要在服务器上创建.env文件"
