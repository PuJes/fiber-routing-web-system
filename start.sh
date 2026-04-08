#!/bin/bash
set -e

echo "====================================="
echo "光纤路由智能前勘系统 (Web版) 启动脚本"
echo "====================================="

VENV_PATH="/tmp/fap_env/venv"
WEB_DIR="/Users/jesspu/.openclaw/workspace/codes/fiber-routing-web"

# 检查虚拟环境
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ 错误: 找不到底层的算法虚拟环境 ($VENV_PATH)"
    echo "请先初始化 fap_env 虚拟环境。"
    exit 1
fi

# 安装 Web 服务必需依赖
echo "📦 正在检查/安装 Web 框架依赖 (Flask)..."
$VENV_PATH/bin/pip install -q Flask flask-cors

echo "🚀 正在启动后台服务..."
cd $WEB_DIR

# 启动服务器并在前台运行
$VENV_PATH/bin/python server.py
