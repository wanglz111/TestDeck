#!/bin/bash
# 原生窗模式启动脚本（Linux/WSL）

cd "$(dirname "$0")"

echo "================================"
echo "测试执行器 - 原生窗模式"
echo "================================"
echo ""

# 检查 pywebview
if ! python3 -c "import webview" 2>/dev/null; then
    echo "⚠️  未安装 pywebview，正在安装..."
    pip3 install pywebview
    echo ""
fi

echo "启动原生窗应用..."
python3 app.py
