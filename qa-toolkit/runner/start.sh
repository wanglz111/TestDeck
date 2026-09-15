#!/bin/bash
# 浏览器模式启动脚本（Linux/WSL）

cd "$(dirname "$0")"

echo "================================"
echo "测试执行器 - 浏览器模式"
echo "================================"
echo ""
echo "启动后端服务..."
python3 serve.py
